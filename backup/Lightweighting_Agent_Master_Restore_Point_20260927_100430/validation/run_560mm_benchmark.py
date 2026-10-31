"""
End-to-End Validation Suite on the 560mm Zerodur Benchmark (Phase 7)
Evaluates full 4-Pillar pipeline performance, inference latency, NSGA-II optimization, and NASTRAN convergence.
"""

import os
import sys
import json
import time

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from server.agent_orchestrator import OptoMechanicalAgent

def run_benchmark():
    print("="*80)
    print("      560MM ZERODUR PRIMARY MIRROR OPTOMECHANICAL BENCHMARK (PHASE 7)")
    print("="*80)
    
    agent = OptoMechanicalAgent()
    prompt = "Design and optimize a 560mm clear aperture Zerodur mirror (Dc=120mm, H=73.7mm) to mass <= 12.0kg and sag <= 60.0nm."
    
    start_time = time.time()
    result = agent.run_agent_workflow(prompt)
    total_duration = time.time() - start_time

    best = result["pareto_best_design"]
    fea = result["fea_verification"]
    residual = result["active_learning"]

    print("\n" + "="*80)
    print("                          BENCHMARK AUDIT REPORT")
    print("="*80)
    print(f"  Total End-to-End Time:       {total_duration:.3f} s")
    print(f"  Optimizer Strategy:          {best.get('optimizer_method', 'Pareto Frontier Search')}")
    print(f"  Recommended Height (H):      {best['H_mm']} mm")
    print(f"  Recommended Faceplate (tf):  {best['tf_mm']} mm")
    print(f"  Recommended Rib (tw):        {best['tw_mm']} mm")
    print(f"  Recommended Cell Size (L):   {best['L_mm']} mm")
    print(f"  Recommended Fillet (rf):     {best['rf_mm']} mm")
    print(f"  ML Predicted Mass:           {best['predicted_mass_kg']} kg")
    print(f"  ML Predicted Sag:            {best['predicted_rms_sag_nm']} nm")
    print(f"  ML Predicted Quilting:       {best['predicted_quilting_nm']} nm")
    print(f"  ----------------------------------------------------------------------")
    print(f"  FEA Actual Mass:             {fea['actual_mass_kg']} kg (Target: <= 12.0 kg) -> {'PASS' if fea['actual_mass_kg'] <= 12.0 else 'FAIL'}")
    print(f"  FEA Actual RMS Sag:          {fea['actual_rms_sag_nm']} nm (Target: <= 60.0 nm) -> {'PASS' if fea['actual_rms_sag_nm'] <= 60.0 else 'FAIL'}")
    print(f"  FEA Actual Quilting:         {fea['actual_quilting_nm']} nm (Limit: <= 30.0 nm) -> {'PASS' if fea['actual_quilting_nm'] <= 30.0 else 'FAIL'}")
    print(f"  All Constraints Passed:      {fea['optical_pass']}")
    print(f"  Support Pad Node Snapping:   {fea['whiffletree_hubs_count']}/18 Hubs Locked to 3-Rib Star Nodes")
    print(f"  Active Learning Status:      Logged (Error Residual: {residual['error_pct']}%)")
    print("="*80)

    if result.get("llm_report"):
        print("\n[Autonomous LLM Engineering Summary]")
        print(result["llm_report"])
        print()

    # Save validation report
    os.makedirs("validation", exist_ok=True)
    report_file = "validation/benchmark_560mm_result.json"
    with open(report_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[Phase 7 SUCCESS] Full benchmark audit saved to '{report_file}'\n")

if __name__ == "__main__":
    run_benchmark()
