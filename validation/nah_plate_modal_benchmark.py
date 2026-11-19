"""
External benchmark: our FEA chain (gmsh 10-node tetra C3D10 + CalculiX) against an
independent, published dataset of plate eigenfrequencies computed with COMSOL Multiphysics.

Data
----
Olivieri, Pezzoli, Antonacci, Sarti, "A Physics-Informed Neural Network Approach for
Nearfield Acoustic Holography", Sensors 21(23):7834 (2021), doi:10.3390/s21237834.
Dataset: Zenodo 10.5281/zenodo.5702615 (CC-BY-4.0), file rectangular_simulation_nah.mat.
672 isotropic rectangular plates (Lx 0.23-0.36 m, Ly 0.15-0.22 m, h 2-7 mm), three boundary
conditions (clamped / free / simply supported), every eigenfrequency below 2 kHz.

The .mat stores the boundary condition as a MATLAB `string` object, which scipy cannot read,
so the metadata (plate id, dimensions, mode number, frequency) is extracted to
data/external_validation/nah_plate_meta.npz. The file is ordered in three contiguous blocks
(clamped, free, simply supported); the block boundaries are where `num_plate` restarts at 1.
This assignment is checked independently: the first simply-supported frequency of every plate
matches Kirchhoff thin-plate theory (see `kirchhoff_ss_check`).

The dataset does not state the material. Its simply-supported frequencies are consistent with
aluminium (E = 70 GPa, rho = 2700 kg/m^3, nu = 0.33); we use those nominal values with NO
fitting, so every comparison below is a genuine prediction.

What this validates
-------------------
The mirror gravity analysis uses exactly this chain: gmsh OpenCascade geometry -> second-order
tetrahedra (C3D10) -> CalculiX. Thin facesheets in bending are the governing physics of the
mirror's gravity sag, which is the same stiffness/mass physics that sets plate eigenfrequencies.
Nothing here feeds the surrogate or the optimiser; it is a solver-verification benchmark.
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
META = os.path.join(ROOT, "data", "external_validation", "nah_plate_meta.npz")
OUT = os.path.join(ROOT, "data", "external_validation", "nah_plate_modal_benchmark.json")

AL = {"E": 70000.0, "nu": 0.33, "rho": 2700.0}   # MPa, -, kg/m^3 (nominal aluminium)
FMAX = 2000.0
BC_NAMES = ["clamped", "free", "simply_supported"]


def load_meta():
    z = np.load(META)
    n, d, m, f = z["num_plate"], z["dims"], z["mode"], z["freq"]
    resets = np.where(np.diff(n) < 0)[0]
    if len(resets) != 2:
        raise RuntimeError("Unexpected block structure in NAH metadata")
    bc = np.empty(len(n), dtype=object)
    bc[: resets[0] + 1] = "clamped"
    bc[resets[0] + 1: resets[1] + 1] = "free"
    bc[resets[1] + 1:] = "simply_supported"
    return n, d, m, f, bc


def kirchhoff_ss_check(n, d, m, f, bc):
    """Closed-form f11 for a simply supported Kirchhoff plate vs the dataset's first SS mode."""
    E, nu, rho = AL["E"] * 1e6, AL["nu"], AL["rho"]
    errs = []
    for p in np.unique(n[bc == "simply_supported"]):
        idx = np.where((n == p) & (bc == "simply_supported") & (m == 1))[0]
        if len(idx) == 0:
            continue
        Lx, Ly, h = d[idx[0]]
        D = E * h ** 3 / (12 * (1 - nu ** 2))
        f11 = (math.pi / 2) * (1 / Lx ** 2 + 1 / Ly ** 2) * math.sqrt(D / (rho * h))
        errs.append(100 * (f11 - f[idx[0]]) / f[idx[0]])
    errs = np.abs(errs)
    return {"plates": int(len(errs)), "median_abs_err_pct": float(np.median(errs)),
            "max_abs_err_pct": float(errs.max())}


