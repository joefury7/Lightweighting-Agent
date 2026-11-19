"""
Geometry for the 3D preview: exactly the features the NX journal builds, as compact outlines.

The journal is executed by the journal replica (same path as the exact-mass calculation).
Each pocket extrude is clipped to the radial bands where it actually removes material
(blank annulus minus the outer/inner wall-restore rings), which is the same clipping the mass
calculation uses. The browser turns these outlines into a triangle mesh (three.js); no CAD
boolean is needed, so a preview takes milliseconds.
"""
import hashlib
from collections import OrderedDict

from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

from cad_engine.journal_replica import replica_mass

_CACHE = OrderedDict()


def _annulus(lo, hi, n=256):
    outer = Point(0, 0).buffer(hi, n // 4)
    return outer.difference(Point(0, 0).buffer(lo, n // 4)) if lo > 0 else outer


def _rings(geom):
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    out = []
    for p in polys:
        if p.is_empty or p.area < 1e-3:
            continue
        out.append({"outer": [[round(x, 3), round(y, 3)] for x, y in p.exterior.coords[:-1]],
                    "holes": [[[round(x, 3), round(y, 3)] for x, y in r.coords[:-1]] for r in p.interiors]})
    return out


def preview_geometry(journal_code):
    key = hashlib.sha1(journal_code.encode("utf-8")).hexdigest()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    det = replica_mass(journal_code, return_details=True)
    ns = det["namespace"]
    R = float(ns["RADIUS"]); rh = float(ns["CENTRAL_HOLE_DIA"]) / 2.0; H = float(ns["TOTAL_DEPTH"])
    cut_region = unary_union([_annulus(lo, hi) for lo, hi in det["intervals"]])
    pockets, removed = [], []
    for p in det["pockets"]:
        g = Polygon(p["poly"]).buffer(0).intersection(cut_region)
        if g.is_empty:
            continue
        removed.append(g)
        z_lo = max(float(p["z_lo"]), -H)
        for r in _rings(g):
            pockets.append(dict(r, z_lo=round(z_lo, 4), z_hi=round(float(p["z_hi"]), 4)))
    back = _annulus(rh, R).difference(unary_union(removed)) if removed else _annulus(rh, R)
    unites = [{"outer": [[round(x, 3), round(y, 3)] for x, y in u["poly"]], "z_lo": u["z_lo"], "z_hi": u["z_hi"]}
              for u in det.get("unites", [])]
    out = {"R": R, "r_hole": rh, "H": H, "R_curv": float(ns["R_CURV"]), "k": float(ns["CONIC_CONSTANT"]),
           "back_face": _rings(back), "pockets": pockets, "unites": unites,
           "pocket_count": det["pocket_count"], "mass_kg": det["mass_kg"]}
    _CACHE[key] = out
    while len(_CACHE) > 16:
        _CACHE.popitem(last=False)
    return out
