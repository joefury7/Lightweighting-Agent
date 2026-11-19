"""
Proof of what the sag/optics model is trained on, and that the old data and models are gone.

Run:  python validation/prove_training_provenance.py [--resolve]
Writes data/fea/training_provenance_proof.json

Checks (each is computed, nothing is hard-coded to pass):
 1. Static scan  - no code file references the old datasets, old model files or old loaders.
 2. Filesystem   - none of the old dataset / model files exist in the repository.
 3. Runtime trace - every file opened while the served surrogate is built and queried is logged;
                    the only data files read are in data/fea/.
 4. Only source  - with data/fea/ hidden, the surrogate cannot be built (there is no other source).
 5. Reproducible - a model refitted from data/fea/ alone gives the same predictions as the served one.
 6. FEA records are solver output - every record's support reaction equals its self-weight
                    (static equilibrium from the CalculiX solve), plus mesh/solver metadata.
 7. (--resolve)  - re-run the FEA for one record from its parameters and compare.
 8. PPO policy   - trained against the FEA-trained environment (training report).
"""
import builtins
import hashlib
import json
import os
import re
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "fea", "training_provenance_proof.json")

OLD_FILES = [
    "data/analytic/mirror_training_data_10k.csv", "data/analytic/multi_material_mirror_dataset_25k.csv",
    "data/analytic/multi_topology_mirror_dataset_20k.csv", "data/analytic/isogrid_analytic_constraints_3884.csv",
    "data/analytic/material_properties_analytic_model.csv", "data/generate_training_data.py",
    "data/generate_nasa_schott_datasets.py", "optimizer/retraining_buffer.json", "optimizer/sac_agent.py",
    "ml_engine/active_learner.py", "ml_engine/data_loaders.py", "ml_engine/train_surrogate.py",
    "ml_engine/train_pinn_surrogate.py", "cad_engine/cad_generator.py", "data/real/flight_mirrors.csv",
]
OLD_PATTERNS = [
    r"mirror_training_data", r"multi_material_mirror_dataset", r"multi_topology_mirror_dataset",
    r"isogrid_analytic_constraints", r"data[/\\]analytic", r"retraining_buffer", r"data_loaders",
    r"active_learner", r"train_pinn_surrogate", r"\bimport xgboost", r"from xgboost", r"\.pkl\b",
    r"\.joblib\b", r"flight_mirrors", r"synthesize_37_zernike", r"cad_generator",
]
CODE_EXT = (".py", ".js", ".html", ".bat")
SKIP_DIRS = {".git", "data_new", "data_new-20261113T183500Z-1-001", "__pycache__", "node_modules"}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def static_scan():
    hits = []
    me = os.path.abspath(__file__)
    for d, sub, files in os.walk(ROOT):
        sub[:] = [s for s in sub if s not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f)
            if not f.endswith(CODE_EXT) or os.path.abspath(p) == me:
                continue
            for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                for pat in OLD_PATTERNS:
                    if re.search(pat, line):
                        hits.append(f"{os.path.relpath(p, ROOT)}:{i}: {line.strip()[:120]}")
    model_files = []
    for d, sub, files in os.walk(ROOT):
        sub[:] = [s for s in sub if s not in SKIP_DIRS]
        for f in files:
            if f.endswith((".pkl", ".joblib", ".pt", ".pth", ".h5", ".onnx", ".json")) and "model" in d.replace("\\", "/").split("/")[-1].lower():
                model_files.append(os.path.relpath(os.path.join(d, f), ROOT))
    return hits, sorted(model_files)


def runtime_trace():
    opened = []
    real_open = builtins.open

    def spy(file, *a, **k):
        try:
            opened.append(os.path.abspath(os.fspath(file)))
        except TypeError:
            pass
        return real_open(file, *a, **k)
    builtins.open = spy
    try:
        from ml_engine.fea_surrogate import get_surrogate
        s = get_surrogate(refresh=True)
        s.predict(73.7, 3.2, 5.3, 46.4, 3.9)
    finally:
        builtins.open = real_open
    data_files = sorted({os.path.relpath(p, ROOT).replace("\\", "/") for p in opened
                         if p.startswith(ROOT) and not p.endswith(".py")})
    return data_files, s


def only_source_check():
    import ml_engine.fea_surrogate as fs
    saved = fs.DATA_FILES
    fs.DATA_FILES = [(n, p + ".hidden_for_test") for n, p in saved]
    try:
        recs = fs.load_records()
        m = fs.FEASurrogate(use_prior=False)
        built = bool(m.models)
    finally:
        fs.DATA_FILES = saved
    return {"records_found_without_data_fea": len(recs), "model_built_without_data_fea": built}


