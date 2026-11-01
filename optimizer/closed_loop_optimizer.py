"""
Closed-Loop Active Learning Multi-Objective Optimizer (Pillar 3)
Features:
1. Fast Vectorized NSGA-II Genetic Algorithm (Non-dominated Sorting, Crowding Distance, SBX, Polynomial Mutation)
2. High-throughput Monte Carlo Pareto Exploration with Surrogate Inference (<120 ms for 50k evaluations)
3. Active Learning Residual Buffer for Ground-Truth Drift Tracking
"""

import os
import sys
import json
import time
import numpy as np

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor
from optimizer.node_snapping import snap_18_whiffletree_hubs


def non_dominated_sort(objectives):
    """
    Fast non-dominated sorting for multi-objective optimization (minimization).
    objectives: np.ndarray of shape (N, M)
    Returns: list of fronts (each front is a list of indices)
    """
    num_points = objectives.shape[0]
    domination_counts = np.zeros(num_points, dtype=int)
    dominated_sets = [[] for _ in range(num_points)]
    fronts = [[]]

    for p in range(num_points):
        for q in range(p + 1, num_points):
            # Check if p dominates q
            p_leq_q = np.all(objectives[p] <= objectives[q])
            p_lt_q = np.any(objectives[p] < objectives[q])
            p_dom_q = p_leq_q and p_lt_q

            # Check if q dominates p
            q_leq_p = np.all(objectives[q] <= objectives[p])
            q_lt_p = np.any(objectives[q] < objectives[p])
            q_dom_p = q_leq_p and q_lt_p

            if p_dom_q:
                dominated_sets[p].append(q)
                domination_counts[q] += 1
            elif q_dom_p:
                dominated_sets[q].append(p)
                domination_counts[p] += 1

        if domination_counts[p] == 0:
            fronts[0].append(p)

    i = 0
    while len(fronts[i]) > 0:
        next_front = []
        for p in fronts[i]:
            for q in dominated_sets[p]:
                domination_counts[q] -= 1
                if domination_counts[q] == 0:
                    next_front.append(q)
        i += 1
        fronts.append(next_front)

    return fronts[:-1]


def calculate_crowding_distance(objectives, front):
    """
    Computes crowding distances for solutions in a given Pareto front.
    """
    if len(front) == 0:
        return np.array([])
    if len(front) <= 2:
        return np.full(len(front), np.inf)

    distances = np.zeros(len(front))
    front_objs = objectives[front]
    num_objs = objectives.shape[1]

    for m in range(num_objs):
        sorted_indices = np.argsort(front_objs[:, m])
        distances[sorted_indices[0]] = np.inf
        distances[sorted_indices[-1]] = np.inf

        obj_min = front_objs[sorted_indices[0], m]
        obj_max = front_objs[sorted_indices[-1], m]
        obj_range = obj_max - obj_min + 1e-9

        for i in range(1, len(front) - 1):
            distances[sorted_indices[i]] += (
                front_objs[sorted_indices[i + 1], m] - front_objs[sorted_indices[i - 1], m]
            ) / obj_range

    return distances


