"""
Local FastAPI Server uniting all 4 Pillars with Full Objectives 1, 2, 3 Implementation
Exposes REST endpoints for:
1. Real-time ML and Deep PINN prediction (with 37 Fringe Zernike Wavefront decomposition)
2. Multi-Material Pareto Optimization (NSGA-II + PPO Reinforcement Learning across Zerodur, SiC, ULE, Beryllium)
3. Generative CAD synthesis for all 8 pocket topologies with 18-point whiffletree mounts
4. Siemens NX Open & NASTRAN SOL 101/103 Finite Element Analysis bridge
"""

import os
import sys
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor
from ml_engine.pinn_inference import PINNMirrorPredictor
from optimizer.closed_loop_optimizer import ClosedLoopOptimizer
from optimizer.multi_material_optimizer import MultiMaterialOptimizer
from nx_bridge.nx_fea_analysis_agent import NXFEAAnalysisEngine
from cad_engine.cad_generator import (
    MirrorCADGenerator, synthesize_all_8_topologies, TOPOLOGY_CATALOG
)

app = FastAPI(
    title="Autonomous Generative Space Mirror Lightweighting Agent API",
    description="Dual-AI Optomechanical Optimization, Deep PINN Surrogate, and Multi-Material Digital Twin",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize engines
predictor = MirrorSurrogatePredictor()
pinn_predictor = PINNMirrorPredictor()
optimizer = ClosedLoopOptimizer()
multi_mat_optimizer = MultiMaterialOptimizer()
fea_engine = NXFEAAnalysisEngine()


class MirrorDesignInput(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 120.0
    H_mm: float = 73.7
    tf_mm: float = 1.0
    tw_mm: float = 3.0
    L_mm: float = 55.5
    rf_mm: float = 3.0
    material: Optional[str] = "zerodur"
    topology: Optional[str] = "triangular_isogrid"
    journal_code: Optional[str] = None


class OptimizeRequest(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 120.0
    H_mm: float = 73.7
    max_mass_kg: float = 12.0
    max_sag_nm: float = 60.0
    num_candidates: int = 50000
    mode: str = "target"
    material: Optional[str] = "zerodur"
    topology: Optional[str] = "triangular_isogrid"


class MultiMaterialOptimizeRequest(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 120.0
    H_mm: float = 73.7
    target_mass_kg: float = 12.0
    max_sag_nm: float = 60.0
    material: str = "zerodur"
    topology: str = "triangular_isogrid"
    algorithm: str = "nsga2"  # "nsga2", "ppo", or "all_materials"


class UnifiedOptimizeRequest(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 120.0
    H_mm: float = 73.7
    max_mass_kg: float = 12.0
    max_sag_nm: float = 60.0
    num_candidates: int = 50000
    mode: str = "target"
    material: Optional[str] = "zerodur"
    topology: Optional[str] = "triangular_isogrid"


class ChatRequest(BaseModel):
    prompt: str


@app.get("/api/health")
def health_check():
    return {
        "status": "ONLINE",
        "pillars": {
            "pillar_1_agent": "FastAPI + Local LLM Qwen2.5-Coder Middleware Active",
            "pillar_2_surrogate": "Multi-Output XGBoost + PyTorch Deep Residual PINN (< 0.5 ms) Active",
            "pillar_3_optimizer": "NSGA-II Genetic Algorithm + PPO Reinforcement Learning Ready",
            "pillar_4_fea_nx": "Siemens NX Open & NASTRAN SOL 101/103 Digital Twin Bridge Ready"
        },
        "objectives_status": {
            "objective_1_cad": "8 Pocket Topologies + 18-Point Kinematic Whiffletree Mount Active",
            "objective_2_pinn": "Physics-Informed Neural Network + 37-Term Fringe Zernike Active",
            "objective_3_rl_materials": "PPO/SAC + NSGA-II across Zerodur, SiC, ULE, and Beryllium Active"
        }
    }


@app.post("/ml/predict")
def predict_metrics(design: MirrorDesignInput):
    """
    Sub-millisecond prediction from Pillar 2 ML Surrogate.
    """
    try:
        res = predictor.predict(
            design.D_mm, design.Dc_mm, design.H_mm,
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ml/predict")
def predict_metrics_get(
    D_mm: float = 560.0, Dc_mm: float = 120.0, H_mm: float = 73.7,
    tf_mm: float = 1.0, tw_mm: float = 3.0, L_mm: float = 55.5, rf_mm: float = 3.0
):
    """GET endpoint for ML XGBoost surrogate evaluation with query parameters."""
    try:
        return predictor.predict(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pinn/predict")
def predict_pinn_with_zernike(design: MirrorDesignInput):
    """
    Objective 2: Sub-millisecond evaluation via PyTorch Deep Residual PINN.
    Returns scalar metrics AND full 37-term Fringe Zernike wavefront coefficients.
    """
    try:
        return pinn_predictor.predict(
            D_mm=design.D_mm, Dc_mm=design.Dc_mm, H_mm=design.H_mm,
            tf_mm=design.tf_mm, tw_mm=design.tw_mm, L_mm=design.L_mm, rf_mm=design.rf_mm,
            material=design.material or "zerodur", topology=design.topology or "triangular_isogrid"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pinn/predict")
def predict_pinn_with_zernike_get(
    D_mm: float = 560.0, Dc_mm: float = 120.0, H_mm: float = 73.7,
    tf_mm: float = 1.0, tw_mm: float = 3.0, L_mm: float = 55.5, rf_mm: float = 3.0,
    material: str = "zerodur", topology: str = "triangular_isogrid"
):
    """GET endpoint for instant PINN surrogate evaluation with query parameters."""
    try:
        return pinn_predictor.predict(
            D_mm=D_mm, Dc_mm=Dc_mm, H_mm=H_mm,
            tf_mm=tf_mm, tw_mm=tw_mm, L_mm=L_mm, rf_mm=rf_mm,
            material=material or "zerodur", topology=topology or "triangular_isogrid"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize")
def run_pareto_optimization(req: OptimizeRequest):
    """
    Evaluates candidate geometries using Pillar 3 & Pillar 2.
    """
    try:
        best_design = optimizer.optimize(
            req.D_mm, req.Dc_mm, req.H_mm,
            req.max_mass_kg, req.max_sag_nm, req.num_candidates,
            mode=req.mode
        )
        return best_design
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize/nsga2")
def run_nsga2_optimization(req: OptimizeRequest):
    """
    Vectorized NSGA-II Multi-Objective Genetic Algorithm with non-dominated sorting and crowding distance.
    """
    try:
        best_design = optimizer.optimize_nsga2(
            req.D_mm, req.Dc_mm, req.H_mm, req.max_mass_kg, req.max_sag_nm,
            mode=req.mode
        )
        return best_design
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize/multi_material")
def run_multi_material_optimization(req: MultiMaterialOptimizeRequest):
    """
    Objective 3: Optimizes across Zerodur, SiC, ULE, and Beryllium using NSGA-II or PPO RL.
    """
    try:
        if req.algorithm == "all_materials":
            return multi_mat_optimizer.run_cross_material_trade_study(
                D_mm=req.D_mm, Dc_mm=req.Dc_mm, H_mm=req.H_mm,
                target_mass_kg=req.target_mass_kg, max_sag_nm=req.max_sag_nm
            )
        elif req.algorithm == "ppo":
            return multi_mat_optimizer.optimize_material_rl_ppo(
                material=req.material, topology=req.topology,
                D_mm=req.D_mm, Dc_mm=req.Dc_mm,
                target_mass_kg=req.target_mass_kg, target_sag_nm=req.max_sag_nm
            )
        else:
            return multi_mat_optimizer.optimize_material_nsga2(
                material=req.material, topology=req.topology,
                D_mm=req.D_mm, Dc_mm=req.Dc_mm, H_mm=req.H_mm,
                target_mass_kg=req.target_mass_kg, max_sag_nm=req.max_sag_nm
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize/rl_ppo")
def run_ppo_rl_optimization(req: MultiMaterialOptimizeRequest):
    """
    Objective 3: Dedicated PPO Reinforcement Learning policy optimization endpoint.
    """
    try:
        return multi_mat_optimizer.optimize_material_rl_ppo(
            material=req.material, topology=req.topology,
            D_mm=req.D_mm, Dc_mm=req.Dc_mm,
            target_mass_kg=req.target_mass_kg, target_sag_nm=req.max_sag_nm
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize/unified")
def run_unified_optimization(req: UnifiedOptimizeRequest):
    """
    Cooperative Two-Stage Coarse-to-Fine Optimization Pipeline:
    1. Stage 1: NSGA-II + XGBoost explores global design space across 16,000+ candidates -> finds macro Pareto seed.
    2. Stage 2: PPO Reinforcement Learning takes NSGA-II seed and fine-tunes continuous variables via Deep PINN.
    3. Stage 3: Deep PINN evaluates refined champion and computes full 37-term Fringe Zernike wavefront decomposition.
    """
    mat = req.material or "zerodur"
    top = req.topology or "triangular_isogrid"

    try:
        coop_res = multi_mat_optimizer.run_cooperative_pipeline(
            material=mat,
            topology=top,
            D_mm=req.D_mm,
            Dc_mm=req.Dc_mm,
            H_mm=req.H_mm,
            target_mass_kg=req.max_mass_kg,
            max_sag_nm=req.max_sag_nm,
            mode=req.mode or "target"
        )
        return coop_res
    except Exception as e_coop:
        print(f"[Unified Pipeline Exception]: {e_coop}")
        import traceback
        traceback.print_exc()
        try:
            nsga2_res = optimizer.optimize_nsga2(
                req.D_mm, req.Dc_mm, req.H_mm, req.max_mass_kg, req.max_sag_nm,
                mode=req.mode or "target"
            )
            pinn_eval = pinn_predictor.predict(
                D_mm=req.D_mm, Dc_mm=req.Dc_mm, H_mm=nsga2_res.get("H_mm", req.H_mm),
                tf_mm=nsga2_res.get("tf_mm", 1.0), tw_mm=nsga2_res.get("tw_mm", 3.0),
                L_mm=nsga2_res.get("L_mm", 55.5), rf_mm=nsga2_res.get("rf_mm", 3.0),
                material=mat, topology=top
            )
            return {
                "status": "FALLBACK_NSGA2",
                "pipeline": "NSGA-II + PINN",
                "winner": "nsga2",
                "winner_reason": f"Fallback NSGA-II GA: {e_coop}",
                "best": pinn_eval,
                "handoff": {
                    "handoff_message": f"NSGA-II Seed: {nsga2_res.get('mass_kg')} kg | Sag: {nsga2_res.get('rms_sag_nm')} nm"
                },
                "nsga2_seed": nsga2_res,
                "pinn_zernike": pinn_eval
            }
        except Exception as e_fallback:
            raise HTTPException(status_code=500, detail=f"Optimization failed: {e_fallback}")


@app.get("/cad/topologies")
def get_synthesized_topologies(D_mm: float = 560.0, Dc_mm: float = 120.0, H_mm: float = 73.7,
                               tf_mm: float = 1.0, tw_mm: float = 3.0, L_mm: float = 55.5,
                               rf_mm: float = 3.0, material: str = "zerodur"):
    """
    Objective 1: Synthesizes and returns specifications for all 8 pocket topologies with 18-point whiffletree mounts.
    """
    try:
        return synthesize_all_8_topologies(
            D_mm=D_mm, Dc_mm=Dc_mm, H_mm=H_mm, tf_mm=tf_mm, tw_mm=tw_mm,
            L_mm=L_mm, rf_mm=rf_mm, material=material
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cad/generate_all_nx_journals")
def generate_nx_journals_all_8_topologies(design: MirrorDesignInput):
    """
    Objective 1: Generates Siemens NX Open Python journal scripts for each of the 8 pocket topologies.
    """
    try:
        output_files = {}
        for top in TOPOLOGY_CATALOG:
            gen = MirrorCADGenerator(
                D_mm=design.D_mm, Dc_mm=design.Dc_mm, H_mm=design.H_mm,
                tf_mm=design.tf_mm, tw_mm=design.tw_mm, L_mm=design.L_mm,
                rf_mm=design.rf_mm, topology=top, material=design.material or "zerodur"
            )
            journal_path = gen.generate_nx_open_journal()
            output_files[top] = journal_path
        return {"status": "SUCCESS", "nx_journals": output_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fea/solve")
def run_fea_validation(design: MirrorDesignInput):
    """
    Runs NASTRAN SOL 101 ground-truth FEA validation via Pillar 4.
    """
    try:
        fea_res = fea_engine.run_fea_solve(
            design.D_mm, design.Dc_mm, design.H_mm,
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm
        )
        ml_pred = predictor.predict(
            design.D_mm, design.Dc_mm, design.H_mm,
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm
        )
        residual_entry = optimizer.log_fea_residual(
            design.dict(), ml_pred["rms_sag_nm"],
            fea_res["actual_rms_sag_nm"], fea_res["actual_mass_kg"]
        )
        return {
            "fea_results": fea_res,
            "ml_comparison": ml_pred,
            "active_learning_residual": residual_entry
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/active_learning/status")
def get_active_learning_status():
    """Returns status of the active learning online residual compensator."""
    try:
        return predictor.active_learner.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/active_learning/retrain")
def trigger_active_learning_retrain():
    """Triggers online retraining of the active learning compensator using all buffer entries."""
    try:
        success = predictor.active_learner.train_from_buffer()
        return {
            "success": success,
            "status": predictor.active_learner.get_status()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/chat")
def agent_chat_endpoint(req: ChatRequest):
    """
    Conversational engineering agent endpoint powered by local Qwen2.5-Coder:7b (Ollama).
    """
    try:
        from server.agent_orchestrator import OptoMechanicalAgent
        agent = OptoMechanicalAgent()
        reply = agent.chat(req.prompt)
        return {
            "response": reply["text"],
            "is_workflow": reply.get("is_workflow", False),
            "best_design": reply.get("best_design"),
            "fea": reply.get("fea_verification"),
            "model": "qwen2.5-coder:7b"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cad/create_prt")
def create_nx_prt_file(design: MirrorDesignInput):
    """
    Executes Siemens NX Open to build and save the native 3D .prt CAD part.
    """
    try:
        prt_result = fea_engine.create_3d_prt(
            design.D_mm, design.Dc_mm, design.H_mm,
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm,
            journal_code=design.journal_code
        )
        return prt_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cad/generate_journal")
def generate_cad_journal(design: MirrorDesignInput):
    """
    Creates Siemens NX Open Python journal file.
    """
    try:
        script_path = fea_engine.generate_nx_journal_script(
            design.D_mm, design.Dc_mm, design.H_mm,
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm
        )
        return {"journal_script": script_path, "status": "GENERATED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/", StaticFiles(directory=workspace_root, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("[Autonomous Agent Server] Starting server on http://127.0.0.1:8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
