"""
Live Demonstration of Autonomous Opto-Mechanical Engineering Agent powered by Qwen2.5-Coder:7b (Pillar 1)
"""

import sys, os, time

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from server.agent_orchestrator import OptoMechanicalAgent

def run_live_demonstration():
    print("=" * 80)
    print("   LIVE DEMONSTRATION: QWEN 2.5 CODER 7B AUTONOMOUS OPTOMECHANICAL AGENT")
    print("=" * 80)

    agent = OptoMechanicalAgent()

    # -------------------------------------------------------------
    # DEMO 1: Engineering Knowledge Retrieval & Mathematical Reasoning
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" [SCENARIO 1] Direct Technical Inquiry to Qwen 2.5 Coder")
    print("=" * 80)
    query = (
        "Explain how the NASA SP-8040 flexural rigidity formula D* relates faceplate thickness (tf) "
        "and rib height to 1G gravity sag in a space telescope primary mirror."
    )
    print(f"USER PROMPT: \"{query}\"\n")
    print("[Qwen 2.5 Coder Generating Response...]")
    t0 = time.time()
    response = agent.chat(query)
    dur = time.time() - t0
    print(f"\nQWEN 2.5 CODER RESPONSE (Generated in {dur:.2f}s):\n")
    print(response)

    # -------------------------------------------------------------
    # DEMO 2: Full Autonomous 4-Pillar Multi-Tool Optimization Loop
    # -------------------------------------------------------------
    print("\n\n" + "=" * 80)
    print(" [SCENARIO 2] Autonomous End-to-End Multi-Tool Workflow")
    print("=" * 80)
    task_prompt = (
        "We need to design a 560mm primary mirror with center hole Dc=120mm. "
        "Target mass must be strictly under 12.0kg, RMS gravity sag under 60nm, "
        "and polishing quilting under 30nm. Optimize the isogrid pocket geometry and verify with FEA."
    )
    print(f"USER TASK: \"{task_prompt}\"\n")

    t0 = time.time()
    result = agent.run_agent_workflow(task_prompt)
    total_time = time.time() - t0

    print("\n" + "=" * 80)
    print("   PILLAR 4 GROUND TRUTH & ACTIVE LEARNING AUDIT")
    print("=" * 80)
    best = result["pareto_best_design"]
    fea = result["fea_verification"]
    residual = result["active_learning"]

    print(f"  Recommended Geometry:  H={best['H_mm']}mm, tf={best['tf_mm']}mm, tw={best['tw_mm']}mm, L={best['L_mm']}mm, rf={best['rf_mm']}mm")
    print(f"  ML Predicted:          Mass={best['predicted_mass_kg']}kg, Sag={best['predicted_rms_sag_nm']}nm, Quilt={best['predicted_quilting_nm']}nm")
    print(f"  FEA Actual Result:     Mass={fea['actual_mass_kg']}kg, Sag={fea['actual_rms_sag_nm']}nm, Quilt={fea['actual_quilting_nm']}nm")
    print(f"  All Constraints Met:   {fea['optical_pass']}")
    print(f"  18-Hub Star Snapping:  {fea['whiffletree_hubs_count']}/18 Hubs Locked")
    print(f"  Active Learning Error: {residual['error_pct']}%")

    print("\n" + "=" * 80)
    print(f"   QWEN 2.5 CODER SYNTHESIS & ENGINEERING REPORT (Total Workflow Time: {total_time:.2f}s)")
    print("=" * 80)
    print(result["llm_report"])
    print("=" * 80)

if __name__ == "__main__":
    run_live_demonstration()
