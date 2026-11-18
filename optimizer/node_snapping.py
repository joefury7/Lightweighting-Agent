"""
18-point whiffletree (Hindle) support hub positions - IDENTICAL to the logic in the NX journal
written by app.js (equal-area radii r1/r2, inner hubs at 0/60/.. deg, outer pairs at 30+-14.5 deg,
each snapped to the nearest isogrid node of get_exact_grid_intersection_nodes()).
Used by the FEA engine (support pads) and reported with optimisation results.
"""
import math


def generate_isogrid_vertices(D_mm, L_mm, Dc_mm=175.0):
    R = D_mm / 2.0
    max_r = R - 4.0
    min_r = Dc_mm / 2.0 + 4.0
    row_h = L_mm * math.sqrt(3.0) / 2.0
    n_rows = int(max_r / row_h) + 2
    n_cols = int(max_r / L_mm) + 2
    nodes = []
    for j in range(-n_rows, n_rows + 1):
        y = j * row_h
        xs = (L_mm / 2.0) if (abs(j) % 2 != 0) else 0.0
        for i in range(-n_cols, n_cols + 1):
            x = i * L_mm + xs
            d = math.hypot(x, y)
            if min_r <= d <= max_r:
                nodes.append((x, y))
    return nodes


def snap_18_whiffletree_hubs(D_mm, L_mm, Dc_mm=175.0):
    R = D_mm / 2.0
    rh = Dc_mm / 2.0
    area = max(100.0, R ** 2 - rh ** 2)
    r_mid = math.sqrt(rh ** 2 + area / 3.0)
    r1 = math.sqrt((rh ** 2 + r_mid ** 2) / 2.0)
    r2 = math.sqrt((r_mid ** 2 + R ** 2) / 2.0)
    nodes = generate_isogrid_vertices(D_mm, L_mm, Dc_mm)
    inner = []
    for i in range(6):
        a = math.radians(i * 60.0)
        tx, ty = r1 * math.cos(a), r1 * math.sin(a)
        inner.append(min(nodes, key=lambda n: math.hypot(n[0] - tx, n[1] - ty)) if nodes else (tx, ty))
    outer = []
    da = math.radians(14.5)
    for i in range(6):
        ax = math.radians(i * 60.0 + 30.0)
        for d in (-da, da):
            a = ax + d
            tx, ty = r2 * math.cos(a), r2 * math.sin(a)
            av = [n for n in nodes if math.hypot(*n) >= r_mid and n not in inner and n not in outer]
            outer.append(min(av, key=lambda n: math.hypot(n[0] - tx, n[1] - ty)) if av else (tx, ty))
    return [[round(x, 4), round(y, 4)] for (x, y) in inner + outer]
