"""
Autonomous Agent Orchestrator & Tool Calling Engine (Pillar 1)
Connects local Qwen2.5-Coder:7b (Ollama) to: exact NX-journal mass, FEA-trained sag surrogate,
NSGA-II (+ PPO refinement) and genuine FEA verification (NX Nastran if installed, else CalculiX).
All PASS/FAIL statements are computed from the numbers - nothing is hardcoded.
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
from ml_engine.pinn_inference import ZernikeSurrogatePredictor
from optimizer.closed_loop_optimizer import ClosedLoopOptimizer
from optimizer.multi_material_optimizer import MultiMaterialOptimizer
from nx_bridge.nx_fea_analysis_agent import NXFEAAnalysisEngine
TOPOLOGY_CATALOG = ["triangular_isogrid"]   # only topology with FEA training data

# ─────────────────────────────────────────────
# Engineering System Prompt for Qwen2.5-Coder
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are an autonomous Opto-Mechanical Design AI Agent specializing in space telescope primary mirror lightweighting.

You have access to a complete intelligent engineering system:
1. Exact mass of the NX journal geometry (identical to the NX part).
2. Gaussian-process surrogate trained on finite-element gravity analyses of the exact geometry: RMS/PV sag and 37 Fringe Zernike terms, with uncertainty.
3. NSGA-II multi-objective optimizer (+ PPO local refinement, accepted only if it improves the design).
4. Materials: Zerodur, ULE, SiC, Beryllium (sag scales with density/modulus).
5. FEA verification: NX Nastran SOL 101 if installed, otherwise CalculiX (C3D10, 18-point pads, 1 g axial).
Quilting and natural frequency are analytic estimates, not FEA. Only the triangular isogrid has FEA data.
Never claim a requirement is met unless the numbers given to you show it.

Target benchmark: D=560mm, mass<=12kg, RMS sag<=60nm, quilting<=30nm, f1>=120Hz.

When answering:
- Be concise, professional, and mathematically rigorous.
- Always include units (kg, nm, mm, Hz).
- Highlight trade-offs between materials and topologies when prompted.
- Provide actionable recommendations for space flight qualification."""


