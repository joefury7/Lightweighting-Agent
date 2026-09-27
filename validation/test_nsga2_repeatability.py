"""
NSGA-II Multi-Seed Repeatability and Robustness Validation Suite
Runs 9 independent random seeds to benchmark convergence reliability and feasibility success rate.
"""

import sys, os
import numpy as np
import time

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from optimizer.closed_loop_optimizer import ClosedLoopOptimizer

def run_repeatability_sweep(num_seeds=9, pop_size=150, generations=30):
    print("="*80)
    print(f"   NSGA-II MULTI-SEED REPEATABILITY BENCHMARK ({num_seeds} INDEPENDENT RUNS)")
    print(f"   Settings: Population={pop_size}, Generations={generations}")
    print("="*80)

    opt = ClosedLoopOptimizer()
    results = []

    print(f"{'Run':<5} | {'Seed':<6} | {'Mass (kg)':<10} | {'Sag (nm)':<10} | {'Quilt (nm)':<11} | {'Feasible Count':<15} | {'All Constraints':<16} | {'Time (s)':<8}")
    print("-" * 88)

    for i in range(num_seeds):
        seed = 100 + i * 42
        np.random.seed(seed)
        
        t0 = time.time()
        res = opt.optimize_nsga2(
            D_mm=560.0, Dc_mm=120.0,
            max_mass_kg=12.0, max_sag_nm=60.0,
            pop_size=pop_size, generations=generations
        )
        duration = time.time() - t0

        mass = res["predicted_mass_kg"]
        sag = res["predicted_rms_sag_nm"]
        quilt = res["predicted_quilting_nm"]
        feas_count = res["feasible_count"]
        passed = res["all_constraints_satisfied"]

        results.append({
            "run": i + 1,
            "seed": seed,
            "mass_kg": mass,
            "sag_nm": sag,
            "quilt_nm": quilt,
            "feasible_count": feas_count,
            "passed": passed,
            "time_s": duration
        })

        pass_label = "PASS [OK]" if passed else "FAIL [X]"
        print(f"{i+1:<5} | {seed:<6} | {mass:<10.3f} | {sag:<10.2f} | {quilt:<11.2f} | {feas_count:<15} | {pass_label:<16} | {duration:<8.2f}")

    total_passed = sum(1 for r in results if r["passed"])
    pass_rate = (total_passed / num_seeds) * 100.0

    print("="*80)
    print(f"  Summary: {total_passed}/{num_seeds} Runs Fully Constraint-Satisfying ({pass_rate:.1f}% Success Rate)")
    print(f"  Mean Mass:    {np.mean([r['mass_kg'] for r in results]):.3f} kg (Std: {np.std([r['mass_kg'] for r in results]):.3f})")
    print(f"  Mean Sag:     {np.mean([r['sag_nm'] for r in results]):.2f} nm (Std: {np.std([r['sag_nm'] for r in results]):.2f})")
    print(f"  Mean Quilt:   {np.mean([r['quilt_nm'] for r in results]):.2f} nm (Std: {np.std([r['quilt_nm'] for r in results]):.2f})")
    print(f"  Avg Runtime:  {np.mean([r['time_s'] for r in results]):.2f} s per run")
    print("="*80)

if __name__ == "__main__":
    run_repeatability_sweep(num_seeds=9, pop_size=150, generations=30)
