"""
Mirror performance predictor used by the server, optimizers and RL environment.

  mass_kg              EXACT  - computed from the NX journal geometry (cad_engine/exact_mass.py);
                                identical to the NX-built part when every pocket is cut.
  rms_sag_nm, pv_sag_nm FEA-TRAINED surrogate (ml_engine/fea_surrogate.py), trained only on
                                genuine FE gravity analyses of the exact geometry; returns a
                                1-sigma uncertainty and a validity-domain flag.
  quilting_nm          ANALYTIC estimate (Yoder Eq. 2.35 polishing-pressure quilting of one
                                pocket cell) - labelled as such, not FEA.
  frequency_hz         ANALYTIC estimate (Leissa free circular plate, smeared isogrid
                                rigidity) - labelled as such, not FEA.

No calibration constants, packing factors or formula-vs-formula "active learning" remain.
"""
import math
import os
import sys

import numpy as np

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from cad_engine.exact_mass import isogrid_exact_mass, isogrid_exact_mass_fast  # noqa: E402
from ml_engine.fea_surrogate import get_surrogate, MATERIALS  # noqa: E402

FEATURE_COLS = ["D_mm", "Dc_mm", "H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm"]
TARGET_COLS = ["mass_kg", "rms_sag_nm", "pv_sag_nm", "quilting_nm", "frequency_hz"]
POLISH_PRESSURE_PA = 1378.95  # 0.2 psi polishing pressure (Yoder)


def analytic_quilting_nm(tf_mm, tw_mm, L_mm, E_pa):
    """Yoder & Vukobratovich Eq. 2.35: quilting under polishing pressure, triangular cell
    (inscribed-circle span B = pocket side / sqrt(3)). Analytic estimate, not FEA."""
    pocket_side = max(1.0, L_mm - 2.0 * tw_mm / math.sqrt(3.0))
    B = (pocket_side / math.sqrt(3.0)) * 1e-3
    tf = tf_mm * 1e-3
    return 0.00151 * POLISH_PRESSURE_PA * B ** 4 / (E_pa * tf ** 3) * 1e9


def analytic_frequency_hz(mass_kg, D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, E_pa, nu):
    """Leissa: lowest elastic mode of a free circular plate (2 nodal diameters, lambda^2 = 5.25)
    using smeared isogrid bending rigidity (NASA CR-124075). Analytic estimate, not FEA."""
    tf = tf_mm * 1e-3
    h = max(1e-3, (H_mm - tf_mm)) * 1e-3
    alpha = (2.0 / math.sqrt(3.0)) * (tw_mm / L_mm)
    delta = h / tf
    D0 = E_pa * tf ** 3 / (12 * (1 - nu ** 2))
    num = (1 + alpha * delta) ** 2 + 3 * alpha * delta * (1 + delta) ** 2 + alpha ** 2 * delta ** 4
    Dstar = D0 * num / max(0.01, 1 + alpha * delta)
    a = D_mm / 2000.0
    area = math.pi * (a ** 2 - (Dc_mm / 2000.0) ** 2)
    m_area = mass_kg / area
    return 5.25 / (2 * math.pi * a ** 2) * math.sqrt(Dstar / m_area)


