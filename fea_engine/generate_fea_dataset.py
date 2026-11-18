"""
Generate a genuine FEA training/validation dataset for the isogrid mirror family.

For every design point:
  1. the EXACT NX journal is produced by the app's own generator (tools/gen_journal.js
     executes generateNXCode() from app.js headlessly) - so the geometry is identical to
     what you build in NX,
  2. mass is computed by the exact journal replica (validated against OpenCascade),
  3. gravity sag / Zernikes are computed by CalculiX FEA (fea_engine/mirror_fea.py).
Results are appended to data/fea/isogrid_fea_dataset.jsonl (resumable).

Parameters are rounded to 0.1 mm because the journal writes them with toFixed(1).
"""
import json, math, os, subprocess, sys, time, traceback
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fea_engine.mirror_fea import run_gravity_fea

OUT_CCX = os.path.join(ROOT, "data", "fea", "isogrid_fea_dataset.jsonl")
OUT_NASTRAN = os.path.join(ROOT, "data", "fea", "nx_nastran_results.jsonl")
FIXED = {"diameter": 560.0, "centralHoleDia": 175.0, "radiusCurv": 1085.0, "conicConstant": -1.22,
         "pattern": "isogrid", "supportType": "18point", "material": "zerodur", "density": 2530}
BOUNDS = {"faceplate": (0.8, 3.5), "ribThick": (1.5, 5.5), "cellSize": (38.0, 92.0), "depth": (55.0, 95.0)}


def journal_for(params):
    """Exact app journal via node (if available); otherwise the journal-identical Python generator."""
    p = dict(FIXED); p.update(params)
    try:
        return subprocess.run(["node", os.path.join(ROOT, "tools", "gen_journal.js"), json.dumps(p)],
                              capture_output=True, text=True, check=True).stdout
    except Exception:
        from cad_engine.exact_mass import isogrid_geometry_details
        return isogrid_geometry_details(p["diameter"], p["centralHoleDia"], p["depth"], p["faceplate"],
                                        p["ribThick"], p["cellSize"], p["filletRadius"], p["radiusCurv"], p["conicConstant"])


def max_fillet(L, tw):
    ps = L - tw * 2.0 / math.sqrt(3.0)
    r_in = ps / math.sqrt(3.0)
    return 0.45 * r_in


def design_points(n_sobol=128, seed=7):
    from scipy.stats import qmc
    named = [
        ("current_prt_46.4", {"faceplate": 3.2, "ribThick": 5.3, "cellSize": 46.4, "filletRadius": 3.9, "depth": 73.7}),
        ("journal_1b30624", {"faceplate": 2.7, "ribThick": 1.5, "cellSize": 64.7, "filletRadius": 1.1, "depth": 73.7}),
        ("journal_56b76e8", {"faceplate": 1.7, "ribThick": 1.5, "cellSize": 59.2, "filletRadius": 3.9, "depth": 73.7}),
        ("app_default_91", {"faceplate": 1.5, "ribThick": 1.5, "cellSize": 91.0, "filletRadius": 10.0, "depth": 73.7}),
    ]
    pts = [(n, p) for n, p in named]
    s = qmc.Sobol(d=5, scramble=True, seed=seed).random(n_sobol)
    keys = ["faceplate", "ribThick", "cellSize", "depth"]
    for i, u in enumerate(s):
        p = {}
        for j, kk in enumerate(keys):
            lo, hi = BOUNDS[kk]
            p[kk] = round(lo + u[j] * (hi - lo), 1)
        rf_hi = min(10.0, max_fillet(p["cellSize"], p["ribThick"]))
        p["filletRadius"] = round(1.0 + u[4] * (rf_hi - 1.0), 1)
        pts.append((f"sobol_{i:03d}", p))
    return pts


def main(mesh=8.0, limit=None, solver="calculix"):
    OUT = OUT_NASTRAN if solver == "nastran" else OUT_CCX
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        for ln in open(OUT):
            try:
                done.add(json.loads(ln)["id"])
            except Exception:
                pass
    pts = design_points()
    if limit:
        pts = pts[:limit]
    for pid, p in pts:
        if pid in done:
            continue
        t0 = time.time()
        try:
            code = journal_for(p)
            res = run_gravity_fea(code, material="zerodur", mesh_size=mesh, solver_backend=solver)
            rec = {"id": pid, "params": p, "fixed": FIXED, **res,
                   "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "wall_s": round(time.time() - t0, 1)}
            with open(OUT, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"[{pid}] mass={res['replica_mass_kg']:.3f} kg rms={res['rms_sag_nm']:.2f} nm ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"[{pid}] FAILED: {e}", flush=True)
            traceback.print_exc()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Generate genuine FEA dataset (resumable)")
    ap.add_argument("mesh", nargs="?", type=float, default=8.0)
    ap.add_argument("limit", nargs="?", type=int, default=None)
    ap.add_argument("--solver", choices=["calculix", "nastran"], default="calculix",
                    help="nastran = Siemens NX Nastran SOL 101 (needs nastran.exe; writes nx_nastran_results.jsonl)")
    a = ap.parse_args()
    main(mesh=a.mesh, limit=a.limit, solver=a.solver)
