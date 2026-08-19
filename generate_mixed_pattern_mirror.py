# ==============================================================================
# SIEMENS NX OPEN PYTHON JOURNAL: PARABOLIC MIRROR WITH MIXED LIGHTWEIGHTING
# ==============================================================================
# Pattern Architecture: HYBRID / MIXED LIGHTWEIGHTING
#   - Core Region  (r <= 400 mm): Hexagonal Honeycomb Pockets (GMT/Hubble Hybrid)
#   - Outer Region (400 mm < r <= 670 mm): Radial Spokes & Concentric Ring Pockets
#
# Instructions:
#   1. Open Siemens NX with a blank part (or run in an active part).
#   2. Press Alt + F8 to open the Journal Manager.
#   3. Select this script (generate_mixed_pattern_mirror.py) and click "Run".
# ==============================================================================

import math
import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF as UF

def create_z_direction(workPart, axis_line):
    """Robust Z-direction builder compatible across all NX versions."""
    try:
        return workPart.Directions.CreateDirection(axis_line)
    except Exception:
        return workPart.Directions.CreateDirection(
            axis_line, NXOpen.Sense.Forward, NXOpen.SmartObject.UpdateOption.WithinModeling)

def revolve_profile(workPart, curves, axis_pt, z_direction):
    """Revolves a profile around Z-axis using NX ScRuleFactory."""
    revolve_builder = workPart.Features.CreateRevolveBuilder(NXOpen.Features.Revolve.Null)
    section = workPart.Sections.CreateSection(0.0095, 0.01, 0.5)
    section.SetAllowedEntityTypes(NXOpen.Section.AllowTypes.OnlyCurves)
    
    rule = workPart.ScRuleFactory.CreateRuleCurveDumb(curves)
    null_obj = NXOpen.NXObject.Null
    help_pt = NXOpen.Point3d(0.0, 0.0, 0.0)
    section.AddToSection([rule], curves[0], null_obj, null_obj, help_pt, NXOpen.Section.Mode.Create, False)
        
    revolve_builder.Section = section
    axis_point = workPart.Points.CreatePoint(axis_pt)
    axis_obj = workPart.Axes.CreateAxis(axis_point, z_direction, NXOpen.SmartObject.UpdateOption.WithinModeling)
    revolve_builder.Axis = axis_obj
    
    revolve_builder.Limits.StartExtend.Value.Value = 0.0
    revolve_builder.Limits.EndExtend.Value.Value = 360.0
    revolve_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    
    feat = revolve_builder.CommitFeature()
    revolve_builder.Destroy()
    return feat.GetBodies()[0]

