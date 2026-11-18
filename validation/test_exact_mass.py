"""Fast exact mass (Python + app.js JavaScript) must equal the journal replica for random designs."""
import json, os, random, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cad_engine.journal_replica import replica_mass
from cad_engine.exact_mass import isogrid_exact_mass

def main(n=25, seed=3):
    rnd = random.Random(seed)
    worst = 0.0
    for i in range(n):
        p = {"diameter": rnd.choice([560.0, 560.0, 500.0, 610.0]), "centralHoleDia": rnd.choice([175.0, 120.0]),
             "depth": round(rnd.uniform(50, 100), 2), "faceplate": round(rnd.uniform(0.8, 4.0), 2),
             "ribThick": round(rnd.uniform(1.5, 5.5), 2), "cellSize": round(rnd.uniform(38, 95), 2),
             "radiusCurv": 1085.0, "conicConstant": -1.22, "pattern": "isogrid", "supportType": "18point", "density": 2530}
        ps = p["cellSize"] - p["ribThick"] * 2 / 3 ** 0.5
        p["filletRadius"] = round(rnd.uniform(1.0, min(10.0, 0.45 * ps / 3 ** 0.5)), 2)
        code = subprocess.run(["node", os.path.join(ROOT, "tools", "gen_journal.js"), json.dumps(p)], capture_output=True, text=True).stdout
        ref = replica_mass(code)["mass_kg"]
        t = time.perf_counter()
        py = isogrid_exact_mass(p["diameter"], p["centralHoleDia"], p["depth"], p["faceplate"], p["ribThick"], p["cellSize"], p["filletRadius"])["mass_kg"]
        dt = (time.perf_counter() - t) * 1000
        js = float(subprocess.run(["node", os.path.join(ROOT, "tools", "exact_mass_cli.js"), json.dumps(p)], capture_output=True, text=True).stdout or "nan")
        err = max(abs(py - ref), abs(js - ref))
        worst = max(worst, err)
        print(f"{i:02d} replica={ref:.6f}  python={py:.6f}  js={js:.6f}  |err|max={err*1000:.4f} g  ({dt:.1f} ms)")
    print(f"WORST |error| = {worst*1000:.4f} g")
    return worst

if __name__ == "__main__":
    w = main()
    sys.exit(0 if w < 1e-3 else 1)
