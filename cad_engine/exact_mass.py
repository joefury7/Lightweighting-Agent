"""
Fast exact mass of the isogrid mirror, identical to the geometry built by the NX journal.

This is a line-by-line port of the journal's isogrid pocket loop (app.js -> generateNXCode):
  * parameters rounded exactly as the journal writes them (toFixed(1) / toFixed(4)),
  * chamfered-corner triangular pockets (build_filleted_triangle, n_sub = 1),
  * adaptive pocket height  h = z_front(r_min) - FACESHEET - BACK_Z,
  * outer and inner 5 mm wall rings re-united after pocketing.
Mass = density x [blank volume - sum(pocket footprint ∩ cut annulus) x pocket height].

There are NO calibration or packing factors.  Agreement with the journal replica
(cad_engine/journal_replica.py, itself validated against an OpenCascade solid model) is
checked by validation/test_exact_mass.py.
"""
import math
import numpy as np

from cad_engine.journal_replica import polygon_annulus_area, blank_volume, conic_z

WALL_MARGIN = 5.0
N_SUB = 1  # corner segments, as written in the journal (app.js)


def _r1(v, nd=1):
    """Exact equivalent of JavaScript Number(v).toFixed(nd): rounds the exact binary value,
    ties (only possible for exactly representable values) away from zero."""
    from decimal import Decimal, ROUND_HALF_UP
    return float(Decimal(float(v)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP))


def journal_rounded_params(D, Dc, H, tf, tw, L, rf, R_curv=1085.0, k=-1.22, rho_kg_m3=2530.0):
    return {
        "R": _r1(D / 2.0), "Dc": _r1(Dc), "H": _r1(H), "tf": _r1(tf), "tw": _r1(tw), "L": _r1(L),
        "rf": _r1(rf), "R_curv": _r1(R_curv), "k": _r1(k, 4),
        "rho": float(f"{_r1(rho_kg_m3) * 1e-9:.6e}"),
    }


def pocket_polygons(R, Dc, H, tf, tw, L, rf):
    """Yield (polygon, height) for every pocket the journal extrudes (isogrid)."""
    max_r = R - WALL_MARGIN
    central_exclude = Dc / 2.0 + 3.0
    row_h = L * math.sqrt(3.0) / 2.0
    pocket_side = L - tw * 2.0 / math.sqrt(3.0)
    r_in = pocket_side / math.sqrt(3.0)
    n_rows = int(math.ceil(max_r / row_h)) + 1
    n_cols = int(math.ceil(max_r / L)) + 1
    back_z = -H
    for j in range(-n_rows, n_rows + 1):
        y_base = j * row_h
        x_off = (L * 0.5) if (j % 2 != 0) else 0.0
        for i in range(-n_cols, n_cols + 1):
            for (cx, cy, ori) in ((i * L + x_off, y_base + row_h / 3.0, 1),
                                  (i * L + L * 0.5 + x_off, y_base + 2.0 * row_h / 3.0, -1)):
                d = math.hypot(cx, cy)
                margin_tol = L * 0.6
                if d > max_r + margin_tol or d < max(5.0, central_exclude - margin_tol):
                    continue
                base_a = math.radians(90.0) if ori == 1 else math.radians(-90.0)
                v_ang = [base_a + math.radians(120.0 * kk) for kk in range(3)]
                ac = [(cx + (r_in - 2.0 * rf) * math.cos(a), cy + (r_in - 2.0 * rf) * math.sin(a)) for a in v_ang]
                poly = []
                for kk in range(3):
                    c_x, c_y = ac[kk]
                    a_s = v_ang[kk] - math.pi / 3.0
                    a_e = v_ang[kk] + math.pi / 3.0
                    for s in range(N_SUB):
                        ta = a_s + s * (a_e - a_s) / float(N_SUB)
                        poly.append((c_x + rf * math.cos(ta), c_y + rf * math.sin(ta)))
                    poly.append((c_x + rf * math.cos(a_e), c_y + rf * math.sin(a_e)))
                # remove duplicate consecutive vertex (end of chord == start of side line)
                clean = [poly[0]]
                for p in poly[1:]:
                    if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-12:
                        clean.append(p)
                r_min = max(0.0, d - r_in)
                r_min = min(r_min, R - WALL_MARGIN)
                z_front_min = None  # filled by caller (needs conic params)
                yield clean, r_min


