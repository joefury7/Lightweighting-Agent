"""
FEA-trained surrogate for the isogrid mirror (replaces the XGBoost / "PINN" models that were
trained on closed-form formulas and mis-mapped external datasets).

Training data
-------------
Only genuine finite-element results of the *exact* NX journal geometry:
  * data/fea/isogrid_fea_dataset.jsonl   - CalculiX C3D10 runs  (fea_engine/generate_fea_dataset.py)
  * data/fea/nx_nastran_results.jsonl     - NX Nastran SOL 101 runs (highest fidelity; used with
                                            priority and lower noise whenever present)
Mass is NOT learned: it is computed exactly from the journal geometry (cad_engine/exact_mass.py).

Model
-----
Gaussian-process regression (Matern 5/2, ARD length scales + white noise) on
    log(RMS sag), log(PV sag), log(RMS sag with power removed)
and on the normalised 37-term Fringe Zernike shape  z_j / RMS_sag,
with inputs (faceplate tf, rib tw, cell L, fillet rf, depth H) plus the ACTUAL mean radii of the inner and
outer support pads after the journal snaps them to lattice nodes (these jump with L and drive the focus term).
A GP is the right tool for ~100 expensive FEA samples: it interpolates them, reports its own
uncertainty, and its leave-one-out error is reported as the honest "prediction gap".

Materials
---------
For a fixed geometry under gravity, linear-elastic deflection scales exactly with rho/E
(Poisson's ratio enters only weakly).  Predictions for other materials scale the Zerodur
FEA surrogate by (rho/E) / (rho/E)_Zerodur; the small Poisson effect is measured with
CalculiX runs (fea_engine/material_check.py) and reported, not hidden.
"""
import json
import math
import os
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILES = [
    ("nx_nastran", os.path.join(ROOT, "data", "fea", "nx_nastran_results.jsonl")),
    ("calculix", os.path.join(ROOT, "data", "fea", "isogrid_fea_dataset.jsonl")),
]
FEATURES = ["faceplate", "ribThick", "cellSize", "filletRadius", "depth"]
BOUNDS = {"faceplate": (0.8, 3.5), "ribThick": (1.5, 5.5), "cellSize": (38.0, 92.0),
          "filletRadius": (1.0, 10.0), "depth": (55.0, 95.0)}
DOMAIN = {"diameter": 560.0, "centralHoleDia": 175.0, "radiusCurv": 1085.0, "conicConstant": -1.22}
MATERIALS = {
    "zerodur": {"E": 90.3e9, "nu": 0.24, "rho": 2530.0},
    "ule": {"E": 67.6e9, "nu": 0.17, "rho": 2210.0},
    "sic": {"E": 420.0e9, "nu": 0.14, "rho": 3160.0},
    "beryllium": {"E": 303.0e9, "nu": 0.08, "rho": 1850.0},
    "fused_silica": {"E": 72.7e9, "nu": 0.17, "rho": 2200.0},
}
SCALAR_TARGETS = ["rms_sag_nm", "pv_sag_nm", "rms_sag_power_removed_nm"]


def analytic_sag_proxy(H, tf, tw, L, mass_kg, D=560.0, Dc=175.0, E=90.3e9, nu=0.24):
    """Classical plate scaling  delta ~ q R^4 / D*  (q = areal weight from the EXACT mass,
    D* = smeared isogrid bending rigidity, NASA CR-124075).  Used only as a prior mean: the GP
    learns log(FEA / proxy), so the absolute coefficient is irrelevant."""
    tf_m, h_m, tw_m, L_m = tf * 1e-3, max(1.0, H - tf) * 1e-3, tw * 1e-3, L * 1e-3
    alpha = (2.0 / math.sqrt(3.0)) * (tw_m / L_m)
    delta = h_m / tf_m
    D0 = E * tf_m ** 3 / (12 * (1 - nu ** 2))
    num = (1 + alpha * delta) ** 2 + 3 * alpha * delta * (1 + delta) ** 2 + alpha ** 2 * delta ** 4
    Dstar = D0 * num / max(0.01, 1 + alpha * delta)
    R = D / 2000.0
    area = math.pi * (R ** 2 - (Dc / 2000.0) ** 2)
    q = mass_kg * 9.80665 / area
    return q * R ** 4 / Dstar * 1e9


def _proxy_for(H, tf, tw, L, rf):
    from cad_engine.exact_mass import isogrid_exact_mass_fast
    m = isogrid_exact_mass_fast(DOMAIN["diameter"], DOMAIN["centralHoleDia"], H, tf, tw, L, rf)["mass_kg"]
    return analytic_sag_proxy(H, tf, tw, L, m)


