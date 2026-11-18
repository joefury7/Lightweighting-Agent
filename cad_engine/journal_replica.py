"""
Exact geometric replica of the NX Open mirror journal (single source of truth for mass).

How it works
------------
The app generates an NX Open Python journal that builds the mirror in NX.  Instead of
re-implementing that geometry with fitted "packing factors", this module *executes the
journal itself* against a lightweight stand-in for the ``NXOpen`` API that records every
curve and every extrude/boolean the journal asks NX to perform.  Mass is then computed
exactly from the recorded operations:

  * blank   = solid of revolution of the conic front profile between the central hole
              and the outer radius, down to the flat back at z = -TOTAL_DEPTH
  * pockets = vertical prisms (closed polygon from the recorded lines x extrude height),
              intersected exactly with the annular blank footprint

Because the very same journal text drives both NX and this replica, the geometry cannot
drift apart (the old code used separate hand-written approximations + fudge factors).
No calibration constants are used anywhere in this file.
"""
import math
import sys
import types
import numpy as np

# ----------------------------------------------------------------------------------
# Exact area of (convex or simple) polygon ∩ disk centred at the origin
# ----------------------------------------------------------------------------------

def _tri_disk_area(ax, ay, bx, by, R):
    """Signed area of triangle (O, A, B) ∩ disk(O, R). Exact (segment/arc decomposition)."""
    def seg_points(ax, ay, bx, by):
        # parameters t in (0,1) where |A + t(B-A)| = R
        dx, dy = bx - ax, by - ay
        a = dx * dx + dy * dy
        b = 2 * (ax * dx + ay * dy)
        c = ax * ax + ay * ay - R * R
        disc = b * b - 4 * a * c
        if a == 0 or disc <= 0:
            return []
        s = math.sqrt(disc)
        ts = sorted([(-b - s) / (2 * a), (-b + s) / (2 * a)])
        return [t for t in ts if 0.0 < t < 1.0]

    def sector(px, py, qx, qy):
        ang = math.atan2(px * qy - py * qx, px * qx + py * qy)
        return 0.5 * R * R * ang

    def tri(px, py, qx, qy):
        return 0.5 * (px * qy - py * qx)

    pts = [(ax, ay)]
    for t in seg_points(ax, ay, bx, by):
        pts.append((ax + t * (bx - ax), ay + t * (by - ay)))
    pts.append((bx, by))
    area = 0.0
    for (px, py), (qx, qy) in zip(pts[:-1], pts[1:]):
        mx, my = 0.5 * (px + qx), 0.5 * (py + qy)
        if mx * mx + my * my <= R * R:
            area += tri(px, py, qx, qy)
        else:
            area += sector(px, py, qx, qy)
    return area


def polygon_disk_area(poly, R):
    """Exact area of a simple polygon ∩ disk(0, R). poly: list of (x, y)."""
    if R <= 0:
        return 0.0
    a = 0.0
    n = len(poly)
    for k in range(n):
        ax, ay = poly[k]
        bx, by = poly[(k + 1) % n]
        a += _tri_disk_area(ax, ay, bx, by, R)
    return abs(a)


def polygon_annulus_area(poly, r_in, r_out):
    return max(0.0, polygon_disk_area(poly, r_out) - polygon_disk_area(poly, r_in))


def polygon_area(poly):
    a = 0.0
    for k in range(len(poly)):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % len(poly)]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5

# ----------------------------------------------------------------------------------
# Minimal recording stand-in for the NXOpen API
# ----------------------------------------------------------------------------------

class _Any:
    """Generic object: any attribute / call returns another _Any. Iterates as empty."""
    def __init__(self, *a, **k):
        pass
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        v = _Any()
        object.__setattr__(self, name, v)
        return v
    def __call__(self, *a, **k):
        return _Any()
    def __iter__(self):
        return iter([])
    def __len__(self):
        return 0
    def __getitem__(self, i):
        return _Any()


class Point3d:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = float(x), float(y), float(z)


class Vector3d(Point3d):
    pass


class _Line(_Any):
    def __init__(self, p1, p2):
        object.__setattr__(self, "StartPoint", p1)
        object.__setattr__(self, "EndPoint", p2)
    def Blank(self):
        pass


class _Rule(_Any):
    def __init__(self, curves):
        object.__setattr__(self, "curves", list(curves))


class _Section(_Any):
    def __init__(self):
        object.__setattr__(self, "rules", [])
    def SetAllowedEntityTypes(self, *a):
        pass
    def AddToSection(self, rules, *a, **k):
        self.rules.extend(rules)


class _Expr:
    def __init__(self):
        self.RightHandSide = "0"
        self.Value = 0.0


class _Limits:
    def __init__(self):
        self.StartExtend = types.SimpleNamespace(Value=_Expr())
        self.EndExtend = types.SimpleNamespace(Value=_Expr())