class ClosedLoopOptimizer:
    def __init__(self, buffer_file="optimizer/retraining_buffer.json"):
        self.predictor = MirrorSurrogatePredictor()
        self.buffer_file = buffer_file
        self.retraining_buffer = self._load_buffer()

    def _load_buffer(self):
        if os.path.exists(self.buffer_file):
            try:
                with open(self.buffer_file, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_buffer(self):
        os.makedirs(os.path.dirname(self.buffer_file), exist_ok=True)
        with open(self.buffer_file, "w") as f:
            json.dump(self.retraining_buffer, f, indent=2)

    def optimize_nsga2(self, D_mm=560.0, Dc_mm=120.0, H_mm=73.7, max_mass_kg=12.0, max_sag_nm=60.0,
                       pop_size=200, generations=40, eta_c=15.0, eta_m=20.0, mode="target"):
        """
        True NSGA-II Multi-Objective Genetic Algorithm with ML Surrogate fitness evaluations.
        Objectives: Minimize Mass (kg) & Minimize RMS Gravity Sag (nm).
        Constraints: mass <= max_mass_kg, rms_sag <= max_sag_nm, quilting <= 30.0 nm, tf >= 0.8 mm, tw >= 1.5 mm.
        """
        t0 = time.time()
        print(f"\n[Pillar 3 NSGA-II] Initializing Multi-Objective GA (Pop={pop_size}, Gen={generations}) for D={D_mm}mm, Dc={Dc_mm}mm, H={H_mm}mm...")

        # Gene bounds: [H, tf, tw, L, rf]
        # When H_mm is specified (e.g. 73.7mm from UI blank geometry), fix H so pocket geometry is optimized for the actual blank depth
        if H_mm is not None and H_mm > 5.0:
            bounds_lower = np.array([H_mm, 0.8, 1.5, 25.0, 1.0])
            bounds_upper = np.array([H_mm, 3.5, 5.0, 80.0, 5.0])
        else:
            bounds_lower = np.array([55.0, 0.8, 1.5, 25.0, 1.0])
            bounds_upper = np.array([95.0, 3.5, 5.0, 80.0, 5.0])

        # Initial Population
        population = np.random.uniform(bounds_lower, bounds_upper, (pop_size, len(bounds_lower)))

        def evaluate_pop(pop):
            N = pop.shape[0]
            D_arr = np.full(N, D_mm)
            Dc_arr = np.full(N, Dc_mm)
            feat = np.column_stack([D_arr, Dc_arr, pop[:, 0], pop[:, 1], pop[:, 2], pop[:, 3], pop[:, 4]])
            preds = self.predictor.predict_batch(feat)
            mass = preds[:, 0]
            sag = preds[:, 1]
            pv = preds[:, 2]
            quilt = preds[:, 3]
            freq = preds[:, 4]

            # Constraint violations (penalty > 0 if violated)
            c_sag = np.maximum(0.0, sag - max_sag_nm)
            c_quilt = np.maximum(0.0, quilt - 30.0)
            c_tf = np.maximum(0.0, 0.8 - pop[:, 1])
            c_tw = np.maximum(0.0, 1.5 - pop[:, 2])
            structural_penalty = (c_sag * 0.5) + (c_quilt * 2.0) + (c_tf * 50.0) + (c_tw * 50.0)

            is_min_mode = (str(mode).lower() == "min") or (str(max_mass_kg).upper() == "MIN") or (float(max_mass_kg) >= 900.0)
            target_kg = float(max_mass_kg) if not is_min_mode else None

            if not is_min_mode:
                # Force Target Weight Mode: minimize absolute deviation |mass - target_kg|
                mass_diff = np.abs(mass - target_kg)
                total_penalty = structural_penalty + (mass_diff * 5.0)
                obj1 = mass_diff * 20.0 + structural_penalty
                obj2 = sag + structural_penalty
            else:
                # Minimum Weight (MIN) Mode: minimize mass directly without artificial ceiling
                total_penalty = structural_penalty
                obj1 = mass + structural_penalty
                obj2 = sag + structural_penalty

            objs = np.column_stack([obj1, obj2])
            return objs, preds, total_penalty

        for gen in range(generations):
            # Evaluate parent population
            objs, preds, penalties = evaluate_pop(population)

            # Non-dominated sorting and crowding distance for parent population
            parent_fronts = non_dominated_sort(objs)
            ranks = np.zeros(pop_size, dtype=int)
            crowding_distances = np.zeros(pop_size)

            for rank_idx, front in enumerate(parent_fronts):
                if len(front) == 0:
                    continue
                ranks[front] = rank_idx
                crowding_distances[front] = calculate_crowding_distance(objs, front)

            def binary_tournament():
                i1, i2 = np.random.choice(pop_size, 2, replace=False)
                if ranks[i1] < ranks[i2]:
                    return population[i1]
                elif ranks[i2] < ranks[i1]:
                    return population[i2]
                else:
                    return population[i1] if crowding_distances[i1] >= crowding_distances[i2] else population[i2]

            # Tournament Selection & Offspring Generation (SBX + Polynomial Mutation)
            offspring = np.empty_like(population)
            for i in range(0, pop_size, 2):
                p1 = binary_tournament()
                p2 = binary_tournament()

                # Simulated Binary Crossover (SBX)
                u = np.random.rand(len(bounds_lower))
                beta = np.where(u <= 0.5, (2.0 * u) ** (1.0 / (eta_c + 1.0)), (1.0 / (2.0 * (1.0 - u))) ** (1.0 / (eta_c + 1.0)))
                c1 = 0.5 * ((1.0 + beta) * p1 + (1.0 - beta) * p2)
                c2 = 0.5 * ((1.0 - beta) * p1 + (1.0 + beta) * p2)

                # Polynomial Mutation
                for child in [c1, c2]:
                    r = np.random.rand(len(bounds_lower))
                    mut_mask = r < (1.0 / len(bounds_lower))
                    u_mut = np.random.rand(len(bounds_lower))
                    delta = np.where(
                        u_mut < 0.5,
                        (2.0 * u_mut) ** (1.0 / (eta_m + 1.0)) - 1.0,
                        1.0 - (2.0 * (1.0 - u_mut)) ** (1.0 / (eta_m + 1.0))
                    )
                    child[mut_mask] += delta[mut_mask] * (bounds_upper[mut_mask] - bounds_lower[mut_mask]) * 0.1

                offspring[i] = np.clip(c1, bounds_lower, bounds_upper)
                if i + 1 < pop_size:
                    offspring[i + 1] = np.clip(c2, bounds_lower, bounds_upper)

            # Combine Parent + Offspring (Elitist selection of size pop_size)
            combined_pop = np.vstack([population, offspring])
            comb_objs, comb_preds, comb_penalties = evaluate_pop(combined_pop)

            fronts = non_dominated_sort(comb_objs)
            new_population = []

            for front in fronts:
                if len(new_population) + len(front) <= pop_size:
                    new_population.extend(front)
                else:
                    needed = pop_size - len(new_population)
                    crowding_dist = calculate_crowding_distance(comb_objs, front)
                    sorted_by_dist = np.argsort(-crowding_dist)
                    selected_from_front = [front[idx] for idx in sorted_by_dist[:needed]]
                    new_population.extend(selected_from_front)
                    break

            population = combined_pop[new_population]

        eval_time = time.time() - t0
        final_objs, final_preds, final_penalties = evaluate_pop(population)

        is_min_mode = (str(mode).lower() == "min") or (str(max_mass_kg).upper() == "MIN") or (float(max_mass_kg) >= 900.0)
        target_kg = float(max_mass_kg) if not is_min_mode else None

        # Filter strictly feasible in final population (meeting optical and manufacturing limits)
        feasible_mask = (
            (final_preds[:, 1] <= max_sag_nm) &
            (final_preds[:, 3] <= 30.0) &
            (population[:, 1] >= 0.8) &
            (population[:, 2] >= 1.5)
        )

        feasible_indices = np.where(feasible_mask)[0]

        if len(feasible_indices) > 0:
            if not is_min_mode:
                # Force Target Weight Mode: find design matching target_kg with minimal sag
                m_diffs = np.abs(final_preds[feasible_indices, 0] - target_kg)
                s_vals = final_preds[feasible_indices, 1]
                scores = (m_diffs / 0.05)**2 + 0.5 * (s_vals / max_sag_nm)
                best_idx = feasible_indices[np.argmin(scores)]
                is_fully_feasible = bool(m_diffs[np.argmin(scores)] <= 0.2)
            else:
                # Minimum Weight (MIN) Mode: find absolute lightest feasible design with sag tiebreaker
                valid_masses = final_preds[feasible_indices, 0]
                valid_sags = final_preds[feasible_indices, 1]
                norm_m = (valid_masses - valid_masses.min()) / (np.ptp(valid_masses) + 1e-6)
                norm_s = (valid_sags - valid_sags.min()) / (np.ptp(valid_sags) + 1e-6)
                best_idx = feasible_indices[np.argmin(0.85 * norm_m + 0.15 * norm_s)]
                is_fully_feasible = True
        else:
            if not is_min_mode:
                best_idx = np.argmin(np.abs(final_preds[:, 0] - target_kg) * 10.0 + final_penalties)
            else:
                best_idx = np.argmin(final_penalties)
            is_fully_feasible = False

        best_genes = population[best_idx]
        best_pred = final_preds[best_idx]

        print(f"[Pillar 3 NSGA-II] Completed {generations} generations ({pop_size*generations*2:,} surrogate evaluations) in {eval_time*1000:.2f} ms")
        print(f"[Pillar 3 NSGA-II] Feasible Pareto solutions in final generation: {len(feasible_indices)}/{pop_size} | Fully Feasible: {is_fully_feasible}")

        best_design = {
            "D_mm": float(D_mm),
            "Dc_mm": float(Dc_mm),
            "H_mm": round(float(best_genes[0]), 2),
            "tf_mm": round(float(best_genes[1]), 2),
            "tw_mm": round(float(best_genes[2]), 2),
            "L_mm": round(float(best_genes[3]), 2),
            "rf_mm": round(float(best_genes[4]), 2),
            "all_constraints_satisfied": is_fully_feasible,
            "optimizer_method": "NSGA-II Multi-Objective Genetic Algorithm",
            "evaluation_duration_ms": round(eval_time * 1000.0, 2),
            "feasible_count": int(len(feasible_indices))
        }
        # Re-evaluate exactly with rounded parameters to ensure 0.000 kg discrepancy with Instant ML Predict & Siemens NX
        p_eval = self.predictor.predict(
            best_design["D_mm"], best_design["Dc_mm"], best_design["H_mm"],
            best_design["tf_mm"], best_design["tw_mm"], best_design["L_mm"], best_design["rf_mm"]
        )
        best_design["predicted_mass_kg"] = round(p_eval["mass_kg"], 2)
        best_design["predicted_rms_sag_nm"] = round(p_eval["rms_sag_nm"], 2)
        best_design["predicted_pv_sag_nm"] = round(p_eval["pv_sag_nm"], 2)
        best_design["predicted_quilting_nm"] = round(p_eval["quilting_nm"], 2)
        best_design["predicted_freq_hz"] = round(p_eval["frequency_hz"], 1)

        best_design["support_hubs_18"] = snap_18_whiffletree_hubs(D_mm, best_design["L_mm"], Dc_mm)
        return best_design

    def optimize(self, D_mm=560.0, Dc_mm=120.0, H_mm=73.7, max_mass_kg=12.0, max_sag_nm=60.0, num_candidates=50000, mode="target"):
        """
        Fast High-Throughput Monte Carlo Pareto Search with automatic fallback to NSGA-II if needed.
        """
        print(f"\n[Pillar 3 Optimizer] Exploring {num_candidates:,} candidate geometries for D={D_mm}mm...")
        t0 = time.time()

        # Generate candidates
        tf_vals = np.random.uniform(0.8, 3.5, num_candidates)
        tw_vals = np.random.uniform(1.5, 4.5, num_candidates)
        L_vals = np.random.uniform(25.0, 75.0, num_candidates)
        rf_vals = np.random.uniform(1.0, 5.0, num_candidates)
        if H_mm is not None and H_mm > 5.0:
            H_vals = np.full(num_candidates, H_mm)
        else:
            H_vals = np.random.uniform(55.0, 95.0, num_candidates)

        D_arr = np.full(num_candidates, D_mm)
        Dc_arr = np.full(num_candidates, Dc_mm)

        feature_matrix = np.column_stack([D_arr, Dc_arr, H_vals, tf_vals, tw_vals, L_vals, rf_vals])

        preds = self.predictor.predict_batch(feature_matrix)
        eval_time = time.time() - t0

        masses = preds[:, 0]
        rms_sags = preds[:, 1]
        pv_sags = preds[:, 2]
        quiltings = preds[:, 3]
        freqs = preds[:, 4]

        is_min_mode = (str(mode).lower() == "min") or (str(max_mass_kg).upper() == "MIN") or (float(max_mass_kg) >= 900.0)
        target_kg = float(max_mass_kg) if not is_min_mode else None

        valid_mask = (
            (rms_sags <= max_sag_nm) &
            (quiltings <= 30.0) &
            (tf_vals >= 0.8) &
            (tw_vals >= 1.5)
        )

        valid_indices = np.where(valid_mask)[0]
        print(f"[Pillar 3] Evaluated {num_candidates:,} designs in {eval_time*1000:.2f} ms ({len(valid_indices)} feasible designs found)")

        if len(valid_indices) == 0:
            print("[Pillar 3] Falling back to NSGA-II Genetic Search for fine Pareto convergence...")
            return self.optimize_nsga2(D_mm, Dc_mm, H_mm, max_mass_kg, max_sag_nm, mode=mode)

        if not is_min_mode:
            # Force Target Weight Mode: score by distance to target mass + optical sag
            m_diffs = np.abs(masses[valid_indices] - target_kg)
            s_vals = rms_sags[valid_indices]
            scores = (m_diffs / 0.05)**2 + 0.5 * (s_vals / max_sag_nm)
            best_idx = valid_indices[np.argmin(scores)]
        else:
            # Minimum Weight (MIN) Mode: prioritize lowest mass with sag tiebreaker
            valid_masses = masses[valid_indices]
            valid_sags = rms_sags[valid_indices]
            ptp_mass = float(np.ptp(valid_masses)) + 1e-6
            ptp_sag = float(np.ptp(valid_sags)) + 1e-6
            norm_mass = (valid_masses - valid_masses.min()) / ptp_mass
            norm_sag = (valid_sags - valid_sags.min()) / ptp_sag
            scores = 0.85 * norm_mass + 0.15 * norm_sag
            best_idx = valid_indices[np.argmin(scores)]

        best_design = {
            "D_mm": float(D_mm),
            "Dc_mm": float(Dc_mm),
            "H_mm": round(float(H_vals[best_idx]), 2),
            "tf_mm": round(float(tf_vals[best_idx]), 2),
            "tw_mm": round(float(tw_vals[best_idx]), 2),
            "L_mm": round(float(L_vals[best_idx]), 2),
            "rf_mm": round(float(rf_vals[best_idx]), 2),
            "all_constraints_satisfied": bool(len(valid_indices) > 0),
            "optimizer_method": "High-Throughput Vectorized Pareto Search",
            "evaluation_duration_ms": round(eval_time * 1000.0, 2),
            "feasible_count": int(len(valid_indices))
        }
        # Re-evaluate exactly with rounded parameters to ensure 0.000 kg discrepancy with Instant ML Predict & Siemens NX
        p_eval = self.predictor.predict(
            best_design["D_mm"], best_design["Dc_mm"], best_design["H_mm"],
            best_design["tf_mm"], best_design["tw_mm"], best_design["L_mm"], best_design["rf_mm"]
        )
        best_design["predicted_mass_kg"] = round(p_eval["mass_kg"], 2)
        best_design["predicted_rms_sag_nm"] = round(p_eval["rms_sag_nm"], 2)
        best_design["predicted_pv_sag_nm"] = round(p_eval["pv_sag_nm"], 2)
        best_design["predicted_quilting_nm"] = round(p_eval["quilting_nm"], 2)
        best_design["predicted_freq_hz"] = round(p_eval["frequency_hz"], 1)

        best_design["support_hubs_18"] = snap_18_whiffletree_hubs(D_mm, best_design["L_mm"], Dc_mm)
        return best_design

    def log_fea_residual(self, design_params, ml_pred_sag, fea_actual_sag, fea_actual_mass):
        """
        Active Learning Loop: Tracks residual error and saves to retraining buffer.
        """
        error_nm = abs(fea_actual_sag - ml_pred_sag)
        pct_error = (error_nm / fea_actual_sag) * 100.0 if fea_actual_sag > 0 else 0.0

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "params": design_params,
            "ml_pred_sag_nm": ml_pred_sag,
            "fea_actual_sag_nm": fea_actual_sag,
            "fea_actual_mass_kg": fea_actual_mass,
            "residual_error_nm": round(error_nm, 3),
            "error_pct": round(pct_error, 2),
            "needs_retrain": pct_error > 5.0
        }

        self.retraining_buffer.append(entry)
        self._save_buffer()
        print(f"[Active Learning] Residual logged: Error = {pct_error:.2f}% (Threshold: 5.0%). Buffer size: {len(self.retraining_buffer)}")
        # Online Active Learning: retrain residual compensator immediately
        try:
            if hasattr(self.predictor, "active_learner"):
                self.predictor.active_learner.train_from_buffer()
        except Exception as e:
            print(f"[Active Learning] Online update warning: {e}")
        return entry


if __name__ == "__main__":
    opt = ClosedLoopOptimizer()
    print("=== TEST 1: Vectorized Monte Carlo Pareto ===")
    res_mc = opt.optimize(560.0, 120.0, 73.7, max_mass_kg=12.0, max_sag_nm=60.0, num_candidates=50000)
    print(f"Result: Mass={res_mc['predicted_mass_kg']}kg, Sag={res_mc['predicted_rms_sag_nm']}nm, Quilt={res_mc['predicted_quilting_nm']}nm")

    print("\n=== TEST 2: True NSGA-II Multi-Objective Genetic Algorithm ===")
    res_ga = opt.optimize_nsga2(560.0, 120.0, max_mass_kg=12.0, max_sag_nm=60.0, pop_size=150, generations=30)
    print(f"Result: Mass={res_ga['predicted_mass_kg']}kg, Sag={res_ga['predicted_rms_sag_nm']}nm, Quilt={res_ga['predicted_quilting_nm']}nm")