HUB_BOUNDS = {"r_hub_inner": (100.0, 190.0), "r_hub_outer": (195.0, 275.0), "outer_pair_half_angle": (5.0, 25.0)}


def hub_radii(L, D=560.0, Dc=175.0):
    """Mean radii of the 6 inner and 12 outer support pads AFTER the journal's node snapping.
    Snapping makes the real support radii jump with cell size L, which drives the focus (Z4)
    term of the gravity sag - so they are given to the GP as explicit inputs."""
    from optimizer.node_snapping import snap_18_whiffletree_hubs
    h = snap_18_whiffletree_hubs(D, float(L), Dc)
    ri = float(np.mean([math.hypot(*p) for p in h[:6]]))
    ro = float(np.mean([math.hypot(*p) for p in h[6:]]))
    half = []
    for i in range(6):   # angular half-spread of each outer pad pair about its rocker axis (deg)
        a1 = math.degrees(math.atan2(h[6 + 2 * i][1], h[6 + 2 * i][0]))
        a2 = math.degrees(math.atan2(h[7 + 2 * i][1], h[7 + 2 * i][0]))
        half.append(abs((a2 - a1 + 180.0) % 360.0 - 180.0) / 2.0)
    return ri, ro, float(np.mean(half))


_HUB_CACHE = {}


def _hub_cached(L):
    k = round(float(L), 1)
    if k not in _HUB_CACHE:
        _HUB_CACHE[k] = hub_radii(k)
    return _HUB_CACHE[k]


def _scale(X):
    """X columns: tf, tw, L, rf, H  ->  scaled [tf, tw, L, rf, H, r_hub_inner, r_hub_outer, outer_pair_half_angle]."""
    X = np.asarray(X, float)
    lo = np.array([BOUNDS[f][0] for f in FEATURES])
    hi = np.array([BOUNDS[f][1] for f in FEATURES])
    base = (X - lo) / (hi - lo)
    hubs = np.array([_hub_cached(L) for L in X[:, 2]])
    keys = ["r_hub_inner", "r_hub_outer", "outer_pair_half_angle"]
    hlo = np.array([HUB_BOUNDS[k][0] for k in keys])
    hhi = np.array([HUB_BOUNDS[k][1] for k in keys])
    return np.column_stack([base, (hubs - hlo) / (hhi - hlo)])


