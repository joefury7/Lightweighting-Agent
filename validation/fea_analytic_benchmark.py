"""
FE pipeline verification against a closed-form plate solution (Timoshenko & Woinowsky-Krieger).

Solid circular plate, radius a, thickness h, uniform self-weight q = rho*g*h, simply supported
along the full outer edge (mid-plane).  Centre deflection (thin-plate, Kirchhoff):
    w0 = (5 + nu) q a^4 / (64 (1 + nu) D),   D = E h^3 / (12 (1 - nu^2))
plus Mindlin shear correction for moderately thick plates:
    w_shear = q a^2 / (4 kappa G h) ... (centre, kappa = 5/6)
Uses the same quarter-model, C3D10 element, gravity load and CalculiX solver as mirror_fea.py.
"""
import math, os, sys, subprocess, tempfile, json
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fea_engine.mirror_fea import _read_frd_disp, G_MM_S2

def run(a=150.0, h=6.0, E=90300.0, nu=0.24, rho=2530.0, mesh=3.0):
    import gmsh
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    occ = gmsh.model.occ
    c = occ.addCylinder(0, 0, -h / 2, 0, 0, h, a, angle=math.pi / 2)
    occ.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh); gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.model.mesh.generate(3)
    tags, X, _ = gmsh.model.mesh.getNodes(); X = X.reshape(-1, 3)
    et, etg, en = gmsh.model.mesh.getElements(3)
    conn = np.array(en[list(et).index(11)], dtype=np.int64).reshape(-1, 10)
    gmsh.finalize()
    wd = tempfile.mkdtemp()
    r = np.hypot(X[:, 0], X[:, 1])
    edge = (np.abs(r - a) < 1e-3) & (np.abs(X[:, 2]) < 1e-6 + 0.0)   # mid-plane edge circle
    if edge.sum() < 3:
        edge = (np.abs(r - a) < 1e-3) & (np.abs(X[:, 2]) <= h / 2 * 0.34)
    with open(os.path.join(wd, "p.inp"), "w") as f:
        f.write("*NODE\n"); [f.write(f"{t},{x:.9g},{y:.9g},{z:.9g}\n") for t, (x, y, z) in zip(tags, X)]
        f.write("*ELEMENT,TYPE=C3D10,ELSET=E\n")
        for i, e in enumerate(conn, 1):
            f.write(f"{i}," + ",".join(str(int(e[p])) for p in [0,1,2,3,4,5,6,7,9,8]) + "\n")
        def ns(n, m):
            f.write(f"*NSET,NSET={n}\n"); [f.write(f"{int(t)},\n") for t in tags[m]]
        ns("S0", np.abs(X[:, 1]) < 1e-6); ns("S90", np.abs(X[:, 0]) < 1e-6); ns("EDGE", edge)
        f.write(f"*MATERIAL,NAME=M\n*ELASTIC\n{E},{nu}\n*DENSITY\n{rho*1e-12}\n*SOLID SECTION,ELSET=E,MATERIAL=M\n")
        f.write("*BOUNDARY\nS0,2,2\nS90,1,1\nEDGE,3,3\n*STEP\n*STATIC\n")
        f.write(f"*DLOAD\nE,GRAV,{G_MM_S2},0.,0.,-1.\n*NODE FILE\nU\n*END STEP\n")
    subprocess.run(["ccx", "-i", "p"], cwd=wd, capture_output=True)
    d = _read_frd_disp(os.path.join(wd, "p.frd"))
    centre = [t for t, (x, y, z) in zip(tags, X) if math.hypot(x, y) < 1e-6 and abs(z) < 1e-6]
    if not centre:
        i0 = np.argmin(np.hypot(X[:, 0], X[:, 1]) + np.abs(X[:, 2])); centre = [tags[i0]]
    w_fe = -d[int(centre[0])][2]
    q = rho * 1e-12 * G_MM_S2 * h
    Dp = E * h ** 3 / (12 * (1 - nu ** 2))
    w_k = (5 + nu) * q * a ** 4 / (64 * (1 + nu) * Dp)
    G = E / (2 * (1 + nu))
    w_s = q * a ** 2 / (4 * (5.0 / 6.0) * G * h)
    return {"a_mm": a, "h_mm": h, "mesh_mm": mesh, "fe_centre_nm": w_fe * 1e6,
            "kirchhoff_nm": w_k * 1e6, "mindlin_nm": (w_k + w_s) * 1e6,
            "error_vs_mindlin_pct": 100 * (w_fe - (w_k + w_s)) / (w_k + w_s)}

if __name__ == "__main__":
    for m in [6.0, 3.0]:
        print(json.dumps(run(mesh=m)))