def isogrid_exact_mass(D, Dc, H, tf, tw, L, rf, R_curv=1085.0, k=-1.22, rho_kg_m3=2530.0, details=False):
    p = journal_rounded_params(D, Dc, H, tf, tw, L, rf, R_curv, k, rho_kg_m3)
    R, Dc_, H_, tf_, tw_, L_, rf_ = p["R"], p["Dc"], p["H"], p["tf"], p["tw"], p["L"], p["rf"]
    rh = Dc_ / 2.0
    v_blank = blank_volume(R, rh, H_, p["R_curv"], p["k"])
    lo, hi = rh + WALL_MARGIN, R - WALL_MARGIN
    v_rem = 0.0
    n = 0
    for poly, r_min in pocket_polygons(R, Dc_, H_, tf_, tw_, L_, rf_):
        z_front_min = conic_z(r_min, p["R_curv"], p["k"])
        h = round(max(5.0, z_front_min - tf_ + H_), 3)   # journal: str(round(h, 3))
        a = polygon_annulus_area(poly, lo, hi)
        if a > 1e-6:
            v_rem += a * h
        if polygon_annulus_area(poly, rh, R) > 1e-6:   # NX extrude succeeds (tool touches blank)
            n += 1
    v = v_blank - v_rem
    out = {"mass_kg": v * p["rho"], "volume_mm3": v, "solid_mass_kg": v_blank * p["rho"],
           "lightweight_pct": 100.0 * (1.0 - v / v_blank), "pocket_count": n}
    if details:
        out["rounded_params"] = p
    return out


def isogrid_exact_mass_batch(feature_matrix, R_curv=1085.0, k=-1.22, rho_kg_m3=2530.0):
    """feature_matrix columns: D, Dc, H, tf, tw, L, rf  ->  mass array (kg)."""
    fm = np.asarray(feature_matrix, dtype=float)
    return np.array([isogrid_exact_mass(*row, R_curv=R_curv, k=k, rho_kg_m3=rho_kg_m3)["mass_kg"] for row in fm])


# ----------------------------------------------------------------------------------
# Vectorised implementation (identical maths, ~20x faster) for optimisers
# ----------------------------------------------------------------------------------