def load_records():
    recs = []
    seen = set()
    for source, path in DATA_FILES:
        if not os.path.exists(path):
            continue
        for ln in open(path, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            if r.get("material", "zerodur") != "zerodur":
                continue
            p = r["params"]
            key = tuple(round(float(p[f]), 1) for f in FEATURES)
            if key in seen:      # NX Nastran result (read first) wins over CalculiX for same design
                continue
            seen.add(key)
            r["_source"] = source
            recs.append(r)
    return recs


class FEASurrogate:
    def __init__(self, records=None, fit=True, use_prior=True):
        self.use_prior = use_prior
        self.records = records if records is not None else load_records()
        self.models = {}
        self.z_model = None
        self.meta = {}
        if fit and len(self.records) >= 5:
            self.fit()

    # ------------------------------------------------------------------
    def _X(self, recs):
        return np.array([[float(r["params"][f]) for f in FEATURES] for r in recs])

    def _make_gp(self, noise=1e-4):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern, ConstantKernel, WhiteKernel
        k = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=np.ones(len(FEATURES) + 3) * 0.5,
                                                    length_scale_bounds=(0.03, 30.0), nu=2.5) \
            + WhiteKernel(noise, (1e-8, 1e-1))
        return GaussianProcessRegressor(kernel=k, normalize_y=True, n_restarts_optimizer=3, random_state=0)

    def fit(self, records=None):
        recs = records if records is not None else self.records
        X = _scale(self._X(recs))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._prior_train = np.array([self._log_prior(r["params"]) for r in recs])
            for t in SCALAR_TARGETS:
                y = np.log(np.array([max(1e-6, float(r[t])) for r in recs])) - self._prior_train
                gp = self._make_gp()
                gp.fit(X, y)
                self.models[t] = gp
            Z = np.array([np.array(r["zernike_fringe_37_nm"]) / max(1e-9, float(r["rms_sag_nm"])) for r in recs])
            gpz = self._make_gp()
            gpz.fit(X, Z)
            self.z_model = gpz
        self.meta = {"n_training_records": len(recs), "physics_prior": "log(FEA / smeared-plate q R^4 / D*)" if self.use_prior else None,
                     "sources": {s: sum(1 for r in recs if r["_source"] == s) for s in ("calculix", "nx_nastran")}}
        return self

    def _log_prior(self, p):
        if not self.use_prior:
            return 0.0
        return math.log(_proxy_for(float(p["depth"]), float(p["faceplate"]), float(p["ribThick"]),
                                   float(p["cellSize"]), float(p["filletRadius"])))

    # ------------------------------------------------------------------
    @staticmethod
    def in_domain(D, Dc, H, tf, tw, L, rf, R_curv=1085.0, k=-1.22, topology="triangular_isogrid"):
        issues = []
        if topology not in ("triangular_isogrid", "isogrid"):
            issues.append(f"topology '{topology}' has no FEA training data (only triangular isogrid)")
        for name, v, ref in [("diameter", D, 560.0), ("centralHoleDia", Dc, 175.0), ("radiusCurv", R_curv, 1085.0)]:
            if abs(v - ref) > 0.05:
                issues.append(f"{name}={v} differs from the FEA-sampled value {ref}")
        if abs(k - (-1.22)) > 1e-4:
            issues.append(f"conicConstant={k} differs from -1.22")
        for f, v in zip(FEATURES, [tf, tw, L, rf, H]):
            lo, hi = BOUNDS[f]
            if v < lo - 1e-9 or v > hi + 1e-9:
                issues.append(f"{f}={v} outside sampled range [{lo}, {hi}]")
        return (len(issues) == 0), issues

    def material_factor(self, material):
        m = MATERIALS.get((material or "zerodur").lower(), MATERIALS["zerodur"])
        z = MATERIALS["zerodur"]
        return (m["rho"] / m["E"]) / (z["rho"] / z["E"])

    def predict(self, H, tf, tw, L, rf, material="zerodur", return_std=True):
        x = _scale([[tf, tw, L, rf, H]])
        f = self.material_factor(material)
        lp = self._log_prior({"depth": H, "faceplate": tf, "ribThick": tw, "cellSize": L, "filletRadius": rf})
        out = {}
        for t, gp in self.models.items():
            mu, sd = gp.predict(x, return_std=True)
            out[t] = float(math.exp(mu[0] + lp)) * f
            out[t + "_std"] = float(math.exp(mu[0] + lp) * sd[0]) * f  # delta-method 1-sigma
        z = self.z_model.predict(x)[0] * out["rms_sag_nm"]
        out["zernike_fringe_37_nm"] = [float(v) for v in z]
        return out

    def predict_batch(self, X5, material="zerodur"):
        """X5 columns: tf, tw, L, rf, H -> dict of arrays."""
        X5 = np.asarray(X5, float)
        x = _scale(X5)
        f = self.material_factor(material)
        lp = np.array([self._log_prior({"faceplate": r[0], "ribThick": r[1], "cellSize": r[2], "filletRadius": r[3], "depth": r[4]})
                       for r in X5]) if self.use_prior else 0.0
        return {t: np.exp(gp.predict(x) + lp) * f for t, gp in self.models.items()}

    # ------------------------------------------------------------------
    def loo_cv(self, records=None):
        """Leave-one-out prediction errors on the FEA records (the honest prediction gap)."""
        recs = records if records is not None else self.records
        errs = {t: [] for t in SCALAR_TARGETS}
        rows = []
        for i in range(len(recs)):
            tr = recs[:i] + recs[i + 1:]
            s = FEASurrogate(tr, fit=True, use_prior=self.use_prior)
            p = recs[i]["params"]
            pr = s.predict(p["depth"], p["faceplate"], p["ribThick"], p["cellSize"], p["filletRadius"])
            row = {"id": recs[i]["id"]}
            for t in SCALAR_TARGETS:
                e = 100.0 * (pr[t] - float(recs[i][t])) / float(recs[i][t])
                errs[t].append(e)
                row[t + "_fea"] = float(recs[i][t])
                row[t + "_pred"] = pr[t]
                row[t + "_err_pct"] = e
            rows.append(row)
        summary = {t: {"mape_pct": float(np.mean(np.abs(v))), "max_abs_pct": float(np.max(np.abs(v))),
                       "rmse_pct": float(np.sqrt(np.mean(np.square(v))))} for t, v in errs.items()}
        return summary, rows


_SINGLETON = None


def get_surrogate(refresh=False):
    global _SINGLETON
    if _SINGLETON is None or refresh:
        cfg = os.path.join(ROOT, "data", "fea", "surrogate_config.json")
        use_prior = json.load(open(cfg)).get("use_prior", True) if os.path.exists(cfg) else True
        _SINGLETON = FEASurrogate(use_prior=use_prior)
    return _SINGLETON