def ccx_plate_modes(Lx, Ly, h, bc, mesh_mm=None, nmodes=40, verbose=False):
    """Plate eigenfrequencies (Hz) with gmsh C3D10 + CalculiX. Units: mm, MPa, t/mm^3."""
    import gmsh
    Lx, Ly, h = Lx * 1e3, Ly * 1e3, h * 1e3
    if mesh_mm is None:
        mesh_mm = max(2.0 * h, 6.0)
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 1 if verbose else 0)
        gmsh.model.add("plate")
        # two layers so the mid-plane edge lines exist (simply-supported constraint)
        b1 = gmsh.model.occ.addBox(0, 0, -h / 2, Lx, Ly, h / 2)
        b2 = gmsh.model.occ.addBox(0, 0, 0, Lx, Ly, h / 2)
        gmsh.model.occ.fragment([(3, b1)], [(3, b2)])
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_mm)
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_mm * 0.25)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
        gmsh.option.setNumber("General.NumThreads", os.cpu_count() or 2)
        gmsh.model.mesh.generate(3)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        X = xyz.reshape(-1, 3)
        _, conn = gmsh.model.mesh.getElementsByType(11)
        conn = conn.reshape(-1, 10)
    finally:
        gmsh.finalize()
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    tol = 1e-6 * max(Lx, Ly)
    edge = (np.abs(x) < tol) | (np.abs(x - Lx) < tol) | (np.abs(y) < tol) | (np.abs(y - Ly) < tol)
    wd = tempfile.mkdtemp(prefix="nah_")
    try:
        with open(os.path.join(wd, "plate.inp"), "w") as fh:
            fh.write("*NODE, NSET=NALL\n")
            for t, (a, b, c) in zip(tags, X):
                fh.write(f"{int(t)},{a:.9g},{b:.9g},{c:.9g}\n")
            fh.write("*ELEMENT, TYPE=C3D10, ELSET=EALL\n")
            perm = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]
            for i, e in enumerate(conn, start=1):
                fh.write(f"{i}," + ",".join(str(int(e[p])) for p in perm) + "\n")

            def nset(name, mask):
                ids = tags[mask]
                fh.write(f"*NSET, NSET={name}\n")
                for j in range(0, len(ids), 12):
                    fh.write(",".join(str(int(v)) for v in ids[j:j + 12]) + ",\n")
            if bc == "clamped":
                nset("FIX", edge)
            elif bc == "simply_supported":
                nset("FIX", edge & (np.abs(z) < 1e-6 * h + 1e-9))
            fh.write(f"*MATERIAL, NAME=AL\n*ELASTIC\n{AL['E']},{AL['nu']}\n*DENSITY\n{AL['rho']*1e-12:.6e}\n")
            fh.write("*SOLID SECTION, ELSET=EALL, MATERIAL=AL\n")
            if bc != "free":
                fh.write("*BOUNDARY\nFIX,1,3\n")
            fh.write("*STEP\n*FREQUENCY\n")
            # lower bound 1 Hz -> shift away from the six rigid-body modes of the free plate
            fh.write(f"{nmodes},1.,{FMAX*1.15}\n*END STEP\n")
        ccx = os.environ.get("CCX_EXE") or shutil.which("ccx") or "ccx"
        env = dict(os.environ, OMP_NUM_THREADS=str(os.cpu_count() or 2))
        r = subprocess.run([ccx, "-i", "plate"], cwd=wd, capture_output=True, text=True, env=env)
        dat = open(os.path.join(wd, "plate.dat")).read() if os.path.exists(os.path.join(wd, "plate.dat")) else ""
        if r.returncode != 0 or "E I G E N V A L U E" not in dat:
            raise RuntimeError("ccx failed: " + r.stdout[-800:])
        freqs = []
        sec = dat.split("E I G E N V A L U E   O U T P U T")[1]
        for line in sec.splitlines():
            parts = line.split()
            if len(parts) == 5 and parts[0].isdigit():
                freqs.append(float(parts[3]))   # cycles/time (Hz)
            elif freqs and not parts:
                break
        return np.array(sorted(f for f in freqs if f > 1.0)), int(len(conn))
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def pick_plates(n, d, k=12, seed=0):
    """Deterministic spread over Lx, Ly and thickness (2-7 mm)."""
    rng = np.random.default_rng(seed)
    ids = np.unique(n)
    by_h = {}
    for p in ids:
        h = round(float(d[np.where(n == p)[0][0], 2]) * 1e3)
        by_h.setdefault(h, []).append(p)
    chosen = [1, int(ids.max())]
    hs = sorted(by_h)
    while len(chosen) < k:
        h = hs[len(chosen) % len(hs)]
        p = int(rng.choice(by_h[h]))
        if p not in chosen:
            chosen.append(p)
    return sorted(chosen)