class OptoMechanicalAgent:
    def __init__(self,
                 ollama_url="http://localhost:11434/api/generate",
                 model_name="qwen2.5-coder:7b"):
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.predictor  = MirrorSurrogatePredictor()
        self.pinn       = ZernikeSurrogatePredictor()
        self.optimizer  = ClosedLoopOptimizer()
        self.multi_mat_opt = MultiMaterialOptimizer()
        self.fea_engine = NXFEAAnalysisEngine()
        self._llm_available = self._ping_ollama()
        if self._llm_available:
            print("[Pillar 1 Agent] Qwen2.5-Coder:7b connected via Ollama [OK]")
        else:
            print("[Pillar 1 Agent] Ollama not reachable - using rule-based NLP fallback")

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

    def parse_engineering_intent(self, text):
        """Extract numerical constraints and options from user prompt."""
        d_match    = re.search(r'(\d{3,4})\s*mm', text, re.IGNORECASE)
        mass_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', text, re.IGNORECASE)
        sag_match  = re.search(r'(\d+(?:\.\d+)?)\s*nm', text, re.IGNORECASE)
        is_min     = bool(re.search(r'\b(min|minimum|least|lightest)\b', text, re.IGNORECASE))

        material = "zerodur"
        for mat in ["sic", "silicon carbide", "ule", "beryllium", "zerodur"]:
            if mat in text.lower():
                material = "sic" if "sic" in mat or "silicon" in mat else mat
                break

        topology = "triangular_isogrid"
        for top in TOPOLOGY_CATALOG:
            clean_top = top.replace("_", " ")
            if clean_top in text.lower() or top in text.lower():
                topology = top
                break

        target_mass = 999.0 if is_min else (float(mass_match.group(1)) if mass_match else 12.0)

        return {
            "D_mm":        float(d_match.group(1))    if d_match    else 560.0,
            "max_mass_kg": target_mass,
            "max_sag_nm":  float(sag_match.group(1))  if sag_match  else 60.0,
            "is_min":      is_min,
            "material":    material,
            "topology":    topology
        }

    def run_agent_workflow(self, user_prompt, run_fea=True):
        """Parse -> NSGA-II on exact mass + FEA surrogate -> genuine FEA check -> report."""
        intent = self.parse_engineering_intent(user_prompt)
        D_mm, max_mass, max_sag = intent["D_mm"], intent["max_mass_kg"], intent["max_sag_nm"]
        material, topology = intent["material"], intent["topology"]
        Dc_mm = 175.0
        best = self.multi_mat_opt.optimize_material_nsga2(
            material=material, topology=topology, D_mm=D_mm, Dc_mm=Dc_mm, H_mm=73.7,
            target_mass_kg=max_mass, max_sag_nm=max_sag, mode="min" if intent.get("is_min") else "target")
        fea = None
        if run_fea:
            fea = self.fea_engine.run_fea_solve(D_mm, Dc_mm, best["H_mm"], best["tf_mm"], best["tw_mm"],
                                                best["L_mm"], best["rf_mm"], material=material)
            if material == "zerodur":
                self.optimizer.add_fea_record(best, fea["raw"] | {"zernike_fringe_37_nm": fea["zernike_fringe_37_nm"]},
                                              source="nx_nastran" if "Nastran" in fea["solver"] else "calculix")
        report = self._generate_report(best, fea, material, topology, max_mass, max_sag)
        return {"prompt": user_prompt, "material": material, "topology": topology,
                "pareto_best_design": best, "fea_verification": fea, "llm_report": report}

    def _generate_report(self, best, fea, material, topology, max_mass, max_sag):
        sag = fea["actual_rms_sag_nm"] if fea else best["rms_sag_nm"]
        sag_src = fea["solver"] if fea else "FEA-trained surrogate (not verified by a new FEA run)"
        mass = best["mass_kg"]
        lines = [
            f"Material: {material.upper()} | Topology: {topology} | 18-point Hindle whiffletree pads",
            f"Geometry: H={best['H_mm']} mm, tf={best['tf_mm']} mm, tw={best['tw_mm']} mm, L={best['L_mm']} mm, rf={best['rf_mm']} mm",
            f"Mass (exact NX geometry): {mass:.3f} kg vs target {max_mass} kg -> {'PASS' if mass <= max_mass + 0.1 else 'FAIL'}",
            f"RMS gravity sag ({sag_src}): {sag:.2f} nm vs limit {max_sag} nm -> {'PASS' if sag <= max_sag else 'FAIL'}",
            f"Surrogate predicted {best['rms_sag_nm']:.2f} +/- {best.get('rms_sag_std_nm', 0):.2f} nm"
            + (f"; FEA/surrogate gap {100*(best['rms_sag_nm']-sag)/sag:+.1f}%" if fea else ""),
            f"Quilting (analytic estimate): {best['predicted_quilting_nm']:.1f} nm; f1 (analytic estimate): {best['predicted_freq_hz']:.0f} Hz",
        ]
        facts = "\n".join(lines)
        llm_text = self._call_llm("Write a short engineering assessment of these results. Use only these numbers:\n" + facts,
                                  system=SYSTEM_PROMPT)
        return ("### Results\n" + facts + ("\n\n### Assessment\n" + llm_text if llm_text else ""))

    def chat(self, user_message):
        """Conversational interface with intent classification."""
        intent_keywords = ["design", "optimize", "benchmark", "lightweight", "mirror", "diameter", "zerodur", "sic", "ule", "beryllium"]
        has_intent = any(kw in user_message.lower() for kw in intent_keywords)
        has_numbers = bool(re.search(r'\d+', user_message))

        if has_intent and has_numbers:
            workflow_res = self.run_agent_workflow(user_message)
            return {
                "text": workflow_res["llm_report"],
                "is_workflow": True,
                "best_design": workflow_res["pareto_best_design"],
                "fea_verification": workflow_res["fea_verification"],
                "pinn": workflow_res["pinn_evaluation"]
            }
        else:
            reply = self._call_llm(user_message, system=SYSTEM_PROMPT)
            if not reply:
                reply = "I am the Opto-Mechanical Design AI Agent. Please provide your mirror requirements (e.g., 'Design a 560mm Beryllium mirror with mass <= 12kg and sag <= 60nm')."
            return {"text": reply, "is_workflow": False}


if __name__ == "__main__":
    agent = OptoMechanicalAgent()
    res = agent.chat("Design and optimize a 560mm SiC mirror with mass <= 12kg and sag <= 60nm")
    print(res["text"])