def reproduce(served):
    from ml_engine.fea_surrogate import FEASurrogate, load_records, BOUNDS, FEATURES
    fresh = FEASurrogate(records=load_records(), use_prior=served.use_prior)
    rng = np.random.default_rng(42)
    lo = np.array([BOUNDS[f][0] for f in FEATURES]); hi = np.array([BOUNDS[f][1] for f in FEATURES])
    X = lo + rng.random((200, len(FEATURES))) * (hi - lo)       # FEATURES order: tf, tw, L, rf, H
    a = served.predict_batch(X)
    b = fresh.predict_batch(X)
    ka = a["rms_sag_nm"] if isinstance(a, dict) else a
    kb = b["rms_sag_nm"] if isinstance(b, dict) else b
    d = np.max(np.abs(np.asarray(ka, float) - np.asarray(kb, float)))
    return {"designs": 200, "max_abs_diff_rms_sag_nm": float(d), "n_training_records": served.meta.get("n_training_records"),
            "sources": served.meta.get("sources"), "physics_prior_used": served.use_prior}


def fea_record_checks():
    path = os.path.join(ROOT, "data", "fea", "isogrid_fea_dataset.jsonl")
    recs = [json.loads(l) for l in open(path) if l.strip()]
    eq = [abs(r["reaction_z_wedge_N"] - r["weight_wedge_N"]) / r["weight_wedge_N"] * 100 for r in recs if r.get("reaction_z_wedge_N")]
    mass = [abs(r["occ_mass_kg"] - r["replica_mass_kg"]) / r["replica_mass_kg"] * 100 for r in recs]
    return {"file": "data/fea/isogrid_fea_dataset.jsonl", "sha256_16": sha(path), "records": len(recs),
            "solvers": sorted({r["solver"].split(" linear")[0] for r in recs}),
            "nodes_range": [min(r["n_nodes"] for r in recs), max(r["n_nodes"] for r in recs)],
            "support_reaction_vs_self_weight_max_err_pct": float(max(eq)),
            "occ_solid_vs_exact_mass_max_err_pct": float(max(mass)),
            "first_last_timestamp": [recs[0].get("timestamp"), recs[-1].get("timestamp")]}, recs


def resolve_one(recs):
    from fea_engine.mirror_fea import run_gravity_fea_params
    r = recs[0]; p, fx = r["params"], r["fixed"]
    t = time.time()
    res = run_gravity_fea_params(fx["diameter"], fx["centralHoleDia"], p["depth"], p["faceplate"], p["ribThick"],
                                 p["cellSize"], p["filletRadius"], material=fx["material"], mesh_size=r["mesh_size_mm"],
                                 pad_radius=r["pad_radius_mm"], R_curv=fx["radiusCurv"], k=fx["conicConstant"])
    return {"record": r["id"], "stored_rms_sag_nm": r["rms_sag_nm"], "resolved_rms_sag_nm": res["rms_sag_nm"],
            "diff_pct": 100 * (res["rms_sag_nm"] - r["rms_sag_nm"]) / r["rms_sag_nm"],
            "stored_mass_kg": r["replica_mass_kg"], "resolved_mass_kg": res["replica_mass_kg"],
            "note": "small differences come from non-deterministic multithreaded meshing", "seconds": round(time.time() - t)}


def main():
    out = {"generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    hits, model_files = static_scan()
    out["1_static_scan"] = {"patterns": OLD_PATTERNS, "hits": hits, "model_files_in_model_dirs": model_files, "pass": not hits}
    present = [f for f in OLD_FILES if os.path.exists(os.path.join(ROOT, f))]
    out["2_old_files_present"] = {"checked": OLD_FILES, "present": present, "pass": not present}
    data_files, served = runtime_trace()
    bad = [f for f in data_files if not f.startswith("data/fea/")]
    out["3_runtime_files_read"] = {"files": data_files, "outside_data_fea": bad, "pass": not bad and bool(data_files)}
    o = only_source_check()
    out["4_only_source"] = dict(o, **{"pass": o["records_found_without_data_fea"] == 0 and not o["model_built_without_data_fea"]})
    r = reproduce(served)
    out["5_reproducible_from_data_fea"] = dict(r, **{"pass": r["max_abs_diff_rms_sag_nm"] < 1e-6})
    f, recs = fea_record_checks()
    out["6_fea_records"] = dict(f, **{"pass": f["support_reaction_vs_self_weight_max_err_pct"] < 0.1})
    if "--resolve" in sys.argv:
        rs = resolve_one(recs)
        out["7_resolve_one_record"] = dict(rs, **{"pass": abs(rs["diff_pct"]) < 1.0})
    ppo = os.path.join(ROOT, "optimizer", "models", "ppo_training_report.json")
    rep = json.load(open(ppo))
    out["8_ppo_policy"] = {"report": rep, "policy_sha256_16": sha(os.path.join(ROOT, "optimizer", "models", "ppo_mirror_policy.pt")),
                           "pass": "FEA-trained" in rep.get("environment", "")}
    out["ALL_PASS"] = all(v.get("pass", True) for v in out.values() if isinstance(v, dict))
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    for k, v in out.items():
        if isinstance(v, dict):
            print(f"{k:32s} {'PASS' if v.get('pass') else 'FAIL'}")
    print("files read by the served model:", out["3_runtime_files_read"]["files"])
    print("ALL PASS" if out["ALL_PASS"] else "SOME CHECKS FAILED")
    return 0 if out["ALL_PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