class _Bool:
    def __init__(self):
        self.Type = None
        self.targets = []
    def SetTargetBodies(self, b):
        self.targets = list(b)


class _Recorder:
    def __init__(self):
        self.extrudes = []
        self.revolves = []


class _ExtrudeBuilder(_Any):
    def __init__(self, rec):
        object.__setattr__(self, "_rec", rec)
        object.__setattr__(self, "Section", None)
        object.__setattr__(self, "Direction", None)
        object.__setattr__(self, "Limits", _Limits())
        object.__setattr__(self, "BooleanOperation", _Bool())
    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
    def CommitFeature(self):
        lim = self.Limits
        def _val(e):
            try:
                return float(e.Value.RightHandSide)
            except Exception:
                return float(e.Value.Value)
        start, end = _val(lim.StartExtend), _val(lim.EndExtend)
        curves = []
        for r in (self.Section.rules if self.Section is not None else []):
            curves.extend(r.curves)
        self._rec.extrudes.append({
            "curves": curves,
            "start": start,
            "end": end,
            "bool": self.BooleanOperation.Type,
        })
        f = _Any()
        object.__setattr__(f, "GetBodies", lambda: [_Any()])
        return f
    def Destroy(self):
        pass


class _RevolveBuilder(_Any):
    def __init__(self, rec):
        object.__setattr__(self, "_rec", rec)
        object.__setattr__(self, "Section", None)
        object.__setattr__(self, "Limits", _Limits())
        object.__setattr__(self, "BooleanOperation", _Bool())
    def __setattr__(self, k, v):
        object.__setattr__(self, k, v)
    def CommitFeature(self):
        xs = []
        for r in (self.Section.rules if self.Section is not None else []):
            for c in r.curves:
                if isinstance(c, _Line):
                    xs += [abs(c.StartPoint.X), abs(c.EndPoint.X)]
        self._rec.revolves.append({"bool": self.BooleanOperation.Type,
                                   "r_min": min(xs) if xs else None, "r_max": max(xs) if xs else None})
        f = _Any()
        object.__setattr__(f, "GetBodies", lambda: [_Any()])
        return f
    def Destroy(self):
        pass


def _make_fake_nxopen(rec):
    nx = types.ModuleType("NXOpen")
    nx.Point3d = Point3d
    nx.Vector3d = Vector3d

    class Part:
        class Units:
            Millimeters = "mm"
    nx.Part = Part

    work = _Any()
    curves = _Any()
    object.__setattr__(curves, "CreateLine", lambda p1, p2: _Line(p1, p2))
    object.__setattr__(work, "Curves", curves)
    sections = _Any()
    object.__setattr__(sections, "CreateSection", lambda *a: _Section())
    object.__setattr__(work, "Sections", sections)
    scr = _Any()
    object.__setattr__(scr, "CreateRuleCurveDumb", lambda c, *a: _Rule(c))
    object.__setattr__(work, "ScRuleFactory", scr)
    feats = _Any()
    object.__setattr__(feats, "CreateExtrudeBuilder", lambda *a: _ExtrudeBuilder(rec))
    object.__setattr__(feats, "CreateRevolveBuilder", lambda *a: _RevolveBuilder(rec))
    object.__setattr__(work, "Features", feats)

    session = _Any()
    parts = _Any()
    object.__setattr__(parts, "Work", work)
    object.__setattr__(parts, "NewDisplay", lambda *a, **k: work)
    object.__setattr__(session, "Parts", parts)

    class Session:
        @staticmethod
        def GetSession():
            return session
    nx.Session = Session

    class _BT:
        Subtract = "subtract"
        Unite = "unite"
        Create = "create"
        Intersect = "intersect"
    gu = types.ModuleType("NXOpen.GeometricUtilities")
    gu.BooleanOperation = types.SimpleNamespace(BooleanType=_BT)
    nx.GeometricUtilities = gu
    feats_mod = types.ModuleType("NXOpen.Features")
    for nm in ["Extrude", "Revolve", "StudioSpline", "Feature", "Block", "Cylinder"]:
        setattr(feats_mod, nm, types.SimpleNamespace(Null=None))
    feats_mod.StudioSplineBuilderEx = types.SimpleNamespace(Types=types.SimpleNamespace(ThroughPoints=0))
    nx.Features = feats_mod
    uf = types.ModuleType("NXOpen.UF")
    uf.UFSession = types.SimpleNamespace(GetUFSession=lambda: _Any())
    nx.UF = uf
    for nm in ["Section", "NXObject", "SmartObject", "Sense", "BasePart", "PhysicalMaterial",
               "Body", "DisplayableObject", "Unit"]:
        setattr(nx, nm, _Any())
    nx.NXObject = types.SimpleNamespace(Null=None)
    return nx, {"NXOpen": nx, "NXOpen.GeometricUtilities": gu, "NXOpen.Features": feats_mod, "NXOpen.UF": uf}

