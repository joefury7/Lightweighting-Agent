"""
Multi-material optimisation (Objective 3): NSGA-II global search + optional PPO local refinement,
both scored by the same evaluator (exact NX-journal mass, FEA-trained sag surrogate).

Materials: Zerodur, ULE, SiC, Beryllium.  For a fixed geometry the gravity deflection scales with
rho/E (see ml_engine/fea_surrogate.py); mass uses each material's density exactly.
Only the triangular isogrid has FEA training data, so other topologies are rejected explicitly
instead of being given made-up predictions.  (SAC was removed: it never had training code.)
"""
import os
import sys
import time

import numpy as np

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from optimizer.closed_loop_optimizer import ClosedLoopOptimizer  # noqa: E402
from optimizer.rl_environment import OptoMechanicalMirrorEnv  # noqa: E402
from optimizer.ppo_agent import PPOAgent  # noqa: E402
from optimizer.node_snapping import snap_18_whiffletree_hubs  # noqa: E402

SUPPORTED_MATERIALS = ["zerodur", "sic", "ule", "beryllium"]


def _check_topology(topology):
    if topology not in (None, "triangular_isogrid", "isogrid"):
        raise ValueError(f"No FEA data for topology '{topology}'. Only triangular isogrid is supported "
                         "for sag prediction; run FEA for other topologies before optimising them.")


class MultiMaterialOptimizer:
    def __init__(self):
        self.nsga = ClosedLoopOptimizer()
        self.predictor = self.nsga.predictor
        self.ppo_agent = PPOAgent()
        self.ppo_trained = False
        policy_path = os.path.join(workspace_root, "optimizer", "models", "ppo_mirror_policy.pt")
        report = os.path.join(workspace_root, "optimizer", "models", "ppo_training_report.json")
        if os.path.exists(policy_path) and os.path.exists(report):   # only policies trained on the current evaluator
            import torch
            self.ppo_agent.policy.load_state_dict(torch.load(policy_path))
            self.ppo_agent.policy.eval()
            self.ppo_trained = True

    def optimize_material_nsga2(self, material="zerodur", topology="triangular_isogrid", D_mm=560.0, Dc_mm=175.0,
                                H_mm=73.7, target_mass_kg=12.0, max_sag_nm=60.0, mode="target", seed=42, **_):
        _check_topology(topology)
        r = self.nsga.optimize_nsga2(D_mm, Dc_mm, H_mm, target_mass_kg, max_sag_nm, mode=mode,
                                     material=material, seed=seed)
        r["optimization_algorithm"] = r["optimizer_method"]
        r["whiffletree_18_hubs"] = r["support_hubs_18"]
        return r

    def optimize_material_rl_ppo(self, material="zerodur", topology="triangular_isogrid", D_mm=560.0, Dc_mm=175.0,
                                 target_mass_kg=12.0, target_sag_nm=60.0, H_mm=73.7, **_):
        """PPO refinement starting from the NSGA-II optimum (PPO alone is not a global optimiser)."""
        coop = self.run_cooperative_pipeline(material=material, topology=topology, D_mm=D_mm, Dc_mm=Dc_mm,
                                             H_mm=H_mm, target_mass_kg=target_mass_kg, max_sag_nm=target_sag_nm)
        return coop["best"]

    def run_cooperative_pipeline(self, material="zerodur", topology="triangular_isogrid", D_mm=560.0, Dc_mm=175.0,
                                 H_mm=73.7, target_mass_kg=12.0, max_sag_nm=60.0, mode="target"):
        _check_topology(topology)
        t0 = time.time()
        seed = self.optimize_material_nsga2(material, topology, D_mm, Dc_mm, H_mm, target_mass_kg, max_sag_nm, mode)
        t1 = time.time()
        refinement = {"improved": False, "note": "PPO policy not trained on the current evaluator - skipped"}
        best_geom = [seed["H_mm"], seed["tf_mm"], seed["tw_mm"], seed["L_mm"], seed["rf_mm"]]
        if self.ppo_trained:
            env = OptoMechanicalMirrorEnv(D_mm=D_mm, Dc_mm=Dc_mm, target_mass_kg=target_mass_kg,
                                          target_sag_nm=max_sag_nm, material=material, mode=mode,
                                          fine_tuning=True, initial_geom=best_geom, max_steps=30)
            refinement = self.ppo_agent.refine_design(env, max_steps=30, initial_geom=best_geom)
            if refinement["improved"]:
                rd = refinement["refined_design"]
                best_geom = [rd["H_mm"], rd["tf_mm"], rd["tw_mm"], rd["L_mm"], rd["rf_mm"]]
        H, tf, tw, L, rf = best_geom
        final = self.predictor.predict(D_mm, Dc_mm, H, tf, tw, L, rf, material=material, max_sag_nm=max_sag_nm)
        z = final["zernike_fringe_37_nm"]
        final["dominant_zernike_modes"] = {"Z4_Defocus_nm": round(z[3], 3), "Z9_Primary_Spherical_nm": round(z[8], 3),
                                           "Z10_Primary_Trefoil_3Fold_nm": round(z[9], 3),
                                           "Z37_Hexafoil_6Fold_Whiffletree_nm": round(z[36], 3)}
        final.update({"H_mm": H, "tf_mm": tf, "tw_mm": tw, "L_mm": L, "rf_mm": rf, "material": material,
                      "D_mm": D_mm, "Dc_mm": Dc_mm, "topology": "triangular_isogrid",
                      "whiffletree_18_hubs": snap_18_whiffletree_hubs(D_mm, L, Dc_mm),
                      "optimization_algorithm": "NSGA-II" + (" + PPO refinement" if refinement.get("improved") else "")})
        msg = (f"NSGA-II: {seed['mass_kg']:.3f} kg / {seed['rms_sag_nm']:.2f} nm"
               + (f" -> PPO: {final['mass_kg']:.3f} kg / {final['rms_sag_nm']:.2f} nm" if refinement.get("improved")
                  else " (PPO did not improve the seed; seed kept)" if self.ppo_trained else ""))
        return {
            "status": "SUCCESS", "pipeline": "NSGA-II global search -> PPO local refinement (accepted only if better)",
            "winner": "cooperative" if refinement.get("improved") else "nsga2",
            "winner_reason": msg, "best": final,
            "handoff": {"seed_nsga2": {k: seed[k] for k in ("mass_kg", "rms_sag_nm", "tf_mm", "tw_mm", "L_mm", "H_mm")},
                        "refined_ppo": {k: final[k] for k in ("mass_kg", "rms_sag_nm", "tf_mm", "tw_mm", "L_mm", "H_mm")},
                        "improved": bool(refinement.get("improved")), "handoff_message": msg},
            "nsga2_seed": seed, "ppo_refinement": refinement, "pinn_zernike": final,
            "duration_total_sec": round(time.time() - t0, 2), "stage1_nsga2_duration_sec": round(t1 - t0, 2),
        }

    def run_cross_material_trade_study(self, D_mm=560.0, Dc_mm=175.0, H_mm=73.7, target_mass_kg=12.0, max_sag_nm=60.0):
        return {m: {"nsga2_optimum": self.optimize_material_nsga2(m, "triangular_isogrid", D_mm, Dc_mm, H_mm,
                                                                  target_mass_kg, max_sag_nm)}
                for m in SUPPORTED_MATERIALS}
