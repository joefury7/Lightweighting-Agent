"""
NSGA-II multi-objective optimiser (Pillar 3) for the isogrid mirror.

Fitness evaluations use:
  * exact mass of the NX-journal geometry (cad_engine/exact_mass.py) - not a model,
  * RMS gravity sag from the FEA-trained Gaussian-process surrogate (ml_engine/fea_surrogate.py),
  * analytic polishing-quilting estimate (Yoder Eq. 2.35) as a manufacturing constraint.

Decision variables: faceplate tf, rib tw, cell L, fillet rf (blank depth H fixed to the user's blank,
or free when H is not given).  Bounds = the FEA-sampled validity domain, plus the journal's own
geometric validity rule rf <= 0.45 * pocket circumradius.

The closed loop: run genuine FEA on the optimum (/fea/solve), the record is appended to the FEA
dataset and the surrogate is refitted (that is the active-learning step - with real FEA, not a
second formula).
"""
import json
import math
import os
import sys
import time

import numpy as np

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor  # noqa: E402
from ml_engine.fea_surrogate import BOUNDS, get_surrogate  # noqa: E402
from optimizer.node_snapping import snap_18_whiffletree_hubs  # noqa: E402

FEA_DATASET = os.path.join(workspace_root, "data", "fea", "isogrid_fea_dataset.jsonl")
MAX_QUILT_NM = 30.0


def non_dominated_sort(objectives):
    N = objectives.shape[0]
    dom = np.all(objectives[:, None, :] <= objectives[None, :, :], axis=2) & \
        np.any(objectives[:, None, :] < objectives[None, :, :], axis=2)
    counts = dom.sum(axis=0)
    dominated = [np.where(dom[p])[0].tolist() for p in range(N)]
    fronts, cur = [], np.where(counts == 0)[0].tolist()
    while cur:
        fronts.append(cur)
        nxt = []
        for p in cur:
            for q in dominated[p]:
                counts[q] -= 1
                if counts[q] == 0:
                    nxt.append(q)
        cur = nxt
    return fronts


def calculate_crowding_distance(objectives, front):
    if len(front) <= 2:
        return np.full(len(front), np.inf)
    d = np.zeros(len(front))
    F = objectives[front]
    for m in range(F.shape[1]):
        o = np.argsort(F[:, m])
        d[o[0]] = d[o[-1]] = np.inf
        rng = F[o[-1], m] - F[o[0], m] + 1e-12
        d[o[1:-1]] += (F[o[2:], m] - F[o[:-2], m]) / rng
    return d


def max_fillet(L, tw):
    return 0.45 * (L - tw * 2.0 / math.sqrt(3.0)) / math.sqrt(3.0)