class MirrorSurrogatePredictor:
    def __init__(self, models_dir=None):
        self.features = FEATURE_COLS
        self.targets = TARGET_COLS

    @property
    def sur(self):
        s = get_surrogate()
        if not s.models:
            raise RuntimeError("FEA surrogate has no training data yet - run fea_engine/generate_fea_dataset.py")
        return s

    @staticmethod
    def compute_exact_cad_mass(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, rho=2530e-9, **_):
        return isogrid_exact_mass(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, rho_kg_m3=rho * 1e9)["mass_kg"]

    @staticmethod
    def compute_exact_cad_mass_batch(D_arr, Dc_arr, H_arr, tf_arr, tw_arr, L_arr, rf_arr, rho=2530e-9, **_):
        rho = np.broadcast_to(np.asarray(rho, float), np.shape(D_arr))
        return np.array([isogrid_exact_mass_fast(d, dc, h, tf, tw, l, rf, rho_kg_m3=r * 1e9)["mass_kg"]
                         for d, dc, h, tf, tw, l, rf, r in zip(D_arr, Dc_arr, H_arr, tf_arr, tw_arr, L_arr, rf_arr, rho)])

    def predict(self, D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, material="zerodur",
                topology="triangular_isogrid", max_sag_nm=60.0, max_mass_kg=None):
        mat = MATERIALS.get((material or "zerodur").lower(), MATERIALS["zerodur"])
        m = isogrid_exact_mass(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, rho_kg_m3=mat["rho"], details=True)
        ok, issues = self.sur.in_domain(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, topology=topology)
        p = self.sur.predict(H_mm, tf_mm, tw_mm, L_mm, rf_mm, material=material)
        quilt = analytic_quilting_nm(tf_mm, tw_mm, L_mm, mat["E"])
        f1 = analytic_frequency_hz(m["mass_kg"], D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, mat["E"], mat["nu"])
        sag = p["rms_sag_nm"]
        status = "PASS" if sag <= max_sag_nm and (max_mass_kg is None or m["mass_kg"] <= max_mass_kg) else "REVIEW"
        return {
            "mass_kg": round(m["mass_kg"], 4),
            "mass_source": "exact NX-journal geometry (no fitted factors)",
            "solid_mass_kg": round(m["solid_mass_kg"], 3),
            "lightweight_pct": round(m["lightweight_pct"], 2),
            "pocket_count": m["pocket_count"],
            "rms_sag_nm": round(sag, 3),
            "rms_sag_std_nm": round(p["rms_sag_nm_std"], 3),
            "pv_sag_nm": round(p["pv_sag_nm"], 3),
            "rms_sag_power_removed_nm": round(p["rms_sag_power_removed_nm"], 3),
            "sag_source": f"GP surrogate trained on {self.sur.meta.get('n_training_records', 0)} FEA runs of the exact geometry",
            "quilting_nm": round(quilt, 2),
            "quilting_source": "analytic estimate (Yoder Eq. 2.35) - not FEA",
            "frequency_hz": round(f1, 1),
            "frequency_source": "analytic estimate (free circular plate, smeared isogrid) - not FEA",
            "zernike_fringe_37_nm": [round(v, 4) for v in p["zernike_fringe_37_nm"]],
            "in_validity_domain": ok,
            "validity_warnings": issues,
            "status": status,
        }

    def predict_batch(self, feature_matrix, material="zerodur"):
        """Columns in: D, Dc, H, tf, tw, L, rf.  Columns out: mass, rms, pv, quilting, f1."""
        fm = np.asarray(feature_matrix, dtype=float)
        mat = MATERIALS.get((material or "zerodur").lower(), MATERIALS["zerodur"])
        mass = np.array([isogrid_exact_mass_fast(*row, rho_kg_m3=mat["rho"])["mass_kg"] for row in fm])
        s = self.sur.predict_batch(fm[:, [3, 4, 5, 6, 2]], material=material)
        quilt = np.array([analytic_quilting_nm(r[3], r[4], r[5], mat["E"]) for r in fm])
        f1 = np.array([analytic_frequency_hz(mm, r[0], r[1], r[2], r[3], r[4], r[5], mat["E"], mat["nu"])
                       for mm, r in zip(mass, fm)])
        return np.column_stack([mass, s["rms_sag_nm"], s["pv_sag_nm"], quilt, f1])


if __name__ == "__main__":
    pr = MirrorSurrogatePredictor()
    r = pr.predict(560.0, 175.0, 73.7, 3.2, 5.3, 46.4, 3.9)
    r.pop("zernike_fringe_37_nm")
    for k, v in r.items():
        print(f"  {k}: {v}")
