"""
Runs every genuine check (no hard-coded PASS):
  1. exact mass: Python == app.js == journal replica (random designs)
  2. replica == OpenCascade B-rep solid volume (one design, full 360 deg)
  3. FE pipeline vs closed-form plate solution
  4. surrogate leave-one-out prediction gap on the FEA dataset
  5. (optional) design unchanged vs an older app.js:  python validation/run_validation.py <old_app.js>
"""
import json, math, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

def occ_volume_check():
    import gmsh
    from cad_engine.exact_mass import isogrid_geometry_details
    from cad_engine.journal_replica import conic_z
    d = isogrid_geometry_details(560, 175, 73.7, 1.5, 1.5, 64.7, 10.0)
    ns = d["namespace"]; R = ns["RADIUS"]; rh = ns["CENTRAL_HOLE_DIA"] / 2; H = ns["TOTAL_DEPTH"]; Rc = ns["R_CURV"]; k = ns["CONIC_CONSTANT"]
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0); occ = gmsh.model.occ
    def ring(a, b, n):
        q = [occ.addPoint(a + (b - a) * i / (n - 1), 0, conic_z(a + (b - a) * i / (n - 1), Rc, k)) for i in range(n)]
        s = occ.addSpline(q); p1 = occ.addPoint(b, 0, -H); p2 = occ.addPoint(a, 0, -H)
        lp = occ.addCurveLoop([s, occ.addLine(q[-1], p1), occ.addLine(p1, p2), occ.addLine(p2, q[0])])
        return [e for e in occ.revolve([(2, occ.addPlaneSurface([lp]))], 0, 0, 0, 0, 0, 1, 2 * math.pi) if e[0] == 3]
    blank = ring(rh, R, 51); tools = []
    for p in d["pockets"]:
        pt = [occ.addPoint(x, y, p["z_lo"]) for x, y in p["poly"]]
        s = occ.addPlaneSurface([occ.addCurveLoop([occ.addLine(pt[i], pt[(i + 1) % len(pt)]) for i in range(len(pt))])])
        tools += [e for e in occ.extrude([(2, s)], 0, 0, p["z_hi"] - p["z_lo"]) if e[0] == 3]
    body, _ = occ.cut(blank, tools); rings = []
    for a, b in d["restored_bands"]:
        rings += ring(a, b, 11)
    occ.fuse(body, rings); occ.synchronize()
    v = sum(occ.getMass(3, e[1]) for e in gmsh.model.getEntities(3)); gmsh.finalize()
    return v, d["volume_mm3"]

def main():
    ok = True
    print("== 1. exact mass Python / JS / journal replica")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "validation", "test_exact_mass.py")], capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1]); ok &= r.returncode == 0
    print("== 2. replica vs OpenCascade solid")
    v_occ, v_rep = occ_volume_check(); err = 100 * (v_occ - v_rep) / v_rep
    print(f"OCC {v_occ:.3f} mm3 vs replica {v_rep:.3f} mm3  ({err:+.2e} %)"); ok &= abs(err) < 1e-4
    print("== 3. FE pipeline vs closed-form plate")
    from validation.fea_analytic_benchmark import run
    b = run(mesh=6.0); print(json.dumps(b)); ok &= abs(b["error_vs_mindlin_pct"]) < 1.0
    print("== 4. surrogate prediction gap (leave-one-out on FEA records)")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "ml_engine", "train_fea_surrogate.py")], capture_output=True, text=True)
    print(r.stdout.strip())
    if len(sys.argv) > 1:
        print("== 5. design unchanged vs", sys.argv[1])
        r = subprocess.run([sys.executable, os.path.join(ROOT, "validation", "test_design_unchanged.py"), sys.argv[1]], capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1]); ok &= r.returncode == 0
    print("\nOVERALL:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