def _poly_disk_area_np(P, R):
    """P: (n_poly, n_vert, 2) polygons -> exact areas of each polygon ∩ disk(0,R)."""
    A = P
    B = np.roll(P, -1, axis=1)
    ax, ay, bx, by = A[..., 0], A[..., 1], B[..., 0], B[..., 1]
    dx, dy = bx - ax, by - ay
    a = dx * dx + dy * dy
    b = 2 * (ax * dx + ay * dy)
    c = ax * ax + ay * ay - R * R
    disc = b * b - 4 * a * c
    sq = np.sqrt(np.maximum(disc, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = np.where(disc > 0, (-b - sq) / (2 * a), 0.0)
        t2 = np.where(disc > 0, (-b + sq) / (2 * a), 0.0)
    t1 = np.clip(t1, 0.0, 1.0)
    t2 = np.clip(t2, 0.0, 1.0)
    ts = [np.zeros_like(t1), t1, t2, np.ones_like(t1)]
    total = np.zeros(ax.shape)
    for s0, s1 in zip(ts[:-1], ts[1:]):
        px, py = ax + s0 * dx, ay + s0 * dy
        qx, qy = ax + s1 * dx, ay + s1 * dy
        mx, my = 0.5 * (px + qx), 0.5 * (py + qy)
        cross = px * qy - py * qx
        dot = px * qx + py * qy
        inside = mx * mx + my * my <= R * R
        total += np.where(inside, 0.5 * cross, 0.5 * R * R * np.arctan2(cross, dot))
    return np.abs(total.sum(axis=1))


def isogrid_exact_mass_fast(D, Dc, H, tf, tw, L, rf, R_curv=1085.0, k=-1.22, rho_kg_m3=2530.0):
    p = journal_rounded_params(D, Dc, H, tf, tw, L, rf, R_curv, k, rho_kg_m3)
    R, Dc_, H_, tf_, tw_, L_, rf_ = p["R"], p["Dc"], p["H"], p["tf"], p["tw"], p["L"], p["rf"]
    rh = Dc_ / 2.0
    max_r = R - WALL_MARGIN
    central_exclude = Dc_ / 2.0 + 3.0
    row_h = L_ * math.sqrt(3.0) / 2.0
    r_in = (L_ - tw_ * 2.0 / math.sqrt(3.0)) / math.sqrt(3.0)
    n_rows = int(math.ceil(max_r / row_h)) + 1
    n_cols = int(math.ceil(max_r / L_)) + 1
    j = np.arange(-n_rows, n_rows + 1)[:, None]
    i = np.arange(-n_cols, n_cols + 1)[None, :]
    x_off = np.where(j % 2 != 0, L_ * 0.5, 0.0)
    cx = np.concatenate([(i * L_ + x_off).ravel(), (i * L_ + L_ * 0.5 + x_off).ravel()])
    cy = np.concatenate([np.broadcast_to(j * row_h + row_h / 3.0, (j.size, i.size)).ravel(),
                         np.broadcast_to(j * row_h + 2.0 * row_h / 3.0, (j.size, i.size)).ravel()])
    ori = np.concatenate([np.ones(j.size * i.size), -np.ones(j.size * i.size)])
    d = np.hypot(cx, cy)
    tol = L_ * 0.6
    keep = ~((d > max_r + tol) | (d < max(5.0, central_exclude - tol)))
    cx, cy, ori, d = cx[keep], cy[keep], ori[keep], d[keep]
    base = np.where(ori == 1, math.pi / 2, -math.pi / 2)
    verts = []
    for q in range(3):
        va = base + q * 2 * math.pi / 3
        ccx = cx + (r_in - 2 * rf_) * np.cos(va)
        ccy = cy + (r_in - 2 * rf_) * np.sin(va)
        verts.append(np.stack([ccx + rf_ * np.cos(va - math.pi / 3), ccy + rf_ * np.sin(va - math.pi / 3)], -1))
        verts.append(np.stack([ccx + rf_ * np.cos(va + math.pi / 3), ccy + rf_ * np.sin(va + math.pi / 3)], -1))
    P = np.stack(verts, axis=1)
    area = np.maximum(0.0, _poly_disk_area_np(P, R - WALL_MARGIN) - _poly_disk_area_np(P, rh + WALL_MARGIN))
    r_min = np.minimum(np.maximum(0.0, d - r_in), R - WALL_MARGIN)
    Rc, kk = p["R_curv"], p["k"]
    zf = r_min ** 2 / (Rc * (1.0 + np.sqrt(np.maximum(0.0001, 1.0 - (1.0 + kk) * r_min ** 2 / Rc ** 2))))
    h = np.round(np.maximum(5.0, zf - tf_ + H_), 3)   # journal: str(round(h, 3))
    v_blank = blank_volume(R, rh, H_, Rc, kk)
    area = np.where(area > 1e-6, area, 0.0)
    v = v_blank - float(np.sum(area * h))
    touches = (_poly_disk_area_np(P, R) - _poly_disk_area_np(P, rh)) > 1e-6
    return {"mass_kg": v * p["rho"], "volume_mm3": v, "solid_mass_kg": v_blank * p["rho"],
            "lightweight_pct": 100.0 * (1.0 - v / v_blank), "pocket_count": int(np.sum(touches))}


def isogrid_geometry_details(D, Dc, H, tf, tw, L, rf, R_curv=1085.0, k=-1.22, rho_kg_m3=2530.0):
    """Same structure as journal_replica.replica_mass(..., return_details=True), built directly
    from parameters with the journal-identical pocket generator (used by the FEA engine)."""
    p = journal_rounded_params(D, Dc, H, tf, tw, L, rf, R_curv, k, rho_kg_m3)
    R, Dc_, H_, tf_, tw_, L_, rf_ = p["R"], p["Dc"], p["H"], p["tf"], p["tw"], p["L"], p["rf"]
    rh = Dc_ / 2.0
    lo, hi = rh + WALL_MARGIN, R - WALL_MARGIN
    pockets = []
    for poly, r_min in pocket_polygons(R, Dc_, H_, tf_, tw_, L_, rf_):
        h = round(max(5.0, conic_z(r_min, p["R_curv"], p["k"]) - tf_ + H_), 3)
        a = polygon_annulus_area(poly, lo, hi)
        if a > 1e-6:
            pockets.append({"poly": poly, "h": h, "area_in": a, "z_lo": -H_, "z_hi": -H_ + h})
    m = isogrid_exact_mass_fast(D, Dc, H, tf, tw, L, rf, R_curv, k, rho_kg_m3)
    return {**m, "pockets": pockets,
            "restored_bands": [(R - WALL_MARGIN, R), (rh, rh + WALL_MARGIN)],
            "intervals": [(lo, hi)],
            "namespace": {"RADIUS": R, "CENTRAL_HOLE_DIA": Dc_, "TOTAL_DEPTH": H_, "R_CURV": p["R_curv"],
                          "CONIC_CONSTANT": p["k"], "FACESHEET": tf_, "RIB_THICK": tw_, "CELL_SIDE": L_,
                          "DENSITY_KG_MM3": p["rho"]}}
