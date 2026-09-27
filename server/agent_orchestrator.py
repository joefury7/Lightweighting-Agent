"""
Autonomous Agent Orchestrator & Tool Calling Engine (Pillar 1)
Connects local Qwen2.5-Coder:7b (Ollama) to the full 4-Pillar engineering pipeline.
"""

import os
import sys
import re
import json
import time
import urllib.request
import urllib.error

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor
from optimizer.closed_loop_optimizer import ClosedLoopOptimizer
from nx_bridge.nx_fea_analysis_agent import NXFEAAnalysisEngine

# ─────────────────────────────────────────────
# Engineering System Prompt for Qwen2.5-Coder
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are an autonomous Opto-Mechanical Design AI Agent specializing in space telescope primary mirror lightweighting.

You have access to a 4-pillar engineering system:
1. ML Surrogate (Pillar 2): predicts mass_kg, rms_sag_nm, quilting_nm, frequency_hz in 0.38ms
2. Pareto Optimizer (Pillar 3): searches 50,000 candidate designs instantly
3. NASTRAN FEA Solver (Pillar 4): ground-truth verification via Simcenter NASTRAN SOL 101
4. NX CAD Generator: creates Siemens NX Open journal files

Mirror material: SCHOTT Zerodur (E=90.3GPa, rho=2530kg/m3, nu=0.24)
Physics: NASA SP-8040 isogrid rigidity + Nelson 18-point Whiffletree sag (K18=0.0000632) + Yoder quilting

Target benchmark: D=560mm, mass<=12kg, RMS sag<=60nm, quilting<=30nm
Known validated point (NASTRAN Run 306): tf=1.0mm, tw=3.0mm, L=55.5mm, H=73.7mm → 11.98kg, 58.11nm

