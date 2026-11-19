"""
Genuine finite-element gravity-sag analysis of the exact NX mirror geometry
==========================================================================

Pipeline (no closed-form shortcuts, no calibration constants):

  1. Geometry  - the app's NX Open journal is executed by cad_engine/journal_replica.py,
                 which records the exact blank profile, every pocket prism (polygon +
                 extrude height) and the wall-restore rings.  The same operations are
                 rebuilt here with the OpenCascade kernel (via gmsh) - the same class of
                 B-rep kernel operations NX/Parasolid performs.
  2. Symmetry  - the journal's pocket lattice has a rib mid-point at the origin, so the
                 pocket layout is mirror-symmetric about the X and Y axes (C2v), and the 18
                 Hindle hubs (C6v) are too.  A 90-degree quarter model with two mirror planes
                 is therefore exact for the axial-gravity load case.
  3. Mesh      - 10-node quadratic tetrahedra (C3D10, same element family as NX
                 Nastran CTETRA10).
  4. Solve     - CalculiX (open-source FE solver, Abaqus-compatible input), linear static,
                 1 g gravity along the optical axis, mirror resting on 18 axial pads at the
                 rib-node hubs on the back face (whiffletree point supports).
  5. Optics    - normal surface deflection of the optical face is mirrored to the full
                 aperture, piston/tilt (and optionally power) removed, RMS/PV computed and
                 37 Fringe Zernike coefficients fitted by least squares.

Units inside the solver: mm, N, tonne, s  (E in MPa, rho in t/mm^3, g = 9810 mm/s^2).
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cad_engine.journal_replica import replica_mass, conic_z  # noqa: E402
from ml_engine.zernike_decomposition import evaluate_fringe_zernike_term  # noqa: E402

WEDGE_DEG = 90.0  # quarter model: the journal's pocket lattice is C2v-symmetric (rib midpoint at origin)
G_MM_S2 = 9806.65

# Engineering constants per material (E in MPa).  Same table the app uses.
MATERIALS = {
    "zerodur": {"E": 90300.0, "nu": 0.24, "rho": 2530.0},
    "ule": {"E": 67600.0, "nu": 0.17, "rho": 2210.0},
    "sic": {"E": 420000.0, "nu": 0.14, "rho": 3160.0},
    "beryllium": {"E": 303000.0, "nu": 0.08, "rho": 1850.0},
    "fused_silica": {"E": 72700.0, "nu": 0.17, "rho": 2200.0},
}


# ----------------------------------------------------------------------------------
# Support hub positions - identical logic to the NX journal (Hindle equal-area radii,
# snapped to isogrid rib intersection nodes)
# ----------------------------------------------------------------------------------

def hindle_18_hubs(D, L, Dc):
    from optimizer.node_snapping import snap_18_whiffletree_hubs
    return [tuple(h) for h in snap_18_whiffletree_hubs(D, L, Dc)]


# ----------------------------------------------------------------------------------
# Geometry (OpenCascade via gmsh)
# ----------------------------------------------------------------------------------

def _in_wedge_bbox(poly, R, margin=1.0):
    """Exact test: does the pocket footprint overlap the 0..30 deg wedge sector?"""
    from shapely.geometry import Polygon
    w = math.radians(WEDGE_DEG)
    n = 64
    sector = [(0.0, 0.0)] + [((R + 50) * math.cos(w * i / n), (R + 50) * math.sin(w * i / n)) for i in range(n + 1)]
    return Polygon(poly).buffer(margin).intersects(Polygon(sector))


def build_wedge_model(details, mesh_size=5.0, min_size=None, order=2, verbose=False, hubs=None, pad_radius=6.0, pad_mesh=1.2):
    """Create the 30-deg wedge solid with gmsh/OCC and mesh it. Returns mesh dict."""
    import gmsh

    ns = details["namespace"]
    R = float(ns["RADIUS"])
    rh = float(ns["CENTRAL_HOLE_DIA"]) / 2.0
    H = float(ns["TOTAL_DEPTH"])
    Rc, k = float(ns["R_CURV"]), float(ns["CONIC_CONSTANT"])
    w = math.radians(WEDGE_DEG)

    gmsh.initialize(interruptible=False)   # safe inside server worker threads
    gmsh.option.setNumber("General.Terminal", 1 if verbose else 0)
    gmsh.model.add("mirror_wedge")
    occ = gmsh.model.occ

    # Blank profile in the XZ plane, revolved 30 degrees about Z
    n_sp = 51
    pts = []
    for i in range(n_sp):
        r = rh + (R - rh) * i / (n_sp - 1)
        pts.append(occ.addPoint(r, 0, conic_z(r, Rc, k)))
    sp = occ.addBSpline(pts) if False else occ.addSpline(pts)
    p_back_out = occ.addPoint(R, 0, -H)
    p_back_in = occ.addPoint(rh, 0, -H)
    l1 = occ.addLine(pts[-1], p_back_out)
    l2 = occ.addLine(p_back_out, p_back_in)
    l3 = occ.addLine(p_back_in, pts[0])
    loop = occ.addCurveLoop([sp, l1, l2, l3])
    surf = occ.addPlaneSurface([loop])
    rev = occ.revolve([(2, surf)], 0, 0, 0, 0, 0, 1, w)
    blank = [e for e in rev if e[0] == 3]

    # Pocket prisms touching the wedge
    tools = []
    for p in details["pockets"]:
        poly = p["poly"]
        if not _in_wedge_bbox(poly, R):
            continue
        z0 = p["z_lo"]
        ptags = [occ.addPoint(x, y, z0) for (x, y) in poly]
        ltags = [occ.addLine(ptags[i], ptags[(i + 1) % len(ptags)]) for i in range(len(ptags))]
        cl = occ.addCurveLoop(ltags)
        s = occ.addPlaneSurface([cl])
        ex = occ.extrude([(2, s)], 0, 0, p["z_hi"] - p["z_lo"])
        tools += [e for e in ex if e[0] == 3]
    if tools:
        body, _ = occ.cut(blank, tools, removeObject=True, removeTool=True)
    else:
        body = blank

    # Wall-restore rings (re-united full-height bands, exactly as the journal does)
    rings = []
    for (a, b) in details.get("restored_bands", []):
        q = []
        for i in range(11):
            r = a + (b - a) * i / 10.0
            q.append(occ.addPoint(r, 0, conic_z(r, Rc, k)))
        s2 = occ.addSpline(q)
        pb1 = occ.addPoint(b, 0, -H)
        pb2 = occ.addPoint(a, 0, -H)
        ll1 = occ.addLine(q[-1], pb1)
        ll2 = occ.addLine(pb1, pb2)
        ll3 = occ.addLine(pb2, q[0])
        lp = occ.addCurveLoop([s2, ll1, ll2, ll3])
        sf = occ.addPlaneSurface([lp])
        rv = occ.revolve([(2, sf)], 0, 0, 0, 0, 0, 1, w)
        rings += [e for e in rv if e[0] == 3]
    if rings:
        body, _ = occ.fuse(body, rings)
    occ.synchronize()
    vols = gmsh.model.getEntities(3)
    vol_wedge = sum(occ.getMass(3, v[1]) for v in vols)

    # Local refinement around every support pad (removes point-support mesh dependence)
    if hubs:
        fids = []
        for (hx, hy) in hubs:
            f_id = gmsh.model.mesh.field.add("Box")
            gmsh.model.mesh.field.setNumber(f_id, "VIn", pad_mesh)
            gmsh.model.mesh.field.setNumber(f_id, "VOut", mesh_size)
            gmsh.model.mesh.field.setNumber(f_id, "XMin", hx - pad_radius - 2)
            gmsh.model.mesh.field.setNumber(f_id, "XMax", hx + pad_radius + 2)
            gmsh.model.mesh.field.setNumber(f_id, "YMin", hy - pad_radius - 2)
            gmsh.model.mesh.field.setNumber(f_id, "YMax", hy + pad_radius + 2)
            gmsh.model.mesh.field.setNumber(f_id, "ZMin", -H - 1)
            gmsh.model.mesh.field.setNumber(f_id, "ZMax", -H + 2 * pad_radius)
            gmsh.model.mesh.field.setNumber(f_id, "Thickness", 4 * pad_radius)
            fids.append(f_id)
        fmin = gmsh.model.mesh.field.add("Min")
        gmsh.model.mesh.field.setNumbers(fmin, "FieldsList", fids)
        gmsh.model.mesh.field.setAsBackgroundMesh(fmin)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
    gmsh.option.setNumber("Mesh.MeshSizeMin", min_size if min_size else min(pad_mesh, mesh_size * 0.25))
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT
    gmsh.option.setNumber("Mesh.ElementOrder", order)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
    gmsh.option.setNumber("General.NumThreads", os.cpu_count() or 2)
    gmsh.model.mesh.generate(3)

    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    coords = coords.reshape(-1, 3)
    etype = 11 if order == 2 else 4
    ets, etags, enodes = gmsh.model.mesh.getElements(3)
    conn = None
    for t, tg, nd in zip(ets, etags, enodes):
        if t == etype:
            conn = np.array(nd, dtype=np.int64).reshape(-1, 10 if order == 2 else 4)
    gmsh.finalize()
    return {"node_tags": np.array(node_tags, dtype=np.int64), "coords": coords, "conn": conn,
            "volume_wedge_mm3": vol_wedge, "R": R, "rh": rh, "H": H, "Rc": Rc, "k": k}


# ----------------------------------------------------------------------------------
# CalculiX deck, solve, parse
# ----------------------------------------------------------------------------------

def _write_inp(path, mesh, mat, hubs, pad_radius, solver="SPOOLES"):
    tags, X, conn = mesh["node_tags"], mesh["coords"], mesh["conn"]
    H = mesh["H"]
    w = math.radians(WEDGE_DEG)
    tol = 1e-4
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    on_p0 = np.abs(y) < tol
    on_p30 = np.abs(x) < tol   # second mirror plane x = 0
    on_back = np.abs(z + H) < 1e-4
    pad = np.zeros(len(tags), bool)
    pads_used = 0
    for (hx, hy) in hubs:
        sel = on_back & (np.hypot(x - hx, y - hy) <= pad_radius)
        if sel.any():
            pad |= sel
            pads_used += 1
    if pads_used == 0:
        raise RuntimeError("No support pad nodes found in wedge")
    with open(path, "w") as f:
        f.write("*HEADING\nMirror quarter model, 1g axial gravity, 18-pt pad supports\n*NODE, NSET=NALL\n")
        for t, (a, b, c) in zip(tags, X):
            f.write(f"{t},{a:.9g},{b:.9g},{c:.9g}\n")
        f.write("*ELEMENT, TYPE=C3D10, ELSET=EALL\n")
        perm = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]
        for i, e in enumerate(conn, start=1):
            f.write(f"{i}," + ",".join(str(int(e[p])) for p in perm) + "\n")

        def nset(name, mask):
            ids = tags[mask]
            f.write(f"*NSET, NSET={name}\n")
            for j in range(0, len(ids), 12):
                f.write(",".join(str(int(v)) for v in ids[j:j + 12]) + ",\n")
        nset("SYM0", on_p0)
        nset("SYM90", on_p30)
        nset("PADS", pad)
        f.write(f"*MATERIAL, NAME=MIRRORMAT\n*ELASTIC\n{mat['E']},{mat['nu']}\n*DENSITY\n{mat['rho']*1e-12:.6e}\n")
        f.write("*SOLID SECTION, ELSET=EALL, MATERIAL=MIRRORMAT\n")
        f.write("*BOUNDARY\nSYM0,2,2\nSYM90,1,1\nPADS,3,3\n")
        f.write(f"*STEP\n*STATIC, SOLVER={solver}\n")
        f.write(f"*DLOAD\nEALL,GRAV,{G_MM_S2},0.,0.,-1.\n")
        f.write("*NODE FILE, OUTPUT=3D\nU\n*NODE PRINT, NSET=PADS, TOTALS=ONLY\nRF\n*END STEP\n")
    return int(pad.sum()), pads_used


def _read_frd_disp(path):
    disp = {}
    with open(path) as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("    1PSTEP") or (lines[i].startswith(" -4  DISP")):
            if lines[i].startswith(" -4  DISP"):
                i += 1
                while i < len(lines) and lines[i].startswith(" -5"):
                    i += 1
                while i < len(lines) and lines[i].startswith(" -1"):
                    s = lines[i]
                    nid = int(s[3:13])
                    vals = [float(s[13 + 12 * j: 25 + 12 * j]) for j in range(3)]
                    disp[nid] = vals
                    i += 1
                break
        i += 1
    return disp


def _read_reaction(dat_path):
    try:
        txt = open(dat_path).read().split("total force")[-1].split("\n")
        for ln in txt[1:6]:
            p = ln.split()
            if len(p) >= 3:
                return [float(v) for v in p[-3:]]
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------------------
# Siemens NX Nastran (Simcenter Nastran) path - same mesh, same loads, NX solver
# ----------------------------------------------------------------------------------

NASTRAN_CANDIDATES = [
    os.environ.get("NX_NASTRAN_EXE", ""),
    r"C:\Program Files\Siemens\NX2007\NXNASTRAN\bin\nastran.exe",
    r"C:\Program Files\Siemens\Simcenter3D_2306\NXNASTRAN\bin\nastran.exe",
    r"C:\Program Files\Siemens\Simcenter Nastran\bin\nastran.exe",
]


def find_nastran():
    import glob
    cands = [c for c in NASTRAN_CANDIDATES if c]
    cands += glob.glob(r"C:\Program Files\Siemens\*\NXNASTRAN\bin\nastran.exe")
    for c in cands:
        if c and os.path.exists(c):
            return c
    return shutil.which("nastran")


def _f16(v):
    s = f"{v:16.9E}"
    return s if len(s) <= 16 else f"{v:16.8E}"


def write_bdf(path, mesh, mat, hubs, pad_radius):
    """Write a Nastran SOL 101 bulk-data deck of the quarter model (mm-N-tonne units)."""
    tags, X, conn = mesh["node_tags"], mesh["coords"], mesh["conn"]
    H = mesh["H"]
    tol = 1e-4
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    on_p0 = np.abs(y) < tol
    on_p90 = np.abs(x) < tol
    on_back = np.abs(z + H) < 1e-4
    pad = np.zeros(len(tags), bool)
    for (hx, hy) in hubs:
        pad |= on_back & (np.hypot(x - hx, y - hy) <= pad_radius)
    with open(path, "w") as f:
        f.write("SOL 101\nCEND\nTITLE = MIRROR QUARTER MODEL 1G AXIAL GRAVITY 18-PT PADS\n")
        f.write("ECHO = NONE\nSUBCASE 1\n  SPC = 1\n  LOAD = 2\n  DISPLACEMENT(PRINT,PLOT) = ALL\n  SPCFORCES(PRINT) = ALL\n")
        f.write("BEGIN BULK\nPARAM,POST,-1\nPARAM,AUTOSPC,YES\n")
        f.write(f"MAT1,1,{float(mat['E']):.6E},,{mat['nu']:.4f},{mat['rho']*1e-12:.6E}\n")
        f.write("PSOLID,1,1\n")
        f.write(f"GRAV,2,,{G_MM_S2:.5f},0.,0.,-1.\n")
        for t, (a, b, c) in zip(tags, X):
            f.write(f"{'GRID*':<8}{int(t):>16}{'':>16}{_f16(a)}{_f16(b)}\n{'*':<8}{_f16(c)}\n")
        for i, e in enumerate(conn, start=1):
            g = [int(e[p]) for p in [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]]
            f.write(f"{'CTETRA':<8}{i:>8}{1:>8}" + "".join(f"{v:>8}" for v in g[:6]) + "\n")
            f.write(" " * 8 + "".join(f"{v:>8}" for v in g[6:]) + "\n")
        for t in tags[on_p0]:
            f.write(f"SPC1,1,2,{int(t)}\n")
        for t in tags[on_p90]:
            f.write(f"SPC1,1,1,{int(t)}\n")
        for t in tags[pad]:
            f.write(f"SPC1,1,3,{int(t)}\n")
        f.write("ENDDATA\n")
    return int(pad.sum())


def read_f06_displacements(path):
    disp = {}
    in_tab = False
    with open(path, errors="ignore") as f:
        for ln in f:
            if "D I S P L A C E M E N T   V E C T O R" in ln:
                in_tab = True
                continue
            if in_tab:
                p = ln.split()
                if len(p) >= 8 and p[1] == "G":
                    try:
                        disp[int(p[0])] = [float(p[2].replace("D", "E")), float(p[3].replace("D", "E")), float(p[4].replace("D", "E"))]
                    except ValueError:
                        pass
                elif ln.startswith("1") and "PAGE" not in ln and len(p) > 0 and p[0] != "POINT":
                    pass
                if "S P C" in ln or "F O R C E S" in ln or "E L E M E N T" in ln:
                    in_tab = False
    return disp


def run_nastran(wd, mesh, mat, hubs, pad_radius, exe):
    bdf = os.path.join(wd, "mirror_nastran.bdf")
    write_bdf(bdf, mesh, mat, hubs, pad_radius)
    res = subprocess.run([exe, "mirror_nastran.bdf", "scr=yes", "old=no", "batch=no", "news=no"],
                         cwd=wd, capture_output=True, text=True)
    f06 = os.path.join(wd, "mirror_nastran.f06")
    if not os.path.exists(f06):
        raise RuntimeError("NX Nastran produced no .f06:\n" + res.stdout[-2000:] + res.stderr[-2000:])
    txt = open(f06, errors="ignore").read()
    if "FATAL" in txt:
        raise RuntimeError("NX Nastran FATAL message - see " + f06)
    return read_f06_displacements(f06)


# ----------------------------------------------------------------------------------
# Optical post-processing
# ----------------------------------------------------------------------------------

def _fringe_basis(rho, th, nterms=37):
    return np.column_stack([evaluate_fringe_zernike_term(j, rho, th) for j in range(1, nterms + 1)])


def optical_metrics(front_xyz, w_normal, R, rh, grid=241):
    """Mirror quarter-model data to full aperture (C2v), resample on a uniform grid, fit Zernikes."""
    x, y = front_xyz[:, 0], front_xyz[:, 1]
    X = np.concatenate([x, -x, x, -x])
    Y = np.concatenate([y, y, -y, -y])
    ww = np.concatenate([w_normal] * 4)
    return optical_metrics_points(X, Y, ww, R, rh, grid=grid)


def optical_metrics_points(X, Y, ww, R, rh, grid=241):
    """Optical metrics of a full-aperture surface deflection sampled at scattered points
    (FEA nodes): linear interpolation onto a uniform grid over the annulus rh..R, then
    least-squares Fringe Zernike fit and piston/tilt (and power) removal. Units in = units out.
    grid=None fits directly at the given points (no interpolation; used for verification)."""
    if grid is None:
        gx, gy, W = np.asarray(X, float), np.asarray(Y, float), np.asarray(ww, float)
    else:
        from scipy.interpolate import LinearNDInterpolator
        interp = LinearNDInterpolator(np.column_stack([X, Y]), ww)
        g = np.linspace(-R, R, grid)
        GX, GY = np.meshgrid(g, g)
        GR = np.hypot(GX, GY)
        m = (GR <= R * 0.999) & (GR >= rh * 1.001)
        W = interp(GX[m], GY[m])
        ok = ~np.isnan(W)
        gx, gy, W = GX[m][ok], GY[m][ok], W[ok]
    rho = np.hypot(gx, gy) / R
    th = np.arctan2(gy, gx)
    B = _fringe_basis(rho, th)
    coef, *_ = np.linalg.lstsq(B, W, rcond=None)
    # residual after piston + tilt removal
    ptt = B[:, :3] @ np.linalg.lstsq(B[:, :3], W, rcond=None)[0]
    w_ptt = W - ptt
    pttf = B[:, :4] @ np.linalg.lstsq(B[:, :4], W, rcond=None)[0]
    w_pttf = W - pttf
    return {
        "rms_sag_nm": float(np.sqrt(np.mean(w_ptt ** 2))),
        "pv_sag_nm": float(w_ptt.max() - w_ptt.min()),
        "rms_sag_power_removed_nm": float(np.sqrt(np.mean(w_pttf ** 2))),
        "pv_sag_power_removed_nm": float(w_pttf.max() - w_pttf.min()),
        "mean_deflection_nm": float(np.mean(W)),
        "zernike_fringe_37_nm": [float(c) for c in coef],
        "zernike_fit_residual_rms_nm": float(np.sqrt(np.mean((W - B @ coef) ** 2))),
        "n_grid_points": int(len(W)),
    }


# ----------------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------------

def run_gravity_fea(journal_code, material="zerodur", mesh_size=6.0, pad_radius=None,
                    workdir=None, keep_files=False, verbose=False, solver_backend="calculix"):
    """solver_backend: 'calculix' | 'nastran' (Siemens NX Nastran, if installed) | 'auto'."""
    t0 = time.time()
    mat = MATERIALS[material]
    if isinstance(journal_code, dict):          # pre-built geometry details (from parameters)
        rep = journal_code
        journal_code = ""
    else:
        rep = replica_mass(journal_code, return_details=True)
    ns = rep["namespace"]
    D = 2.0 * float(ns["RADIUS"])
    L = float(ns["CELL_SIDE"])
    Dc = float(ns["CENTRAL_HOLE_DIA"])
    hubs = hindle_18_hubs(D, L, Dc)
    w = math.radians(WEDGE_DEG)
    hubs_wedge = [(hx, hy) for (hx, hy) in hubs
                  if -1e-6 <= math.atan2(hy, hx) <= w + 1e-6]

    if pad_radius is None:
        # support pad footprint = HUB_OUTER_R written in the journal (6 mm for 18-point)
        pad_radius = 6.0
        for ln in journal_code.splitlines():
            if ln.strip().startswith("HUB_OUTER_R"):
                try:
                    pad_radius = float(ln.split("=")[1].split("#")[0])
                except Exception:
                    pass
    mesh = build_wedge_model(rep, mesh_size=mesh_size, verbose=verbose, hubs=hubs_wedge, pad_radius=pad_radius)
    t_mesh = time.time() - t0

    wd = workdir or tempfile.mkdtemp(prefix="mirror_fea_")
    os.makedirs(wd, exist_ok=True)
    inp = os.path.join(wd, "mirror.inp")
    nastran_exe = find_nastran() if solver_backend in ("nastran", "auto") else None
    if solver_backend == "nastran" and not nastran_exe:
        raise RuntimeError("NX Nastran executable not found (set NX_NASTRAN_EXE)")
    if nastran_exe:
        solver = "NX Nastran SOL 101"
        disp = run_nastran(wd, mesh, mat, hubs_wedge, pad_radius, nastran_exe)
        n_pad_nodes, pads_used = write_bdf(os.path.join(wd, "check.bdf"), mesh, mat, hubs_wedge, pad_radius), len(hubs_wedge)
        reaction = None
        t_solve = time.time() - t0 - t_mesh
    else:
        # direct sparse solver for normal meshes; memory-lean iterative Cholesky for very large ones
        solver = "SPOOLES" if len(mesh["node_tags"]) <= 200000 else "ITERATIVE CHOLESKY"
        n_pad_nodes, pads_used = _write_inp(inp, mesh, mat, hubs_wedge, pad_radius, solver)
        env = dict(os.environ, OMP_NUM_THREADS=str(os.cpu_count() or 2))
        ccx = os.environ.get("CCX_EXE") or shutil.which("ccx") or shutil.which("ccx.exe") or "ccx"
        res = subprocess.run([ccx, "-i", "mirror"], cwd=wd, capture_output=True, text=True, env=env)
        if (res.returncode != 0 or not os.path.exists(os.path.join(wd, "mirror.frd"))) and solver == "SPOOLES":
            solver = "ITERATIVE CHOLESKY"
            _write_inp(inp, mesh, mat, hubs_wedge, pad_radius, solver)
            res = subprocess.run([ccx, "-i", "mirror"], cwd=wd, capture_output=True, text=True, env=env)
        if res.returncode != 0 or not os.path.exists(os.path.join(wd, "mirror.frd")):
            raise RuntimeError("CalculiX failed:\n" + res.stdout[-3000:] + res.stderr[-2000:])
        disp = _read_frd_disp(os.path.join(wd, "mirror.frd"))
        reaction = _read_reaction(os.path.join(wd, "mirror.dat"))
        t_solve = time.time() - t0 - t_mesh
        solver = "CalculiX " + solver

    tags, X = mesh["node_tags"], mesh["coords"]
    U = np.array([disp.get(int(t), [np.nan] * 3) for t in tags])
    r = np.hypot(X[:, 0], X[:, 1])
    zf = np.array([conic_z(v, mesh["Rc"], mesh["k"]) for v in r])
    front = np.abs(X[:, 2] - zf) < 2e-3
    # surface normal of z = f(r): n = (-f' r_hat, 1)/sqrt(1+f'^2)
    eps = 1e-3
    fp = np.array([(conic_z(v + eps, mesh["Rc"], mesh["k"]) - conic_z(max(v - eps, 0.0), mesh["Rc"], mesh["k"])) / (2 * eps) for v in r[front]])
    rx = X[front, 0] / np.maximum(r[front], 1e-9)
    ry = X[front, 1] / np.maximum(r[front], 1e-9)
    nz = 1.0 / np.sqrt(1 + fp ** 2)
    nx_, ny_ = -fp * rx * nz, -fp * ry * nz
    Uf = U[front]
    w_mm = Uf[:, 0] * nx_ + Uf[:, 1] * ny_ + Uf[:, 2] * nz
    opt = optical_metrics(X[front], w_mm * 1e6, mesh["R"], mesh["rh"])

    vol_full = mesh["volume_wedge_mm3"] * (360.0 / WEDGE_DEG)
    out = {
        "solver": solver + " linear static, 10-node tetra (C3D10/CTETRA10), C2v quarter model",
        "load_case": "1 g gravity along optical axis (-Z), face up, 18-point axial pad supports",
        "material": material,
        "E_MPa": mat["E"], "nu": mat["nu"], "rho_kg_m3": mat["rho"],
        "mesh_size_mm": mesh_size, "pad_radius_mm": pad_radius,
        "n_nodes": int(len(tags)), "n_elements": int(len(mesh["conn"])),
        "n_front_nodes": int(front.sum()), "n_pad_nodes": n_pad_nodes, "pads_in_wedge": pads_used,
        "occ_volume_full_mm3": vol_full,
        "occ_mass_kg": vol_full * mat["rho"] * 1e-9,
        "replica_volume_mm3": rep["volume_mm3"],
        "replica_mass_kg": rep["volume_mm3"] * mat["rho"] * 1e-9,
        "reaction_z_wedge_N": (reaction[2] if reaction else None),
        "weight_wedge_N": mesh["volume_wedge_mm3"] * mat["rho"] * 1e-12 * G_MM_S2,
        "max_abs_uz_nm": float(np.nanmax(np.abs(U[:, 2])) * 1e6),
        "time_mesh_s": round(t_mesh, 1), "time_solve_s": round(t_solve, 1),
    }
    out.update(opt)
    if not keep_files and workdir is None:
        shutil.rmtree(wd, ignore_errors=True)
    return out


def run_gravity_fea_params(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, material="zerodur",
                           mesh_size=8.0, pad_radius=6.0, R_curv=1085.0, k=-1.22, **kw):
    """FEA directly from design parameters, using the journal-identical isogrid generator."""
    from cad_engine.exact_mass import isogrid_geometry_details
    det = isogrid_geometry_details(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, R_curv, k,
                                   MATERIALS[material]["rho"])
    return run_gravity_fea(det, material=material, mesh_size=mesh_size, pad_radius=pad_radius, **kw)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("journal")
    ap.add_argument("--material", default="zerodur")
    ap.add_argument("--mesh", type=float, default=6.0)
    ap.add_argument("--pad", type=float, default=None)
    a = ap.parse_args()
    res = run_gravity_fea(open(a.journal, encoding="utf-8").read(), a.material, a.mesh, a.pad, verbose=False)
    res.pop("zernike_fringe_37_nm", None)
    print(json.dumps(res, indent=1))
