"""
Guarantee that the NX design did not change: generate journals with an OLD app.js and the CURRENT
app.js for random parameter sets (all 8 patterns) and compare every recorded pocket / revolve.
Usage: python validation/test_design_unchanged.py <path to old app.js>   (e.g. from `git show <commit>:app.js`)
"""
import json, os, random, subprocess, sys, tempfile, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cad_engine.journal_replica import run_journal

def journal(app_js, params):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "tools"))
    shutil.copy(app_js, os.path.join(d, "app.js"))
    shutil.copy(os.path.join(ROOT, "tools", "gen_journal.js"), os.path.join(d, "tools", "gen_journal.js"))
    out = subprocess.run(["node", os.path.join(d, "tools", "gen_journal.js"), json.dumps(params)], capture_output=True, text=True).stdout
    shutil.rmtree(d)
    return out

def signature(code):
    ns, rec = run_journal(code)
    ex = sorted((round(c.StartPoint.X, 6), round(c.StartPoint.Y, 6), round(c.StartPoint.Z, 6), round(e["end"] - e["start"], 6), e["bool"])
                for e in rec.extrudes for c in e["curves"])
    rv = sorted((r["bool"], r["r_min"], r["r_max"]) for r in rec.revolves)
    return ex, rv

def main(old_app, n=12, seed=5):
    rnd = random.Random(seed)
    pats = ["isogrid", "hexagonal", "square", "radial", "hex_radial", "iso_radial", "double_arch", "sandwich_isogrid"]
    bad = 0
    for i in range(n):
        p = {"pattern": pats[i % len(pats)], "cellSize": round(rnd.uniform(40, 90), 1), "ribThick": round(rnd.uniform(1.5, 5), 1),
             "faceplate": round(rnd.uniform(0.8, 3.5), 1), "filletRadius": round(rnd.uniform(1, 5), 1), "depth": round(rnd.uniform(55, 95), 1)}
        a, b = signature(journal(old_app, p)), signature(journal(os.path.join(ROOT, "app.js"), p))
        same = a == b
        bad += not same
        print(f"{p['pattern']:16s} L={p['cellSize']:5} tw={p['ribThick']:4} -> {'IDENTICAL geometry' if same else 'GEOMETRY DIFFERS'} ({len(a[0])} pocket edges)")
    print("RESULT:", "design unchanged" if bad == 0 else f"{bad} differences")
    return bad

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