When answering:
- Be concise and technical
- Always include units (kg, nm, mm, Hz)
- Interpret engineering requests and suggest next steps
- If given optimization results, explain trade-offs clearly"""


class OptoMechanicalAgent:
    def __init__(self,
                 ollama_url="http://localhost:11434/api/generate",
                 model_name="qwen2.5-coder:7b"):
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.predictor  = MirrorSurrogatePredictor()
        self.optimizer  = ClosedLoopOptimizer()
        self.fea_engine = NXFEAAnalysisEngine()
        self._llm_available = self._ping_ollama()
        if self._llm_available:
            print("[Pillar 1 Agent] Qwen2.5-Coder:7b connected via Ollama [OK]")
        else:
            print("[Pillar 1 Agent] Ollama not reachable - using rule-based NLP fallback")

    # ── Ollama connectivity ──────────────────────────────────────────────────
    def _ping_ollama(self):
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3):
                return True
        except Exception:
            return False

    def _call_llm(self, prompt, system=None):
        """Call Qwen2.5-Coder:7b via Ollama REST API."""
        if not self._llm_available:
            return None
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload = json.dumps({
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 512}
        }).encode()
        try:
            req = urllib.request.Request(
                self.ollama_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read()).get("response", "").strip()
        except Exception as e:
            print(f"[LLM Warning] {e}")
            return None

    # ── Intent Parsing (NLP) ────────────────────────────────────────────────
    def parse_engineering_intent(self, text):
        """Extract numerical constraints from user prompt (regex + LLM fallback)."""
        d_match    = re.search(r'(\d{3,4})\s*mm', text, re.IGNORECASE)
        mass_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', text, re.IGNORECASE)
        sag_match  = re.search(r'(\d+(?:\.\d+)?)\s*nm', text, re.IGNORECASE)

        return {
            "D_mm":        float(d_match.group(1))    if d_match    else 560.0,
            "max_mass_kg": float(mass_match.group(1)) if mass_match else 12.0,
            "max_sag_nm":  float(sag_match.group(1))  if sag_match  else 60.0,
        }

    # ── Main Agentic Workflow ────────────────────────────────────────────────
    def run_agent_workflow(self, user_prompt):
        """Full pipeline: Parse → ML Surrogate → Pareto Optimizer → NASTRAN FEA → LLM Report."""
        print(f"\n{'='*60}")
        print(f"[Pillar 1 Agent] User Prompt: {user_prompt}")
        print(f"{'='*60}")

        intent = self.parse_engineering_intent(user_prompt)
        D_mm, max_mass, max_sag = intent["D_mm"], intent["max_mass_kg"], intent["max_sag_nm"]
        print(f"[Agent] Parsed: D={D_mm}mm | Target mass≤{max_mass}kg | Target sag≤{max_sag}nm")

        # Step 1 ── Quick ML surrogate snapshot of known benchmark
        print("\n[Agent Step 1] Quick ML Surrogate snapshot on benchmark point...")
        benchmark_pred = self.predictor.predict(
            D_mm=D_mm, Dc_mm=D_mm*0.214, H_mm=73.7,
            tf_mm=1.0, tw_mm=3.0, L_mm=55.5, rf_mm=3.0
        )
        print(f"  Benchmark prediction: {benchmark_pred}")

        # Step 2 ── Pareto Optimizer (50k candidates)
        print("\n[Agent Step 2] Running 50,000-candidate Pareto Optimizer...")
        best = self.optimizer.optimize(
            D_mm=D_mm, Dc_mm=D_mm * 0.214,
            H_mm=73.7, max_mass_kg=max_mass,
            max_sag_nm=max_sag, num_candidates=50000
        )
        print(f"  Best candidate: tf={best['tf_mm']}mm, tw={best['tw_mm']}mm, "
              f"L={best['L_mm']}mm, H={best['H_mm']}mm")

        # Step 3 ── Ground-truth NASTRAN FEA verify
        print("\n[Agent Step 3] NASTRAN SOL 101 FEA Verification...")
        fea = self.fea_engine.run_fea_solve(
            D=best["D_mm"], Dc=best["Dc_mm"], H=best["H_mm"],
            tf=best["tf_mm"], tw=best["tw_mm"],
            L=best["L_mm"],  rf=best["rf_mm"]
        )

        # Step 4 ── Active Learning residual log
        residual = self.optimizer.log_fea_residual(
            best,
            best["predicted_rms_sag_nm"],
            fea["actual_rms_sag_nm"],
            fea["actual_mass_kg"]
        )

        # Step 5 ── LLM Engineering Report
        print("\n[Agent Step 5] Generating LLM Engineering Report...")
        llm_context = (
            f"User asked: '{user_prompt}'\n\n"
            f"Benchmark ML prediction (tf=1.0,tw=3.0,L=55.5,H=73.7): "
            f"mass={benchmark_pred['mass_kg']}kg, sag={benchmark_pred['rms_sag_nm']}nm\n\n"
            f"Pareto optimizer recommended: tf={best['tf_mm']}mm, tw={best['tw_mm']}mm, "
            f"L={best['L_mm']}mm, H={best['H_mm']}mm\n"
            f"Predicted → mass={best['predicted_mass_kg']}kg, sag={best['predicted_rms_sag_nm']}nm, "
            f"quilting={best['predicted_quilting_nm']}nm\n\n"
            f"NASTRAN FEA verified → mass={fea['actual_mass_kg']}kg, "
            f"sag={fea['actual_rms_sag_nm']}nm, quilting={fea['actual_quilting_nm']}nm\n"
            f"Optical pass: {fea['optical_pass']}\n"
            f"Residual error: {residual['error_pct']}%\n\n"
            "Write a concise 4-sentence engineering summary covering: "
            "(1) key design parameters, (2) how well targets are met, "
            "(3) trade-offs observed, (4) recommended next step."
        )
        llm_reply = self._call_llm(llm_context, SYSTEM_PROMPT)
        if not llm_reply:
            llm_reply = (
                f"Optimizer recommended tf={best['tf_mm']}mm, tw={best['tw_mm']}mm, "
                f"L={best['L_mm']}mm, H={best['H_mm']}mm. "
                f"NASTRAN FEA verified: mass={fea['actual_mass_kg']}kg, "
                f"sag={fea['actual_rms_sag_nm']}nm, quilting={fea['actual_quilting_nm']}nm. "
                f"Optical pass: {fea['optical_pass']}."
            )

        return {
            "prompt": user_prompt,
            "intent": intent,
            "benchmark_ml_prediction": benchmark_pred,
            "pareto_best_design": best,
            "fea_verification": fea,
            "active_learning": residual,
            "llm_report": llm_reply
        }

    def chat(self, user_message):
        """
        Smart conversational router:
        - If the message asks for optimization/design/refinement, runs the full 4-pillar tool workflow.
        - Otherwise, answers technical engineering questions directly via Qwen 2.5 Coder.
        """
        self._llm_available = self._ping_ollama()
        lower_msg = user_message.lower()

        # Keywords indicating an action/optimization task
        action_keywords = ["optimize", "design", "refine", "dimension", "lightweight", "under", "target", "find", "minimize"]
        is_action_task = any(kw in lower_msg for kw in action_keywords) or bool(re.search(r'\d+\s*(mm|kg|nm)', lower_msg))

        if is_action_task:
            print(f"[Pillar 1 Agent] Action intent detected in chat prompt -> Running Full Tool Pipeline...")
            workflow_res = self.run_agent_workflow(user_message)
            best = workflow_res["pareto_best_design"]
            fea = workflow_res["fea_verification"]

            formatted_response = (
                f"### 🎯 Optimal Refined Parameters:\n"
                f"- **Faceplate Thickness ($t_f$):** `{best['tf_mm']} mm`\n"
                f"- **Rib Wall Thickness ($t_w$):** `{best['tw_mm']} mm`\n"
                f"- **Cell Inscribed Diam ($L$):** `{best['L_mm']} mm`\n"
                f"- **Mirror Height ($H$):** `{best['H_mm']} mm`\n"
                f"- **Fillet Radius ($r_f$):** `{best['rf_mm']} mm`\n\n"
                f"### 📊 Verified Performance Metrics:\n"
                f"- **Mass:** **`{fea['actual_mass_kg']} kg`** (Target: $\leq 12.0\\text{{ kg}}$) -> **{'PASS ✅' if fea['actual_mass_kg'] <= 12.0 else 'FAIL ❌'}**\n"
                f"- **RMS Gravity Sag:** **`{fea['actual_rms_sag_nm']} nm`** (Target: $\leq 60.0\\text{{ nm}}$) -> **{'PASS ✅' if fea['actual_rms_sag_nm'] <= 60.0 else 'FAIL ❌'}**\n"
                f"- **Polishing Quilting:** **`{fea['actual_quilting_nm']} nm`** (Limit: $\leq 30.0\\text{{ nm}}$) -> **{'PASS ✅' if fea['actual_quilting_nm'] <= 30.0 else 'FAIL ❌'}**\n"
                f"- **Support Pads:** `{fea['whiffletree_hubs_count']}/18 Hubs Locked to 3-Rib Star Nodes`\n\n"
                f"### 🧠 AI Engineering Synthesis:\n"
                f"{workflow_res['llm_report']}"
            )

            return {
                "text": formatted_response,
                "is_workflow": True,
                "best_design": best,
                "fea_verification": fea
            }

        # Direct technical Q&A
        reply = self._call_llm(user_message, SYSTEM_PROMPT)
        if reply:
            return {"text": reply, "is_workflow": False}
        return {
            "text": (
                "[LLM offline] Rule-based response: Your query relates to the "
                "560mm Zerodur mirror lightweighting system. "
                "Use /ml/predict or /optimize endpoints for engineering analysis."
            ),
            "is_workflow": False
        }


# ── CLI Test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    agent = OptoMechanicalAgent()

    print("\n--- Test 1: Direct Engineering Chat ---")
    reply = agent.chat(
        "What is the relationship between faceplate thickness and polishing quilting "
        "deformation in a Zerodur isogrid mirror?"
    )
    print(f"LLM: {reply}\n")

    print("\n--- Test 2: Full Agentic Workflow ---")
    result = agent.run_agent_workflow(
        "Optimize a 560mm Zerodur primary mirror to mass under 12kg and gravity sag under 60nm."
    )
    print(f"\n[LLM Engineering Report]\n{result['llm_report']}")