def main(k=12):
    n, d, m, f, bc = load_meta()
    out = {
        "source": "Olivieri et al., Sensors 21:7834 (2021); Zenodo 10.5281/zenodo.5702615 (CC-BY-4.0); COMSOL Multiphysics",
        "material_assumed": AL,
        "material_note": "Not stated in the dataset; nominal aluminium used, no parameter fitted.",
        "kirchhoff_ss_closed_form_check": kirchhoff_ss_check(n, d, m, f, bc),
        "our_solver": "gmsh OCC + C3D10 + CalculiX *FREQUENCY (same chain as the mirror gravity FEA)",
        "cases": [],
    }
    plates = pick_plates(n, d, k)
    t0 = time.time()
    for p in plates:
        Lx, Ly, h = d[np.where(n == p)[0][0]]
        for b in BC_NAMES:
            sel = (n == p) & (bc == b)
            if not sel.any():
                continue
            ref = np.sort(f[sel])
            ours, nel = ccx_plate_modes(Lx, Ly, h, b)
            k_ = min(len(ref), len(ours))
            err = 100 * (ours[:k_] - ref[:k_]) / ref[:k_]
            case = {"plate": int(p), "Lx_m": float(Lx), "Ly_m": float(Ly), "h_m": float(h), "bc": b,
                    "n_modes": int(k_), "elements": nel,
                    "f_comsol_hz": [round(float(v), 2) for v in ref[:k_]],
                    "f_ccx_hz": [round(float(v), 2) for v in ours[:k_]],
                    "err_pct": [round(float(v), 3) for v in err],
                    "mode_count_below_2kHz": {"comsol": int(len(ref)), "ccx": int((ours < FMAX).sum())}}
            out["cases"].append(case)
            print(f"plate {p:3d} {b:17s} h={h*1e3:.0f}mm modes={k_:2d} "
                  f"median|err|={np.median(np.abs(err)):.2f}% max={np.abs(err).max():.2f}%", flush=True)
    allerr = np.abs(np.concatenate([c["err_pct"] for c in out["cases"]]))
    out["summary"] = {
        "plates": len(plates), "cases": len(out["cases"]), "modes_compared": int(len(allerr)),
        "median_abs_err_pct": float(np.median(allerr)),
        "p90_abs_err_pct": float(np.percentile(allerr, 90)),
        "max_abs_err_pct": float(allerr.max()),
        "by_bc": {b: {"modes": int(sum(len(c["err_pct"]) for c in out["cases"] if c["bc"] == b)),
                      "median_abs_err_pct": float(np.median(np.abs(np.concatenate(
                          [c["err_pct"] for c in out["cases"] if c["bc"] == b]))))}
                  for b in BC_NAMES},
        "runtime_s": round(time.time() - t0, 1),
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out["summary"], indent=1))
    print(json.dumps(out["kirchhoff_ss_closed_form_check"]))
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
