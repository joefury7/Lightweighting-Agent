"""
3-Rib Star-Vertex Node Snapper (Pillar 3 & 4)
Algorithmic geometric locking for 18-Point Whiffletree kinematic support pads.
Snaps theoretical Whiffletree positions directly to solid 3-rib star-vertex junctions.
"""

import math
import numpy as np

def generate_isogrid_vertices(D_mm, L_mm, margin_mm=15.0):
    """
    Generates all valid star-vertex intersection coordinates within the mirror aperture.
    """
    R = D_mm / 2.0
    R_max = R - margin_mm
    
    # In an equilateral triangular isogrid, vertices occur on a regular triangular lattice:
    # dx = L, dy = L * sqrt(3) / 2
    dy = L_mm * math.sqrt(3.0) / 2.0
    dx = L_mm
    
    nx = int(math.ceil(D_mm / dx)) + 2
    ny = int(math.ceil(D_mm / dy)) + 2
    
    vertices = []
    for j in range(-ny, ny + 1):
        y = j * dy
        # Alternate rows are offset by dx / 2
        x_offset = (dx / 2.0) if (j % 2 != 0) else 0.0
        for i in range(-nx, nx + 1):
            x = i * dx + x_offset
            dist = math.sqrt(x**2 + y**2)
            if dist <= R_max:
                vertices.append((round(x, 4), round(y, 4)))
                
    return vertices

def snap_18_whiffletree_hubs(D_mm, L_mm, Dc_mm=120.0):
    """
    Computes theoretical 18 Whiffletree support positions (6 inner, 12 outer)
    and snaps each to the nearest solid 3-rib star-vertex junction without duplicates.
    """
    R = D_mm / 2.0
    Rc = Dc_mm / 2.0
    
    # Optimal Nelson 18-point support radii
    r_inner = 0.40 * R
    r_outer = 0.82 * R
    
    theoretical_hubs = []
    # 6 Inner hubs (60 deg apart)
    for k in range(6):
        theta = math.radians(k * 60.0 + 30.0)
        theoretical_hubs.append((r_inner * math.cos(theta), r_inner * math.sin(theta)))
        
    # 12 Outer hubs (30 deg apart, offset by 15 deg)
    for k in range(12):
        theta = math.radians(k * 30.0 + 15.0)
        theoretical_hubs.append((r_outer * math.cos(theta), r_outer * math.sin(theta)))

    vertices = generate_isogrid_vertices(D_mm, L_mm, margin_mm=18.0)
    if not vertices:
        # Fallback if cell size is too large
        return theoretical_hubs

    snapped_hubs = []
    used_vertices = set()

    for hx, hy in theoretical_hubs:
        # Find closest unused vertex
        best_v = None
        min_d = float('inf')
        
        for vx, vy in vertices:
            d = math.hypot(vx - hx, vy - hy)
            if d < min_d and (vx, vy) not in used_vertices:
                min_d = d
                best_v = (vx, vy)
                
        if best_v is not None and min_d < (L_mm * 1.2):
            snapped_hubs.append(best_v)
            used_vertices.add(best_v)
        else:
            # If no vertex close enough, preserve theoretical
            snapped_hubs.append((round(hx, 2), round(hy, 2)))

    return snapped_hubs

if __name__ == "__main__":
    hubs = snap_18_whiffletree_hubs(560.0, 55.5, 120.0)
    print(f"Generated {len(hubs)} Snapped 18-Point Whiffletree Hubs for 560mm Mirror:")
    for idx, (hx, hy) in enumerate(hubs, start=1):
        ring = "INNER" if idx <= 6 else "OUTER"
        print(f"  Hub {idx:02d} ({ring}): X = {hx:7.2f} mm, Y = {hy:7.2f} mm | R = {math.hypot(hx, hy):.2f} mm")