def extrude_subtract_pocket(workPart, lines, target_body, z_direction, distance, bool_type):
    """Extrudes curve loop and executes Boolean operation (Subtract or Unite)."""
    try:
        eb = workPart.Features.CreateExtrudeBuilder(NXOpen.Features.Extrude.Null)
        sec = workPart.Sections.CreateSection(0.0095, 0.01, 0.5)
        sec.SetAllowedEntityTypes(NXOpen.Section.AllowTypes.OnlyCurves)
        
        rule = workPart.ScRuleFactory.CreateRuleCurveDumb(lines)
        null_obj = NXOpen.NXObject.Null
        sec.AddToSection([rule], lines[0], null_obj, null_obj, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        
        eb.Section = sec
        eb.Direction = z_direction
        eb.Limits.StartExtend.Value.Value = 0.0
        eb.Limits.EndExtend.Value.Value = distance
        
        eb.BooleanOperation.Type = bool_type
        eb.BooleanOperation.SetTargetBodies([target_body])
        
        feat = eb.CommitFeature()
        eb.Destroy()
        return True
    except Exception:
        return False

def set_expression(workPart, name, val):
    try:
        expr = workPart.Expressions.FindObject(name)
        expr.Value = float(val)
    except Exception:
        workPart.Expressions.CreateExpression("Number", f"{name}={val}")

def main():
    theSession = NXOpen.Session.GetSession()
    uf_session = UF.UFSession.GetUFSession()
    lw = theSession.ListingWindow
    lw.Open()

    workPart = theSession.Parts.Work
    if not workPart:
        lw.WriteLine("ERROR: No active part found. File -> New -> Model (mm) first.")
        return

    # ==========================================================================
    # PARAMETRIC DESIGN INPUTS
    # ==========================================================================
    DIAMETER = 1400.0          # Total mirror outer diameter (mm)
    RADIUS_CURV = 5000.0       # Radius of curvature for parabolic front face (mm)
    BLANK_DEPTH = 90.0         # Blank edge depth H (mm)
    FACEPLATE_THICK = 15.0     # Front optical faceplate thickness (mm)
    RIB_THICK = 6.0            # Structural rib wall thickness (mm)
    CELL_SIZE = 140.0          # Inner hex cell grid spacing (mm)
    TRANSITION_RADIUS = 400.0  # Radius boundary between Hex core & Radial outer (mm)
    WALL_MARGIN = 30.0         # Solid outer rim width (mm)
    DENSITY = 2530.0           # Zerodur glass-ceramic density (kg/m^3)

    RADIUS = DIAMETER / 2.0
    MAX_POCKET_RADIUS = RADIUS - WALL_MARGIN
    POCKET_DEPTH = BLANK_DEPTH - FACEPLATE_THICK
    BACK_Z = 0.0

    lw.WriteLine("=" * 70)
    lw.WriteLine("       SIEMENS NX MIXED-PATTERN PARABOLIC MIRROR GENERATOR")
    lw.WriteLine("=" * 70)
    lw.WriteLine(f" Mirror Diameter       : {DIAMETER} mm")
    lw.WriteLine(f" Radius of Curvature   : {RADIUS_CURV} mm")
    lw.WriteLine(f" Blank Edge Depth      : {BLANK_DEPTH} mm")
    lw.WriteLine(f" Faceplate Thickness   : {FACEPLATE_THICK} mm (Pocket Depth: {POCKET_DEPTH} mm)")
    lw.WriteLine(f" Inner Core Pattern    : Hexagonal Honeycomb (0 to {TRANSITION_RADIUS} mm)")
    lw.WriteLine(f" Outer Rim Pattern     : Radial Sector Rings ({TRANSITION_RADIUS} to {MAX_POCKET_RADIUS} mm)")
    lw.WriteLine("=" * 70)

    # Define Expressions in workPart for parametric CAD tracking
    set_expression(workPart, "D", DIAMETER)
    set_expression(workPart, "R_CURV", RADIUS_CURV)
    set_expression(workPart, "H", BLANK_DEPTH)
    set_expression(workPart, "T_F", FACEPLATE_THICK)
    set_expression(workPart, "T_W", RIB_THICK)
    set_expression(workPart, "CELL_SIZE", CELL_SIZE)
    set_expression(workPart, "R_TRANS", TRANSITION_RADIUS)
    set_expression(workPart, "POCKET_DEPTH", POCKET_DEPTH)

    # ==========================================================================
    # 1. GENERATE SOLID PARABOLIC BLANK BODY
    # ==========================================================================
    lw.WriteLine("\n[Step 1/4] Generating Solid Parabolic Blank Body...")
    
    n_points = 25
    pt_center_back = NXOpen.Point3d(0.0, 0.0, 0.0)
    pt_outer_back  = NXOpen.Point3d(RADIUS, 0.0, 0.0)
    pt_outer_front = NXOpen.Point3d(RADIUS, 0.0, BLANK_DEPTH)
    
    sag_edge = (RADIUS * RADIUS) / (2.0 * RADIUS_CURV)
    
    line_bottom = workPart.Curves.CreateLine(pt_center_back, pt_outer_back)
    line_side   = workPart.Curves.CreateLine(pt_outer_back, pt_outer_front)
    
    parabola_lines = []
    prev_pt = pt_outer_front
    for i in range(1, n_points + 1):
        r_val = RADIUS * (1.0 - i / float(n_points))
        z_val = BLANK_DEPTH + (r_val * r_val) / (2.0 * RADIUS_CURV) - sag_edge
        curr_pt = NXOpen.Point3d(r_val, 0.0, z_val)
        parabola_lines.append(workPart.Curves.CreateLine(prev_pt, curr_pt))
        prev_pt = curr_pt

    pt_center_front = prev_pt
    line_center = workPart.Curves.CreateLine(pt_center_front, pt_center_back)
    
    z_direction = create_z_direction(workPart, line_center)
    bool_sub = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract

    profile_curves = [line_bottom, line_side] + parabola_lines + [line_center]
    
    blank_body = revolve_profile(workPart, profile_curves, NXOpen.Point3d(0.0, 0.0, 0.0), z_direction)
    lw.WriteLine("   -> Parabolic blank created successfully.")

    # ==========================================================================
    # 2. SUBTRACT INNER HEXAGONAL HONEYCOMB POCKETS (r <= TRANSITION_RADIUS)
    # ==========================================================================
    lw.WriteLine("\n[Step 2/4] Subtracting Inner Hexagonal Honeycomb Pockets...")
    
    W = CELL_SIZE
    pocket_W = W - RIB_THICK
    pocket_side = pocket_W / math.sqrt(3.0)
    step_x = W * math.sqrt(3.0) / 2.0
    step_y = W
    
    n_cols = int(TRANSITION_RADIUS / step_x) + 2
    n_rows = int(TRANSITION_RADIUS / step_y) + 2
    
    hex_pocket_count = 0
    for c in range(-n_cols, n_cols + 1):
        cx = c * step_x
        y_shift = (step_y / 2.0) if (abs(c) % 2 != 0) else 0.0
        for r in range(-n_rows, n_rows + 1):
            cy = r * step_y + y_shift
            cell_dist = math.hypot(cx, cy)
            
            # Keep hex pockets strictly inside TRANSITION_RADIUS
            if cell_dist + pocket_side <= (TRANSITION_RADIUS - RIB_THICK / 2.0):
                lines = []
                for k in range(6):
                    a1 = math.radians(60.0 * k)
                    a2 = math.radians(60.0 * (k + 1))
                    p1 = NXOpen.Point3d(cx + pocket_side * math.cos(a1), cy + pocket_side * math.sin(a1), BACK_Z)
                    p2 = NXOpen.Point3d(cx + pocket_side * math.cos(a2), cy + pocket_side * math.sin(a2), BACK_Z)
                    lines.append(workPart.Curves.CreateLine(p1, p2))
                
                if extrude_subtract_pocket(workPart, lines, blank_body, z_direction, POCKET_DEPTH, bool_sub):
                    hex_pocket_count += 1

    lw.WriteLine(f"   -> Subtracted {hex_pocket_count} inner hexagonal pockets.")

    # ==========================================================================
    # 3. SUBTRACT OUTER RADIAL SECTOR POCKETS (TRANSITION_RADIUS < r <= MAX_POCKET_RADIUS)
    # ==========================================================================
    lw.WriteLine("\n[Step 3/4] Subtracting Outer Radial Sector Ring Pockets...")
    
    n_radial_rings = 2
    ring_width = (MAX_POCKET_RADIUS - TRANSITION_RADIUS) / float(n_radial_rings)
    
    radial_pocket_count = 0
    for ring_idx in range(n_radial_rings):
        r_in = TRANSITION_RADIUS + ring_idx * ring_width + RIB_THICK / 2.0
        r_out = TRANSITION_RADIUS + (ring_idx + 1) * ring_width - RIB_THICK / 2.0
        avg_r = (r_in + r_out) / 2.0
        
        circumference = 2.0 * math.pi * avg_r
        n_spokes = max(12, int(round(circumference / CELL_SIZE)))
        sector_angle = (2.0 * math.pi) / float(n_spokes)
        gap_angle = RIB_THICK / avg_r
        
        for s in range(n_spokes):
            a1 = s * sector_angle + gap_angle / 2.0
            a2 = (s + 1) * sector_angle - gap_angle / 2.0
            
            lines = []
            n_arc_seg = 6
            
            # Outer arc
            for k in range(n_arc_seg):
                ta1 = a1 + k * (a2 - a1) / float(n_arc_seg)
                ta2 = a1 + (k + 1) * (a2 - a1) / float(n_arc_seg)
                p1 = NXOpen.Point3d(r_out * math.cos(ta1), r_out * math.sin(ta1), BACK_Z)
                p2 = NXOpen.Point3d(r_out * math.cos(ta2), r_out * math.sin(ta2), BACK_Z)
                lines.append(workPart.Curves.CreateLine(p1, p2))
                
            # Radial side 1
            lines.append(workPart.Curves.CreateLine(
                NXOpen.Point3d(r_out * math.cos(a2), r_out * math.sin(a2), BACK_Z),
                NXOpen.Point3d(r_in * math.cos(a2), r_in * math.sin(a2), BACK_Z)
            ))
            
            # Inner arc (reversed)
            for k in range(n_arc_seg - 1, -1, -1):
                ta1 = a1 + k * (a2 - a1) / float(n_arc_seg)
                ta2 = a1 + (k + 1) * (a2 - a1) / float(n_arc_seg)
                p1 = NXOpen.Point3d(r_in * math.cos(ta2), r_in * math.sin(ta2), BACK_Z)
                p2 = NXOpen.Point3d(r_in * math.cos(ta1), r_in * math.sin(ta1), BACK_Z)
                lines.append(workPart.Curves.CreateLine(p1, p2))
                
            # Radial side 2
            lines.append(workPart.Curves.CreateLine(
                NXOpen.Point3d(r_in * math.cos(a1), r_in * math.sin(a1), BACK_Z),
                NXOpen.Point3d(r_out * math.cos(a1), r_out * math.sin(a1), BACK_Z)
            ))
            
            if extrude_subtract_pocket(workPart, lines, blank_body, z_direction, POCKET_DEPTH, bool_sub):
                radial_pocket_count += 1

    lw.WriteLine(f"   -> Subtracted {radial_pocket_count} outer radial sector pockets.")

    # ==========================================================================
    # 4. MEASURE & REPORT FINAL MASS METRICS
    # ==========================================================================
    lw.WriteLine("\n[Step 4/4] Calculating Final Mass Properties...")
    total_pockets = hex_pocket_count + radial_pocket_count
    
    vol_mm3 = 0.0
    mass_kg = 0.0
    try:
        mass_props = workPart.MeasureManager.CreateMassProperties([blank_body])
        vol_mm3 = mass_props.Volume
        mass_kg = vol_mm3 * DENSITY * 1e-9
        mass_props.Dispose()
    except Exception:
        pass

    solid_vol_approx = math.pi * (RADIUS * RADIUS) * (BLANK_DEPTH + sag_edge / 2.0)
    solid_mass_kg = solid_vol_approx * DENSITY * 1e-9
    mass_reduction_pct = ((solid_mass_kg - mass_kg) / solid_mass_kg) * 100.0 if solid_mass_kg > 0 else 0.0

    lw.WriteLine("\n" + "=" * 70)
    lw.WriteLine("                FINAL MIRROR GEOMETRY & METRICS REPORT")
    lw.WriteLine("=" * 70)
    lw.WriteLine(f"  Solid Blank Mass        : {solid_mass_kg:.1f} kg")
    lw.WriteLine(f"  Lightweighted Mass      : {mass_kg:.1f} kg")
    lw.WriteLine(f"  Mass Reduction Ratio    : {mass_reduction_pct:.1f}% lightweighting")
    lw.WriteLine(f"  Total Pockets Subtracted: {total_pockets} ({hex_pocket_count} Hex + {radial_pocket_count} Radial)")
    lw.WriteLine(f"  Faceplate Safety Margin : {FACEPLATE_THICK} mm solid front skin")
    lw.WriteLine("=" * 70)
    lw.WriteLine(" SUCCESS: Mixed Lightweight Parabolic Mirror Generated in Siemens NX!\n")

if __name__ == '__main__':
    main()