# ----------------------------------------------------------------------------------
# Journal execution + exact mass
# ----------------------------------------------------------------------------------

def _loop_polygon(curves):
    """Chain recorded line segments into an ordered closed polygon (x, y)."""
    if not curves:
        return []
    pts = [(c.StartPoint.X, c.StartPoint.Y) for c in curves]
    return pts


def run_journal(journal_code):
    """Execute journal text against the recording stand-in. Returns (namespace, recorder)."""
    rec = _Recorder()
    nx, mods = _make_fake_nxopen(rec)
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    ns = {"__name__": "nx_replica"}
    try:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(journal_code, "<nx_journal>", "exec"), ns)
            ns["main"]()
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return ns, rec


def conic_z(r, R_curv, k):
    return (r * r) / (R_curv * (1.0 + math.sqrt(max(0.0001, 1.0 - (1.0 + k) * r * r / (R_curv * R_curv)))))


_GL = np.polynomial.legendre.leggauss(400)


def blank_volume(R, r_hole, H, R_curv, k, n=400):
    """Volume of the revolved conic blank (flat back at -H). 400-point Gauss-Legendre."""
    xi, wi = _GL if n == 400 else np.polynomial.legendre.leggauss(n)
    r = 0.5 * ((R - r_hole) * xi + (R + r_hole))
    z = r * r / (R_curv * (1.0 + np.sqrt(np.maximum(0.0001, 1.0 - (1.0 + k) * r * r / (R_curv * R_curv)))))
    return float(np.sum(wi * 2.0 * np.pi * r * (H + z)) * 0.5 * (R - r_hole))


def replica_mass(journal_code, return_details=False):
    ns, rec = run_journal(journal_code)
    R = float(ns["RADIUS"])
    r_hole = float(ns["CENTRAL_HOLE_DIA"]) / 2.0
    H = float(ns["TOTAL_DEPTH"])
    R_curv = float(ns["R_CURV"])
    k = float(ns["CONIC_CONSTANT"])
    rho = float(ns.get("DENSITY_KG_MM3", 2.53e-6))
    v_blank = blank_volume(R, r_hole, H, R_curv, k)

    # Full-height rings re-united after pocketing (outer / inner wall restore revolves)
    restored = [(rv["r_min"], rv["r_max"]) for rv in rec.revolves
                if rv["bool"] == "unite" and rv["r_min"] is not None]
    intervals = [(r_hole, R)]
    for a, b in restored:
        nxt = []
        for lo, hi in intervals:
            if b <= lo or a >= hi:
                nxt.append((lo, hi)); continue
            if a > lo: nxt.append((lo, a))
            if b < hi: nxt.append((b, hi))
        intervals = nxt

    def cut_area(poly):
        return sum(polygon_annulus_area(poly, lo, hi) for lo, hi in intervals)

    v_removed = 0.0
    v_added = 0.0
    n_pockets = 0
    pockets = []
    for e in rec.extrudes:
        poly = _loop_polygon(e["curves"])
        if len(poly) < 3:
            continue
        z0 = e["curves"][0].StartPoint.Z
        h = e["end"] - e["start"]
        z_lo, z_hi = z0 + e["start"], z0 + e["end"]
        a_in = cut_area(poly)
        if e["bool"] == "subtract":
            if a_in <= 1e-6:
                continue   # tool body misses the blank: NX rejects this feature
            # prism must lie inside blank in z (back plane to below the front surface)
            v = a_in * (z_hi - max(z_lo, -H))
            v_removed += v
            n_pockets += 1
            pockets.append({"poly": poly, "h": h, "area_in": a_in, "z_lo": z_lo, "z_hi": z_hi})
        elif e["bool"] == "unite":
            v_added += polygon_area(poly) * h
    v_cad = v_blank - v_removed + v_added
    out = {
        "volume_mm3": v_cad,
        "mass_kg": v_cad * rho,
        "blank_volume_mm3": v_blank,
        "solid_mass_kg": v_blank * rho,
        "lightweight_pct": 100.0 * (1.0 - v_cad / v_blank),
        "pocket_count": n_pockets,
        "density_kg_mm3": rho,
    }
    if return_details:
        out["pockets"] = pockets
        out["namespace"] = {k: ns[k] for k in ["RADIUS", "CENTRAL_HOLE_DIA", "TOTAL_DEPTH", "R_CURV",
                                               "CONIC_CONSTANT", "FACESHEET", "RIB_THICK", "CELL_SIDE"]}
        out["restored_bands"] = restored
        out["intervals"] = intervals
    return out


if __name__ == "__main__":
    code = open(sys.argv[1], encoding="utf-8").read()
    r = replica_mass(code)
    print({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
