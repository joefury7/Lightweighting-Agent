"""
Local FastAPI Server uniting all 4 Pillars (Pillar 1)
Exposes REST endpoints for real-time ML prediction, Pareto optimization, CAD generation, and FEA solve.
"""

import os
import sys
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor
from optimizer.closed_loop_optimizer import ClosedLoopOptimizer
from nx_bridge.nx_fea_analysis_agent import NXFEAAnalysisEngine

app = FastAPI(
    title="Space Mirror Lightweighting Agent API",
    description="Dual-AI Optomechanical Optimization & Digital Twin Engine",
    version="2.0.0"
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
optimizer = ClosedLoopOptimizer()
fea_engine = NXFEAAnalysisEngine()

class MirrorDesignInput(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 120.0
    H_mm: float = 73.7
    tf_mm: float = 1.0
    tw_mm: float = 3.0
    L_mm: float = 55.5
    rf_mm: float = 3.0

class OptimizeRequest(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 120.0
    H_mm: float = 73.7
    max_mass_kg: float = 12.0
    max_sag_nm: float = 60.0
    num_candidates: int = 50000
    mode: str = "target"

class ChatRequest(BaseModel):
    prompt: str

from fastapi.staticfiles import StaticFiles

@app.get("/api/health")
def health_check():
    return {
        "status": "ONLINE",
        "pillars": {
            "pillar_1_agent": "FastAPI + Local LLM Middleware Active",
            "pillar_2_surrogate": "Multi-Output XGBoost (0.44 ms latency) Ready",
            "pillar_3_optimizer": "NSGA-II Closed-Loop Pareto Search Ready",
            "pillar_4_fea_nx": "Siemens NX Open & NASTRAN SOL 101 Bridge Ready"
        }
    }

@app.post("/ml/predict")
def predict_metrics(design: MirrorDesignInput):
    """
    Sub-millisecond prediction from Pillar 2 ML Surrogate.
    """
    try:
        return predictor.predict(
            design.D_mm, design.Dc_mm, design.H_mm,
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/optimize")
def run_pareto_optimization(req: OptimizeRequest):
    """
    Evaluates 50,000 candidate geometries using Pillar 3 & Pillar 2.
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
        # Log to Active Learning Buffer
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

@app.post("/optimize/nsga2")
def run_nsga2_optimization(req: OptimizeRequest):
    """
    True NSGA-II Multi-Objective Genetic Algorithm with non-dominated sorting and crowding distance.
    """
    try:
        best_design = optimizer.optimize_nsga2(
            req.D_mm, req.Dc_mm, req.H_mm, req.max_mass_kg, req.max_sag_nm,
            mode=req.mode
        )
        return best_design
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/active_learning/status")
def get_active_learning_status():
    """Returns status of the active learning residual compensator."""
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
            design.tf_mm, design.tw_mm, design.L_mm, design.rf_mm
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
    print("[Pillar 1 Server] Starting local server on http://127.0.0.1:8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
