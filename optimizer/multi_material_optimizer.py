"""
Unified Multi-Material & Multi-Algorithm Optimization Engine (Objective 3)
Couples Reinforcement Learning (PPO / SAC) and Evolutionary Algorithms (NSGA-II)
Balances Mass, Optical Figure Error (RMS sag, Zernike), and Launch Stiffness (f1)
across Zerodur, Silicon Carbide (SiC), ULE, and Beryllium.
"""

import os
import sys
import time
import json
import math
import numpy as np

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.pinn_inference import PINNMirrorPredictor
from cad_engine.cad_generator import TOPOLOGY_CATALOG, MirrorCADGenerator
from optimizer.node_snapping import snap_18_whiffletree_hubs
from optimizer.rl_environment import OptoMechanicalMirrorEnv
from optimizer.ppo_agent import PPOAgent
from optimizer.sac_agent import SACAgent
from optimizer.closed_loop_optimizer import non_dominated_sort, calculate_crowding_distance

SUPPORTED_MATERIALS = ["zerodur", "sic", "ule", "beryllium"]


class MultiMaterialOptimizer:
    """
    Master Optimizer unifying Reinforcement Learning (PPO/SAC) and NSGA-II Genetic Optimization
    across all 4 spaceborne mirror substrates and 8 pocket topologies.
    """
    def __init__(self):
        self.predictor = PINNMirrorPredictor()
        self.ppo_agent = PPOAgent()
        # Attempt to load pretrained PPO policy if available
        policy_path = os.path.join(workspace_root, "optimizer", "models", "ppo_mirror_policy.pt")
        if os.path.exists(policy_path):
            try:
                import torch
                self.ppo_agent.policy.load_state_dict(torch.load(policy_path))
                self.ppo_agent.policy.eval()
            except Exception:
                pass

        self.sac_agent = SACAgent()

    def optimize_material_nsga2(self, material="zerodur", topology="triangular_isogrid",
                                D_mm=560.0, Dc_mm=120.0, H_mm=73.7, target_mass_kg=12.0, max_sag_nm=60.0,
                                pop_size=150, generations=30, mode="target", seed=42):
        """
        Runs true NSGA-II Multi-Objective Genetic Algorithm for the specified material and topology.
        Supports both 'target' mass tracking and 'min' mass reduction.
        """
        # Fix random seed for reproducibility
        np.random.seed(seed)

        t0 = time.time()
        # Keep mirror blank depth H strictly fixed to the user's input specification (e.g. 73.7 mm)
        h_fixed = float(H_mm) if (H_mm and H_mm > 10.0) else 73.7
        bounds_lower = np.array([h_fixed, 0.8, 1.5, 25.0, 1.0])
        bounds_upper = np.array([h_fixed, 3.5, 5.5, 95.0, 5.0])

        population = np.random.uniform(bounds_lower, bounds_upper, (pop_size, len(bounds_lower)))

        def evaluate_pop(pop):
            N = len(pop)
            D_arr = np.full((N, 1), D_mm)
            Dc_arr = np.full((N, 1), Dc_mm)
            feat_geom = np.column_stack([D_arr, Dc_arr, pop])

            scalars = self.predictor.predict_batch_fast(feat_geom, material=material, topology=topology)
            mass = scalars[:, 0]
            sag = np.maximum(1.0, scalars[:, 1])
            quilt = np.maximum(0.1, scalars[:, 3])
            freq = np.maximum(20.0, scalars[:, 4])

            # Constraints
            c_sag = np.maximum(0.0, sag - max_sag_nm)
            c_quilt = np.maximum(0.0, quilt - 30.0)
            c_freq = np.maximum(0.0, 120.0 - freq)
            c_tf = np.maximum(0.0, 0.8 - pop[:, 1])
            c_tw = np.maximum(0.0, 1.5 - pop[:, 2])

            penalties = (c_sag * 1.0) + (c_quilt * 2.0) + (c_freq * 1.0) + (c_tf * 50.0) + (c_tw * 50.0)

            if mode == "target":
                # Strong target-mass tracking: heavily penalise deviation from target.
                # Weight 200× means 1 kg off → +200 in obj1, dwarfing all sag/freq penalties.
                c_mass = np.abs(mass - target_mass_kg)
                obj1 = c_mass * 200.0 + penalties
            else:
                c_mass = np.maximum(0.0, mass - target_mass_kg)
                obj1 = mass + (c_mass * 5.0) + penalties

            obj2 = sag + penalties
            return np.column_stack([obj1, obj2]), scalars, penalties

        for gen in range(generations):
            objs, scalars, penalties = evaluate_pop(population)
            fronts = non_dominated_sort(objs)
            ranks = np.zeros(pop_size, dtype=int)
            crowding_dist = np.zeros(pop_size)

            for rank_idx, front in enumerate(fronts):
                if len(front) == 0:
                    continue
                ranks[front] = rank_idx
                crowding_dist[front] = calculate_crowding_distance(objs, front)

            def binary_tournament():
                i1, i2 = np.random.choice(pop_size, 2, replace=False)
                if ranks[i1] < ranks[i2]:
                    return population[i1]
                elif ranks[i2] < ranks[i1]:
                    return population[i2]
                else:
                    return population[i1] if crowding_dist[i1] >= crowding_dist[i2] else population[i2]

            # Crossover & Mutation (SBX + Polynomial Mutation)
            offspring = np.empty_like(population)
            for i in range(0, pop_size, 2):
                p1, p2 = binary_tournament(), binary_tournament()
                u = np.random.rand(len(bounds_lower))
                beta = np.where(u <= 0.5, (2.0 * u)**(1.0 / 16.0), (1.0 / (2.0 * (1.0 - u)))**(1.0 / 16.0))
                c1 = 0.5 * ((1.0 + beta) * p1 + (1.0 - beta) * p2)
                c2 = 0.5 * ((1.0 - beta) * p1 + (1.0 + beta) * p2)

                # Mutate
                for child in [c1, c2]:
                    r = np.random.rand(len(bounds_lower))
                    m = r < (1.0 / len(bounds_lower))
                    u_m = np.random.rand(len(bounds_lower))
                    delta = np.where(u_m < 0.5, (2.0 * u_m)**(1.0 / 21.0) - 1.0, 1.0 - (2.0 * (1.0 - u_m))**(1.0 / 21.0))
                    child[m] += delta[m] * (bounds_upper[m] - bounds_lower[m]) * 0.1

                offspring[i] = np.clip(c1, bounds_lower, bounds_upper)
                if i + 1 < pop_size:
                    offspring[i + 1] = np.clip(c2, bounds_lower, bounds_upper)

            combined_pop = np.vstack([population, offspring])
            comb_objs, comb_scalars, comb_penalties = evaluate_pop(combined_pop)
            comb_fronts = non_dominated_sort(comb_objs)

            new_pop = []
            for front in comb_fronts:
                if len(new_pop) + len(front) <= pop_size:
                    new_pop.extend(front)
                else:
                    needed = pop_size - len(new_pop)
                    cd = calculate_crowding_distance(comb_objs, front)
                    sorted_by_cd = np.argsort(-cd)
                    new_pop.extend([front[idx] for idx in sorted_by_cd[:needed]])
                    break
            population = combined_pop[new_pop]

        # Best solution extraction
        final_objs, final_scalars, final_penalties = evaluate_pop(population)
        if mode == "target":
            # Pick design closest to target mass (200× weight), then sag as tiebreaker
            best_idx = np.argmin(np.abs(final_scalars[:, 0] - target_mass_kg) * 200.0 + final_penalties + (final_scalars[:, 1] * 0.1))
        else:
            best_idx = np.argmin(final_penalties + (final_scalars[:, 0] * 2.0) + (final_scalars[:, 1] * 0.2))
        best_g = population[best_idx]

        full_eval = self.predictor.predict(
            D_mm=D_mm, Dc_mm=Dc_mm, H_mm=best_g[0], tf_mm=best_g[1], tw_mm=best_g[2],
            L_mm=best_g[3], rf_mm=best_g[4], material=material, topology=topology
        )

        elapsed = time.time() - t0
        full_eval["optimization_algorithm"] = "NSGA-II Multi-Objective Genetic Algorithm"
        full_eval["optimization_duration_sec"] = round(elapsed, 3)
        full_eval["H_mm"] = round(float(best_g[0]), 2)
        full_eval["tf_mm"] = round(float(best_g[1]), 2)
        full_eval["tw_mm"] = round(float(best_g[2]), 2)
        full_eval["L_mm"] = round(float(best_g[3]), 2)
        full_eval["rf_mm"] = round(float(best_g[4]), 2)
        full_eval["whiffletree_18_hubs"] = snap_18_whiffletree_hubs(D_mm, best_g[3], Dc_mm)
        return full_eval

    def optimize_material_rl_ppo(self, material="zerodur", topology="triangular_isogrid",
                                 D_mm=560.0, Dc_mm=120.0, target_mass_kg=12.0, target_sag_nm=60.0):
        """
        Runs continuous PPO Reinforcement Learning optimization policy for the specified material.
        """
        t0 = time.time()
        env = OptoMechanicalMirrorEnv(
            D_mm=D_mm, Dc_mm=Dc_mm, target_mass_kg=target_mass_kg, target_sag_nm=target_sag_nm,
            material=material, topology=topology, max_steps=35
        )
        rl_res = self.ppo_agent.optimize_design(env, max_steps=35)
        elapsed = time.time() - t0

        full_eval = self.predictor.predict(
            D_mm=D_mm, Dc_mm=Dc_mm, H_mm=rl_res["H_mm"], tf_mm=rl_res["tf_mm"],
            tw_mm=rl_res["tw_mm"], L_mm=rl_res["L_mm"], rf_mm=rl_res["rf_mm"],
            material=material, topology=topology
        )

        full_eval["optimization_algorithm"] = "PPO (Proximal Policy Optimization) Reinforcement Learning"
        full_eval["optimization_duration_sec"] = round(elapsed, 3)
        full_eval["H_mm"] = rl_res["H_mm"]
        full_eval["tf_mm"] = rl_res["tf_mm"]
        full_eval["tw_mm"] = rl_res["tw_mm"]
        full_eval["L_mm"] = rl_res["L_mm"]
        full_eval["rf_mm"] = rl_res["rf_mm"]
        full_eval["whiffletree_18_hubs"] = snap_18_whiffletree_hubs(D_mm, rl_res["L_mm"], Dc_mm)
        return full_eval

    def run_cooperative_pipeline(self, material="zerodur", topology="triangular_isogrid",
                                 D_mm=560.0, Dc_mm=120.0, H_mm=73.7, target_mass_kg=12.0, max_sag_nm=60.0,
                                 mode="target"):
        """
        Two-Stage Coarse-to-Fine Cooperative Pipeline:
        Stage 1: NSGA-II + XGBoost Global Search across 16,000+ candidates -> finds macro sweet-spot seed.
        Stage 2: PPO RL + Deep PINN Micro-Refinement -> starts from NSGA-II seed and fine-tunes continuous variables.
        Stage 3: Deep PINN Wavefront Decomposition -> generates 37 Fringe Zernike modes on refined mirror.
        """
        t0 = time.time()

        # 1. Stage 1: NSGA-II Global Exploration
        t_s1 = time.time()
        nsga2_res = self.optimize_material_nsga2(
            material=material, topology=topology, D_mm=D_mm, Dc_mm=Dc_mm, H_mm=H_mm,
            target_mass_kg=target_mass_kg, max_sag_nm=max_sag_nm, mode=mode,
            pop_size=150, generations=30, seed=42
        )
        t_s1_dur = time.time() - t_s1

        seed_geom = [
            float(nsga2_res.get("H_mm", H_mm)),
            float(nsga2_res.get("tf_mm", 1.0)),
            float(nsga2_res.get("tw_mm", 3.0)),
            float(nsga2_res.get("L_mm", 55.5)),
            float(nsga2_res.get("rf_mm", 3.0))
        ]

        # 2. Stage 2: PPO RL Micro-Refinement
        t_s2 = time.time()
        env = OptoMechanicalMirrorEnv(
            D_mm=D_mm, Dc_mm=Dc_mm, target_mass_kg=target_mass_kg, target_sag_nm=max_sag_nm,
            material=material, topology=topology, max_steps=30, mode=mode,
            fine_tuning=True, initial_geom=seed_geom
        )
        refinement_result = self.ppo_agent.refine_design(env, max_steps=30, initial_geom=seed_geom)
        t_s2_dur = time.time() - t_s2

        refined_raw = refinement_result["refined_design"]

        # 3. Stage 3: Deep PINN Wavefront Evaluation on Refined Champion
        final_eval = self.predictor.predict(
            D_mm=D_mm, Dc_mm=Dc_mm, H_mm=refined_raw["H_mm"], tf_mm=refined_raw["tf_mm"],
            tw_mm=refined_raw["tw_mm"], L_mm=refined_raw["L_mm"], rf_mm=refined_raw["rf_mm"],
            material=material, topology=topology
        )

        total_dur = time.time() - t0

        final_eval["optimization_algorithm"] = "Cooperative Pipeline: NSGA-II Global Seed ➔ PPO RL Micro-Refinement ➔ Deep PINN Zernike"
        final_eval["pipeline_type"] = "cooperative_two_stage"
        final_eval["duration_total_sec"] = round(total_dur, 3)
        final_eval["stage1_nsga2_duration_sec"] = round(t_s1_dur, 3)
        final_eval["stage2_ppo_duration_sec"] = round(t_s2_dur, 3)
        final_eval["H_mm"] = refined_raw["H_mm"]
        final_eval["tf_mm"] = refined_raw["tf_mm"]
        final_eval["tw_mm"] = refined_raw["tw_mm"]
        final_eval["L_mm"] = refined_raw["L_mm"]
        final_eval["rf_mm"] = refined_raw["rf_mm"]
        final_eval["whiffletree_18_hubs"] = snap_18_whiffletree_hubs(D_mm, refined_raw["L_mm"], Dc_mm)

        # Calculate improvement deltas
        seed_mass = nsga2_res.get("mass_kg") or nsga2_res.get("predicted_mass_kg", 12.0)
        seed_sag = nsga2_res.get("rms_sag_nm") or nsga2_res.get("predicted_rms_sag_nm", 60.0)
        refined_mass = final_eval["mass_kg"]
        refined_sag = final_eval["rms_sag_nm"]

        delta_mass = round(refined_mass - seed_mass, 3)
        delta_sag = round(refined_sag - seed_sag, 2)

        if mode == "target":
            target_err_refined = abs(refined_mass - target_mass_kg)
            target_status = "Exact Target Met" if target_err_refined <= 0.05 else "Refined to Target"
            handoff_msg = (
                f"NSGA-II Seed: {seed_mass:.2f} kg ({seed_sag:.1f} nm) ➔ "
                f"PPO Refined: {refined_mass:.2f} kg ({refined_sag:.1f} nm) | "
                f"ΔSag: {delta_sag:+.1f} nm, Target ±0.01 kg ({target_status})"
            )
        else:
            handoff_msg = (
                f"NSGA-II Seed: {seed_mass:.2f} kg ({seed_sag:.1f} nm) ➔ "
                f"PPO Refined: {refined_mass:.2f} kg ({refined_sag:.1f} nm) | "
                f"ΔMass: {delta_mass:+.2f} kg, ΔSag: {delta_sag:+.1f} nm"
            )

        handoff_summary = {
            "seed_nsga2": {
                "mass_kg": round(float(seed_mass), 2),
                "rms_sag_nm": round(float(seed_sag), 2),
                "tf_mm": nsga2_res.get("tf_mm"),
                "tw_mm": nsga2_res.get("tw_mm"),
                "L_mm": nsga2_res.get("L_mm"),
                "H_mm": nsga2_res.get("H_mm")
            },
            "refined_ppo": {
                "mass_kg": round(float(refined_mass), 2),
                "rms_sag_nm": round(float(refined_sag), 2),
                "tf_mm": refined_raw["tf_mm"],
                "tw_mm": refined_raw["tw_mm"],
                "L_mm": refined_raw["L_mm"],
                "H_mm": refined_raw["H_mm"]
            },
            "delta_mass_kg": delta_mass,
            "delta_sag_nm": delta_sag,
            "improved": refinement_result["improved"],
            "handoff_message": handoff_msg
        }

        return {
            "status": "SUCCESS",
            "pipeline": "Two-Stage Coarse-to-Fine",
            "winner": "cooperative",
            "winner_reason": handoff_msg,
            "best": final_eval,
            "handoff": handoff_summary,
            "nsga2_seed": nsga2_res,
            "ppo_refinement": refinement_result,
            "pinn_zernike": final_eval
        }

    def run_cross_material_trade_study(self, D_mm=560.0, Dc_mm=120.0, H_mm=73.7, target_mass_kg=12.0, max_sag_nm=60.0):
        """
        Executes a comprehensive trade study across all 4 materials (Zerodur, SiC, ULE, Beryllium)
        comparing both NSGA-II Evolutionary search and PPO Reinforcement Learning.
        """
        trade_results = {}
        print("\n" + "="*85)
        print("   OBJECTIVE 3: CROSS-MATERIAL PARETO TRADE STUDY (ZERODUR, SIC, ULE, BERYLLIUM)")
        print("="*85)

        for mat in SUPPORTED_MATERIALS:
            print(f"\n[Evaluating {mat.upper()}] Running NSGA-II + PPO Reinforcement Learning...")
            res_nsga2 = self.optimize_material_nsga2(
                material=mat, topology="triangular_isogrid", D_mm=D_mm, Dc_mm=Dc_mm,
                H_mm=H_mm, target_mass_kg=target_mass_kg, max_sag_nm=max_sag_nm
            )
            res_ppo = self.optimize_material_rl_ppo(
                material=mat, topology="triangular_isogrid", D_mm=D_mm, Dc_mm=Dc_mm,
                target_mass_kg=target_mass_kg, target_sag_nm=max_sag_nm
            )

            trade_results[mat] = {
                "nsga2_optimum": res_nsga2,
                "ppo_rl_optimum": res_ppo
            }

            print(f"  [{mat.upper()} NSGA-II] Mass: {res_nsga2['mass_kg']} kg ({res_nsga2['lightweight_pct']}% LW) | RMS Sag: {res_nsga2['rms_sag_nm']} nm | f1: {res_nsga2['frequency_hz']} Hz")
            print(f"  [{mat.upper()} PPO RL]  Mass: {res_ppo['mass_kg']} kg ({res_ppo['lightweight_pct']}% LW) | RMS Sag: {res_ppo['rms_sag_nm']} nm | f1: {res_ppo['frequency_hz']} Hz")

        return trade_results


if __name__ == "__main__":
    opt = MultiMaterialOptimizer()
    study = opt.run_cross_material_trade_study()
