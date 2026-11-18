"""
Local FastAPI server for the mirror lightweighting studio.

  /ml/predict, /surrogate/predict (/pinn/predict alias)  exact mass + FEA-trained sag/Zernike surrogate
  /optimize, /optimize/nsga2, /optimize/unified ...        NSGA-II (+ PPO refinement) on the same evaluator
  /fea/solve                                               genuine FEA of the exact geometry (NX Nastran if
                                                           installed, else CalculiX); result is added to the
                                                           FEA dataset and the surrogate is refitted
  /cad/exact_mass                                          exact mass of ANY app journal (journal replica)
  /nx/mass_report                                          record NX-measured mass and compare with the app
"""

import json
import os
import sys
import time
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor
from ml_engine.pinn_inference import ZernikeSurrogatePredictor
from ml_engine.fea_surrogate import get_surrogate
from optimizer.closed_loop_optimizer import ClosedLoopOptimizer
from optimizer.multi_material_optimizer import MultiMaterialOptimizer
from nx_bridge.nx_fea_analysis_agent import NXFEAAnalysisEngine
from cad_engine.journal_replica import replica_mass

app = FastAPI(title="Space Mirror Lightweighting Studio API",
              description="Exact NX-geometry mass, FEA-trained surrogate, NSGA-II/PPO, genuine FEA verification",
              version="4.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

predictor = MirrorSurrogatePredictor()
zernike_predictor = ZernikeSurrogatePredictor()
optimizer = ClosedLoopOptimizer()
multi_mat_optimizer = MultiMaterialOptimizer()
fea_engine = NXFEAAnalysisEngine()
NX_REPORTS = os.path.join(workspace_root, "data", "nx", "nx_mass_reports.jsonl")


class MirrorDesignInput(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 175.0
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
    Dc_mm: float = 175.0
    H_mm: float = 73.7
    max_mass_kg: float = 12.0
    max_sag_nm: float = 60.0
    num_candidates: int = 50000
    mode: str = "target"
    material: Optional[str] = "zerodur"
    topology: Optional[str] = "triangular_isogrid"


class MultiMaterialOptimizeRequest(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 175.0
    H_mm: float = 73.7
    target_mass_kg: float = 12.0
    max_sag_nm: float = 60.0
    material: str = "zerodur"
    topology: str = "triangular_isogrid"
    algorithm: str = "nsga2"  # "nsga2", "ppo", or "all_materials"


class UnifiedOptimizeRequest(BaseModel):
    D_mm: float = 560.0
    Dc_mm: float = 175.0
    H_mm: float = 73.7
    max_mass_kg: float = 12.0
    target_mass_kg: Optional[float] = None
    max_sag_nm: float = 60.0
    num_candidates: int = 50000
    mode: str = "target"
    material: Optional[str] = "zerodur"
    topology: Optional[str] = "triangular_isogrid"


class ChatRequest(BaseModel):
    prompt: str


class JournalRequest(BaseModel):
    journal_code: str
    material: Optional[str] = "zerodur"


class NXMassReport(BaseModel):
    nx_mass_kg: float
    nx_volume_mm3: Optional[float] = None
    pocket_count_nx: Optional[int] = None
    pockets_failed: Optional[int] = None
    prt_path: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    journal_code: Optional[str] = None


def _err(e):
    raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def health_check():
    from fea_engine.mirror_fea import find_nastran
    sur = get_surrogate()
    val = os.path.join(workspace_root, "data", "fea", "surrogate_validation.json")
    return {
        "status": "ONLINE",
        "mass": "exact NX-journal geometry (validated against OpenCascade solid, 0.0000 g)",
        "sag_surrogate": {"type": "Gaussian process", **sur.meta,
                          "validation": json.load(open(val)) if os.path.exists(val) else None},
        "fea_solver_available": {"nx_nastran": find_nastran(), "calculix": bool(__import__("shutil").which("ccx") or os.environ.get("CCX_EXE"))},
        "nx_installed": fea_engine.is_nx_installed(),
        "analytic_only": ["quilting_nm", "frequency_hz"],
    }


@app.post("/ml/predict")
def predict_metrics(design: MirrorDesignInput):
    try:
        return predictor.predict(design.D_mm, design.Dc_mm, design.H_mm, design.tf_mm, design.tw_mm, design.L_mm,
                                 design.rf_mm, material=design.material or "zerodur", topology=design.topology or "triangular_isogrid")
    except Exception as e:
        _err(e)


@app.get("/ml/predict")
def predict_metrics_get(D_mm: float = 560.0, Dc_mm: float = 175.0, H_mm: float = 73.7, tf_mm: float = 1.5,
                        tw_mm: float = 3.0, L_mm: float = 55.5, rf_mm: float = 3.0, material: str = "zerodur"):
    try:
        return predictor.predict(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, material=material)
    except Exception as e:
        _err(e)


@app.post("/surrogate/predict")
@app.post("/pinn/predict")
def predict_with_zernike(design: MirrorDesignInput):
    try:
        return zernike_predictor.predict(D_mm=design.D_mm, Dc_mm=design.Dc_mm, H_mm=design.H_mm, tf_mm=design.tf_mm,
                                         tw_mm=design.tw_mm, L_mm=design.L_mm, rf_mm=design.rf_mm,
                                         material=design.material or "zerodur",
                                         topology=_topo(design.topology))
    except Exception as e:
        _err(e)


def _topo(t):
    return "triangular_isogrid" if (t or "isogrid") in ("isogrid", "triangular_isogrid") else t


@app.post("/optimize")
@app.post("/optimize/nsga2")
def run_nsga2_optimization(req: OptimizeRequest):
    try:
        return optimizer.optimize_nsga2(req.D_mm, req.Dc_mm, req.H_mm, req.max_mass_kg, req.max_sag_nm,
                                        mode=req.mode, material=req.material or "zerodur")
    except Exception as e:
        _err(e)


@app.post("/optimize/multi_material")
def run_multi_material_optimization(req: MultiMaterialOptimizeRequest):
    try:
        if req.algorithm == "all_materials":
            return multi_mat_optimizer.run_cross_material_trade_study(req.D_mm, req.Dc_mm, req.H_mm, req.target_mass_kg, req.max_sag_nm)
        if req.algorithm == "ppo":
            return multi_mat_optimizer.optimize_material_rl_ppo(req.material, _topo(req.topology), req.D_mm, req.Dc_mm,
                                                                req.target_mass_kg, req.max_sag_nm, H_mm=req.H_mm)
        return multi_mat_optimizer.optimize_material_nsga2(req.material, _topo(req.topology), req.D_mm, req.Dc_mm, req.H_mm,
                                                           req.target_mass_kg, req.max_sag_nm)
    except Exception as e:
        _err(e)


@app.post("/optimize/rl_ppo")
def run_ppo_rl_optimization(req: MultiMaterialOptimizeRequest):
    try:
        return multi_mat_optimizer.optimize_material_rl_ppo(req.material, _topo(req.topology), req.D_mm, req.Dc_mm,
                                                            req.target_mass_kg, req.max_sag_nm, H_mm=req.H_mm)
    except Exception as e:
        _err(e)


@app.post("/optimize/unified")
def run_unified_optimization(req: UnifiedOptimizeRequest):
    target = req.target_mass_kg if req.target_mass_kg is not None else req.max_mass_kg
    try:
        return multi_mat_optimizer.run_cooperative_pipeline(material=req.material or "zerodur", topology=_topo(req.topology),
                                                            D_mm=req.D_mm, Dc_mm=req.Dc_mm, H_mm=req.H_mm,
                                                            target_mass_kg=target, max_sag_nm=req.max_sag_nm,
                                                            mode=req.mode or "target")
    except Exception as e:
        _err(e)


@app.post("/cad/exact_mass")
def exact_mass_from_journal(req: JournalRequest):
    """Exact mass of whatever geometry the given NX journal builds (any pattern)."""
    try:
        r = replica_mass(req.journal_code)
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}
    except Exception as e:
        _err(e)


@app.post("/nx/mass_report")
def nx_mass_report(rep: NXMassReport):
    """Store the mass NX measured for a built part and compare it with the app's exact prediction."""
    try:
        app_mass = None
        if rep.journal_code:
            app_mass = replica_mass(rep.journal_code)["mass_kg"]
        rec = rep.dict()
        rec.pop("journal_code", None)
        rec["app_exact_mass_kg"] = app_mass
        rec["difference_g"] = None if app_mass is None else round((rep.nx_mass_kg - app_mass) * 1000, 3)
        rec["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(NX_REPORTS), exist_ok=True)
        with open(NX_REPORTS, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec
    except Exception as e:
        _err(e)


@app.post("/fea/solve")
def run_fea_validation(design: MirrorDesignInput):
    """Genuine FEA (takes ~1-3 min). Compares with the surrogate and adds the result to the dataset."""
    try:
        mat = design.material or "zerodur"
        pred = predictor.predict(design.D_mm, design.Dc_mm, design.H_mm, design.tf_mm, design.tw_mm, design.L_mm,
                                 design.rf_mm, material=mat)
        fea = fea_engine.run_fea_solve(design.D_mm, design.Dc_mm, design.H_mm, design.tf_mm, design.tw_mm,
                                       design.L_mm, design.rf_mm, material=mat)
        gap = 100.0 * (pred["rms_sag_nm"] - fea["actual_rms_sag_nm"]) / fea["actual_rms_sag_nm"]
        stored = {"stored": False}
        if mat == "zerodur":
            d = design.dict()
            d["material"] = mat
            stored = optimizer.add_fea_record(d, fea["raw"] | {"zernike_fringe_37_nm": fea["zernike_fringe_37_nm"]},
                                              source="nx_nastran" if "Nastran" in fea["solver"] else "calculix")
        return {"fea_results": fea, "surrogate_prediction": pred, "ml_comparison": pred,
                "surrogate_vs_fea_gap_pct": round(gap, 2), "dataset_update": stored}
    except Exception as e:
        _err(e)


@app.get("/active_learning/status")
@app.get("/fea/status")
def get_fea_status():
    sur = get_surrogate()
    return {"active_learning_enabled": True, "sample_count": sur.meta.get("n_training_records", 0), **sur.meta}


@app.post("/active_learning/retrain")
def trigger_retrain():
    sur = get_surrogate(refresh=True)
    return {"success": True, "status": sur.meta}


@app.post("/agent/chat")
def agent_chat_endpoint(req: ChatRequest):
    try:
        from server.agent_orchestrator import OptoMechanicalAgent
        agent = OptoMechanicalAgent()
        reply = agent.chat(req.prompt)
        return {"response": reply["text"], "is_workflow": reply.get("is_workflow", False),
                "best_design": reply.get("best_design"), "fea": reply.get("fea_verification"), "model": "qwen2.5-coder:7b"}
    except Exception as e:
        _err(e)


@app.post("/cad/create_prt")
def create_nx_prt_file(design: MirrorDesignInput):
    try:
        return fea_engine.create_3d_prt(design.D_mm, design.Dc_mm, design.H_mm, design.tf_mm, design.tw_mm,
                                        design.L_mm, design.rf_mm, journal_code=design.journal_code)
    except Exception as e:
        _err(e)


app.mount("/", StaticFiles(directory=workspace_root, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("[Autonomous Agent Server] Starting server on http://127.0.0.1:8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