class ClosedLoopOptimizer:
    def __init__(self, buffer_file=None):
        self.predictor = MirrorSurrogatePredictor()

    # --------------------------------------------------------------
    def _evaluate(self, pop, D, Dc, material):
        N = len(pop)
        fm = np.column_stack([np.full(N, D), np.full(N, Dc), pop[:, 4], pop[:, 0], pop[:, 1], pop[:, 2], pop[:, 3]])
        return self.predictor.predict_batch(fm, material=material)

    def optimize_nsga2(self, D_mm=560.0, Dc_mm=175.0, H_mm=73.7, max_mass_kg=12.0, max_sag_nm=60.0,
                       pop_size=120, generations=40, eta_c=15.0, eta_m=20.0, mode="target",
                       material="zerodur", seed=42):
        rng = np.random.default_rng(seed)
        t0 = time.time()
        lo = np.array([BOUNDS["faceplate"][0], BOUNDS["ribThick"][0], BOUNDS["cellSize"][0], BOUNDS["filletRadius"][0], BOUNDS["depth"][0]])
        hi = np.array([BOUNDS["faceplate"][1], BOUNDS["ribThick"][1], BOUNDS["cellSize"][1], BOUNDS["filletRadius"][1], BOUNDS["depth"][1]])
        if H_mm is not None and H_mm > 5.0:
            lo[4] = hi[4] = float(H_mm)
        is_min = str(mode).lower() == "min" or str(max_mass_kg).upper() == "MIN" or float(max_mass_kg) >= 900.0
        target = None if is_min else float(max_mass_kg)

        def repair(P):
            P = np.clip(P, lo, hi)
            P[:, 3] = np.minimum(P[:, 3], np.maximum(lo[3], [max_fillet(L, tw) for L, tw in zip(P[:, 2], P[:, 1])]))
            return np.round(P, 1)   # the journal writes every dimension with 0.1 mm resolution

        def objectives(P):
            Y = self._evaluate(P, D_mm, Dc_mm, material)
            mass, sag, quilt = Y[:, 0], Y[:, 1], Y[:, 3]
            viol = np.maximum(0, sag - max_sag_nm) / max_sag_nm + np.maximum(0, quilt - MAX_QUILT_NM) / MAX_QUILT_NM
            o1 = (np.abs(mass - target) if target is not None else mass) + 1e3 * viol
            o2 = sag + 1e3 * viol
            return np.column_stack([o1, o2]), Y, viol

        pop = repair(lo + rng.random((pop_size, 5)) * (hi - lo))
        for _ in range(generations):
            F, _, _ = objectives(pop)
            fronts = non_dominated_sort(F)
            rank = np.zeros(pop_size, int)
            crowd = np.zeros(pop_size)
            for r, fr in enumerate(fronts):
                rank[fr] = r
                crowd[fr] = calculate_crowding_distance(F, fr)

            def tour():
                a, b = rng.choice(pop_size, 2, replace=False)
                if rank[a] != rank[b]:
                    return pop[a] if rank[a] < rank[b] else pop[b]
                return pop[a] if crowd[a] >= crowd[b] else pop[b]
            kids = np.empty_like(pop)
            for i in range(0, pop_size, 2):
                p1, p2 = tour(), tour()
                u = rng.random(5)
                beta = np.where(u <= 0.5, (2 * u) ** (1 / (eta_c + 1)), (1 / (2 * (1 - u))) ** (1 / (eta_c + 1)))
                c1 = 0.5 * ((1 + beta) * p1 + (1 - beta) * p2)
                c2 = 0.5 * ((1 - beta) * p1 + (1 + beta) * p2)
                for c in (c1, c2):
                    m = rng.random(5) < 1.0 / 4
                    um = rng.random(5)
                    dl = np.where(um < 0.5, (2 * um) ** (1 / (eta_m + 1)) - 1, 1 - (2 * (1 - um)) ** (1 / (eta_m + 1)))
                    c[m] += dl[m] * (hi[m] - lo[m])
                kids[i] = c1
                if i + 1 < pop_size:
                    kids[i + 1] = c2
            comb = np.vstack([pop, repair(kids)])
            Fc, _, _ = objectives(comb)
            sel = []
            for fr in non_dominated_sort(Fc):
                if len(sel) + len(fr) <= pop_size:
                    sel += fr
                else:
                    cd = calculate_crowding_distance(Fc, fr)
                    sel += [fr[j] for j in np.argsort(-cd)[:pop_size - len(sel)]]
                    break
            pop = comb[sel]

        F, Y, viol = objectives(pop)
        feas = np.where(viol <= 0)[0]
        if len(feas):
            if target is not None:
                score = np.abs(Y[feas, 0] - target) / 0.05 + 0.5 * Y[feas, 1] / max_sag_nm
            else:
                score = Y[feas, 0] + 0.01 * Y[feas, 1]
            best = feas[np.argmin(score)]
        else:
            best = int(np.argmin(viol))
        g = pop[best]
        p = self.predictor.predict(D_mm, Dc_mm, g[4], g[0], g[1], g[2], g[3], material=material, max_sag_nm=max_sag_nm)
        feasible_target = bool(len(feas)) and (target is None or abs(p["mass_kg"] - target) <= 0.1)
        return {
            "D_mm": float(D_mm), "Dc_mm": float(Dc_mm), "H_mm": float(g[4]),
            "tf_mm": float(g[0]), "tw_mm": float(g[1]), "L_mm": float(g[2]), "rf_mm": float(g[3]),
            "material": material,
            "predicted_mass_kg": p["mass_kg"], "mass_kg": p["mass_kg"],
            "predicted_rms_sag_nm": p["rms_sag_nm"], "rms_sag_nm": p["rms_sag_nm"],
            "rms_sag_std_nm": p["rms_sag_std_nm"],
            "predicted_pv_sag_nm": p["pv_sag_nm"], "predicted_quilting_nm": p["quilting_nm"],
            "predicted_freq_hz": p["frequency_hz"], "frequency_source": p["frequency_source"],
            "lightweight_pct": p["lightweight_pct"], "pocket_count": p["pocket_count"],
            "zernike_fringe_37_nm": p["zernike_fringe_37_nm"],
            "all_constraints_satisfied": feasible_target,
            "feasible_count": int(len(feas)),
            "optimizer_method": "NSGA-II (exact mass + FEA-trained sag surrogate)",
            "evaluation_duration_ms": round((time.time() - t0) * 1000, 1),
            "surrogate": p["sag_source"],
            "validity_warnings": p["validity_warnings"],
            "support_hubs_18": snap_18_whiffletree_hubs(D_mm, float(g[2]), Dc_mm),
        }

    def optimize(self, D_mm=560.0, Dc_mm=175.0, H_mm=73.7, max_mass_kg=12.0, max_sag_nm=60.0,
                 num_candidates=None, mode="target", material="zerodur"):
        """Kept for API compatibility: runs NSGA-II (the old random-search path was removed)."""
        return self.optimize_nsga2(D_mm, Dc_mm, H_mm, max_mass_kg, max_sag_nm, mode=mode, material=material)

    # --------------------------------------------------------------
    @staticmethod
    def add_fea_record(design, fea_result, source="calculix"):
        """Closed loop: append a genuine FEA result to the dataset and refit the surrogate."""
        rec = {
            "id": f"loop_{time.strftime('%Y%m%d_%H%M%S')}",
            "params": {"faceplate": round(design["tf_mm"], 1), "ribThick": round(design["tw_mm"], 1),
                       "cellSize": round(design["L_mm"], 1), "filletRadius": round(design["rf_mm"], 1),
                       "depth": round(design["H_mm"], 1)},
            "fixed": {"diameter": design["D_mm"], "centralHoleDia": design["Dc_mm"]},
            "material": "zerodur",
            "source": source,
            **{k: v for k, v in fea_result.items() if k in (
                "rms_sag_nm", "pv_sag_nm", "rms_sag_power_removed_nm", "zernike_fringe_37_nm",
                "replica_mass_kg", "solver", "mesh_size_mm", "n_nodes")},
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        in_dom = abs(design["D_mm"] - 560.0) < 0.05 and abs(design["Dc_mm"] - 175.0) < 0.05 and \
            design.get("material", "zerodur") == "zerodur"
        if in_dom:
            path = FEA_DATASET if source == "calculix" else FEA_DATASET.replace("isogrid_fea_dataset", "nx_nastran_results")
            with open(path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            get_surrogate(refresh=True)
        return {"stored": in_dom, "record_id": rec["id"]}
