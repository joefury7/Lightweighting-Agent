"""
Unseen Seeds Benchmark for NSGA-II
"""
import sys, os, time
import numpy as np

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from optimizer.closed_loop_optimizer import ClosedLoopOptimizer

def run_unseen():
    opt = ClosedLoopOptimizer()
    unseen_seeds = [501, 1024, 2048, 3141, 4096, 5555, 7777, 8888, 9999]

    print("="*88)
    print("   UNSEEN SEEDS VALIDATION BENCHMARK (9 NEW INDEPENDENT SEEDS)")
    print("   Settings: Pop=150, Gen=30")
    print("="*88)
    print(f"{'Run':<5} | {'Seed':<6} | {'Mass (kg)':<10} | {'Sag (nm)':<10} | {'Quilt (nm)':<11} | {'Feasible':<10} | {'All Constraints':<16} | {'Time (s)':<8}")
    print("-" * 88)

    results = []
    for i, seed in enumerate(unseen_seeds):
        np.random.seed(seed)
        t0 = time.time()
        res = opt.optimize_nsga2(D_mm=560.0, Dc_mm=120.0, max_mass_kg=12.0, max_sag_nm=60.0, pop_size=150, generations=30)
        dur = time.time() - t0
        m = res['predicted_mass_kg']
        s = res['predicted_rms_sag_nm']
        q = res['predicted_quilting_nm']
        fc = res['feasible_count']
        passed = res['all_constraints_satisfied']
        results.append({'run': i+1, 'seed': seed, 'mass': m, 'sag': s, 'quilt': q, 'feasible': fc, 'passed': passed, 'dur': dur})
        plabel = 'PASS [OK]' if passed else 'FAIL [X]'
        print(f"{i+1:<5} | {seed:<6} | {m:<10.3f} | {s:<10.2f} | {q:<11.2f} | {fc:<10} | {plabel:<16} | {dur:<8.2f}")

    passed_count = sum(1 for r in results if r['passed'])
    print("="*88)
    print(f"Summary: {passed_count}/9 Runs Fully Feasible ({passed_count/9*100:.1f}%)")
    print(f"Mean Mass:  {np.mean([r['mass'] for r in results]):.3f} kg (Std: {np.std([r['mass'] for r in results]):.3f})")
    print(f"Mean Sag:   {np.mean([r['sag'] for r in results]):.2f} nm (Std: {np.std([r['sag'] for r in results]):.2f})")
    print(f"Mean Quilt: {np.mean([r['quilt'] for r in results]):.2f} nm (Std: {np.std([r['quilt'] for r in results]):.2f})")
    print("="*88)

if __name__ == '__main__':
    run_unseen()
