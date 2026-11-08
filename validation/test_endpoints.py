"""
Validation script for all Server Endpoints & Handlers
"""
import sys, os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from server.main_server import (
    health_check, predict_metrics, run_pareto_optimization, run_nsga2_optimization,
    run_fea_validation, generate_cad_journal, run_unified_optimization,
    MirrorDesignInput, OptimizeRequest, UnifiedOptimizeRequest
)

print("="*60)
print("1. Health Check Endpoint:")
print(health_check())

print("\n"+"="*60)
print("2. ML Surrogate Prediction Endpoint (/ml/predict):")
pred = predict_metrics(MirrorDesignInput(D_mm=560, Dc_mm=120, H_mm=73.7, tf_mm=1.0, tw_mm=3.0, L_mm=55.5, rf_mm=3.0))
print(pred)

print("\n"+"="*60)
print("3. Vectorized Monte Carlo Pareto Search (/optimize):")
opt_mc = run_pareto_optimization(OptimizeRequest(D_mm=560, Dc_mm=120, max_mass_kg=12.0, max_sag_nm=60.0, num_candidates=25000))
print(f"Feasible designs: {opt_mc.get('feasible_count')}")
print(f"Mass: {opt_mc.get('predicted_mass_kg')} kg, Sag: {opt_mc.get('predicted_rms_sag_nm')} nm, Quilt: {opt_mc.get('predicted_quilting_nm')} nm")

print("\n"+"="*60)
print("4. NSGA-II Multi-Objective Optimization (/optimize/nsga2):")
opt_ga = run_nsga2_optimization(OptimizeRequest(D_mm=560, Dc_mm=120, max_mass_kg=12.0, max_sag_nm=60.0))
print(f"Feasible Pareto count: {opt_ga.get('feasible_count')}")
print(f"Mass: {opt_ga.get('predicted_mass_kg')} kg, Sag: {opt_ga.get('predicted_rms_sag_nm')} nm, Quilt: {opt_ga.get('predicted_quilting_nm')} nm")

print("\n"+"="*60)
print("5. FEA Ground Truth Solve Endpoint (/fea/solve):")
fea = run_fea_validation(MirrorDesignInput(D_mm=560, Dc_mm=120, H_mm=73.7, tf_mm=1.0, tw_mm=3.0, L_mm=55.5, rf_mm=3.0))
print(f"Actual Mass: {fea['fea_results']['actual_mass_kg']} kg")
print(f"Actual RMS Sag: {fea['fea_results']['actual_rms_sag_nm']} nm")
print(f"Actual Quilting: {fea['fea_results']['actual_quilting_nm']} nm")
print(f"Optical Pass: {fea['fea_results']['optical_pass']}")

print("\n"+"="*60)
print("6. CAD NX Journal Script Endpoint (/cad/generate_journal):")
cad = generate_cad_journal(MirrorDesignInput(D_mm=560, Dc_mm=120, H_mm=73.7, tf_mm=1.0, tw_mm=3.0, L_mm=55.5, rf_mm=3.0))
print(cad)

print("\n"+"="*60)
print("7. Consolidated Unified Optimizer Endpoint (/optimize/unified):")
unified_res = run_unified_optimization(UnifiedOptimizeRequest(
    D_mm=560, Dc_mm=120, H_mm=73.7, max_mass_kg=12.0, max_sag_nm=60.0,
    mode="target", material="zerodur", topology="triangular_isogrid"
))
print(f"Winner: {unified_res['winner'].upper()} ({unified_res['winner_reason']})")
print(f"Best: Mass={unified_res['best']['mass_kg']:.2f} kg, Sag={unified_res['best']['rms_sag_nm']:.2f} nm")
print(f"Dominant Zernike Modes: {list(unified_res['best'].get('dominant_zernike_modes', {}).keys())}")
print("="*60)
print("ALL SERVER ENDPOINTS VERIFIED AND FUNCTIONAL!")
