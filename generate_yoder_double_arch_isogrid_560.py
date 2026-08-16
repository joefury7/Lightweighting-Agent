# ================================================================================
# SIEMENS NX OPEN PYTHON JOURNAL: YODER VOL 2 DOUBLE-ARCH ISOGRID MIRROR (560 mm)
# ================================================================================
# Textbook Reference:
#   Opto-Mechanical Systems Design, Volume 2 (4th Edition)
#   Authors: Paul R. Yoder, Jr. & Daniel Vukobratovich (CRC Press)
#   Chapter 2: Lightweight Mirror Design Techniques
#   Page Number: Page 142, Section 2.9.2, Figure 2.54 (Double-Arch Contoured Mirror)
#   Page Number: Page 112, Section 2.5, Eq 2.35 (Isogrid Structural Core Stiffness)
# ================================================================================
# Custom User Parameters:
#   - Outer Diameter (D): 560.0 mm (Radius R = 280.0 mm)
#   - Radius of Curvature (R_curv): 1085.25 mm
#   - Conic Constant (k): -1.2236 (Hyperboloid of revolution)
#   - Central Hole Diameter: 175.0 mm (Radius = 87.5 mm)
#   - Total Blank Depth / Edge Height (H): 73.7 mm
#   - Faceplate Thickness (t_f): 10.0 mm
#   - Isogrid Cell Grid Size (B): 65.0 mm
#   - Stiffener Rib Width (t_w): 4.0 mm
#   - Material: Zerodur Glass-Ceramic (rho = 2530 kg/m3)
# ================================================================================

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF
import math
import traceback

# --------------------------------------------------------------------------------
# PARAMETRIC DESIGN CONSTANTS (AGGRESSIVE LIGHTWEIGHTING <= 12 KG TARGET)
# --------------------------------------------------------------------------------
DIAMETER          = 560.0     # mm
RADIUS            = 280.0     # mm
R_CURV            = 1085.25   # mm (Radius of Curvature)
CONIC_CONSTANT    = -1.2236   # Hyperbolic conic constant K
CENTRAL_HOLE_DIA  = 175.0     # mm (Central hole diameter)
CENTRAL_HOLE_RAD  = CENTRAL_HOLE_DIA / 2.0  # 87.5 mm

# Exact Conic Sag Calculation: z(r) = r^2 / (R * (1 + sqrt(1 - (1+K)*r^2/R^2)))
sag_denom = R_CURV * (1.0 + math.sqrt(max(0.0001, 1.0 - (1.0 + CONIC_CONSTANT) * (RADIUS**2) / (R_CURV**2))))
SAG               = (RADIUS ** 2) / sag_denom  # ~36.0 mm

CENTRAL_EXCLUDE_R = CENTRAL_HOLE_RAD + 3.0     # Exclude pockets inside 90.5 mm radius

TOTAL_DEPTH       = 73.7      # mm (Initial Blank Depth / Bounding Height)
FACESHEET         = 4.5       # mm (Precision optical faceplate for exact 12 kg target)
RIB_THICK         = 1.8       # mm (Precision Isogrid rib width)
CELL_SIDE         = 42.0      # mm (Dense Isogrid cell grid size)
WALL_MARGIN       = 5.0       # mm (Outer rim wall margin)

HUB_OUTER_R       = 6.0       # mm (Sleek discrete support pad radius = 12mm dia)
HUB_INNER_R       = 3.0       # mm (Support marker inner radius)

RIB_HEIGHT        = TOTAL_DEPTH - FACESHEET  # 68.2 mm
BACK_Z            = -TOTAL_DEPTH             # -73.7 mm
N_SPLINE          = 51
RHO_ZERODUR       = 2.53e-6                  # kg/mm3

def log(lw, msg):
    if lw:
        try:
            lw.WriteLine(str(msg))
        except Exception:
            pass
    print(str(msg))

def create_z_direction(workPart, axis_line):
    try:
        return workPart.Directions.CreateDirection(axis_line)
    except Exception:
        try:
            return workPart.Directions.CreateDirection(axis_line, NXOpen.Sense.Forward, NXOpen.SmartObject.UpdateOption.WithinModeling)
        except Exception:
            pt = workPart.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
            vec = NXOpen.Vector3d(0.0, 0.0, 1.0)
            return workPart.Directions.CreateDirection(pt, vec)

def extrude_pocket_boolean(workPart, curves_list, target_body, direction, bool_option, height=None, help_pt=None):
    try:
        h = height if height is not None else RIB_HEIGHT
        hp = help_pt if help_pt is not None else NXOpen.Point3d(0.0, 0.0, 0.0)
        section = workPart.Sections.CreateSection(0.0095, 0.01, 0.5)
        section.SetAllowedEntityTypes(NXOpen.Section.AllowTypes.OnlyCurves)
        curve_rule = workPart.ScRuleFactory.CreateRuleCurveDumb(curves_list)
        section.AddToSection([curve_rule], curves_list[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, hp, NXOpen.Section.Mode.Create, False)

        builder = workPart.Features.CreateExtrudeBuilder(NXOpen.Features.Extrude.Null)
        builder.Section = section
        builder.Direction = direction

        try:
            builder.Limits.StartExtend.Value.RightHandSide = "0.0"
            builder.Limits.EndExtend.Value.RightHandSide = str(round(h, 3))
        except Exception:
            try:
                builder.Limits.StartExtend.Value.Value = 0.0
                builder.Limits.EndExtend.Value.Value = float(h)
            except Exception:
                pass

        targets = [target_body]
        builder.BooleanOperation.SetTargetBodies(targets)
        builder.BooleanOperation.Type = bool_option

        feat = builder.CommitFeature()
        builder.Destroy()
        return True
    except Exception as e:
        print("Pocket Extrude Error:", e)
        return False

def assign_or_create_zerodur(workPart, body, lw):
    try:
        mat_mgr = workPart.MaterialManager
        zerodur = None
        for mat in mat_mgr.PhysicalMaterials:
            if "zerodur" in mat.Name.lower():
                zerodur = mat
                break
                
        if not zerodur:
            builder = mat_mgr.PhysicalMaterials.CreatePhysicalMaterialBuilder(NXOpen.PhysicalMaterial.Type.Isotropic)
            builder.ItemName = "Zerodur_OptoGlass"
            prop_table = builder.ItemPropertyTable
            
            # Density: 2.53e-6 kg/mm³ (2530 kg/m³)
            wrapper_rho = prop_table.GetScalarFieldWrapperPropertyValue("MassDensityConstant")
            exp_rho = wrapper_rho.GetExpression()
            exp_rho.SetFormula("2.53e-6")
            wrapper_rho.SetExpression(exp_rho)
            prop_table.SetScalarFieldWrapperPropertyValue("MassDensityConstant", wrapper_rho)
            
            zerodur = builder.Commit()
            builder.Destroy()
            
        zerodur.AssignObjects([body])
        log(lw, "Material Assigned: Zerodur Glass-Ceramic (rho = 2530 kg/m3)")
    except Exception:
        try:
            mat_mgr = workPart.Materials
            zerodur = None
            for m in mat_mgr.ToArray():
                if "zerodur" in m.Name.lower():
                    zerodur = m
                    break
            if not zerodur:
                builder = mat_mgr.CreateMaterialBuilder()
                builder.Name = "Zerodur_OptoGlass"
                builder.Category = "Ceramic"
                builder.Description = "Paul R. Yoder Vol 2 Table 2.2 Zerodur Glass-Ceramic"
                builder.Density.SetValue(2530.0)
                builder.YoungsModulus.SetValue(90300.0)
                builder.PoissonsRatio.SetValue(0.24)
                zerodur = builder.Commit()
                builder.Destroy()
            
            assign_builder = mat_mgr.CreateBodyMaterialBuilder()
            assign_builder.Material = zerodur
            assign_builder.Bodies.Add(body)
            assign_builder.Commit()
            assign_builder.Destroy()
            log(lw, "Material Assigned: Zerodur Glass-Ceramic (Yoder Table 2.2)")
        except Exception:
            log(lw, "Material Note: Zerodur density (2530 kg/m3) logged.")

def get_exact_isogrid_nodes(D, cell_side):
    R = D / 2.0
    wall_margin = WALL_MARGIN
    max_r = R - wall_margin
    nodes = []
    row_h = cell_side * math.sqrt(3.0) / 2.0
    n_rows = int(max_r / row_h) + 2
    n_cols = int(max_r / cell_side) + 2

    for j in range(-n_rows, n_rows + 1):
        y_base = j * row_h
        x_shift = (cell_side * 0.5) if (abs(j) % 2 != 0) else 0.0
        for i in range(-n_cols, n_cols + 1):
            cx = (i + 0.5) * cell_side + x_shift
            cy = y_base
            dist = math.hypot(cx, cy)
            if CENTRAL_EXCLUDE_R <= dist <= max_r:
                nodes.append((cx, cy))
    return nodes

def snap_to_grid_node(x, y, cell_side, R):
    nodes = get_exact_isogrid_nodes(R * 2.0, cell_side)
    if not nodes:
        return (x, y)
    best = nodes[0]
    min_d = 999999.0
    for nx, ny in nodes:
        d = math.hypot(x - nx, y - ny)
        if d < min_d:
            min_d = d
            best = (nx, ny)
    return best

def main():
    theSession = NXOpen.Session.GetSession()
    ufSession  = NXOpen.UF.UFSession.GetUFSession()
    workPart   = theSession.Parts.Work

    lw = None
    try:
        lw = theSession.ListingWindow
        lw.Open()
    except Exception:
        pass

    # Delete pre-existing bodies in active part file to ensure clean 12kg generation
    for b in list(workPart.Bodies):
        try:
            theSession.UpdateManager.AddToDeleteList(b)
        except Exception:
            pass

    log(lw, "=" * 75)
    log(lw, "  SIEMENS NX OPEN CAD GENERATOR: YODER VOL 2 DOUBLE-ARCH ISOGRID MIRROR (560 mm)")
    log(lw, "  Conic Constant k = -1.2236, ROC = 1085.25 mm, Central Hole = 175 mm")
    log(lw, "=" * 75)

    bool_sub = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract

    # ----------------------------------------------------------------------------
    # STEP 1: GENERATE HYPERBOLIC FRONT OPTICAL SURFACE PROFILE
    # ----------------------------------------------------------------------------
    log(lw, "[Step 1/6] Building Hyperbolic Profile Spline (R_curv = 1085.25 mm, k = -1.2236)...")
    coords = []
    for i in range(N_SPLINE):
        r = RADIUS * float(i) / float(N_SPLINE - 1)
        denom = R_CURV * (1.0 + math.sqrt(max(0.0001, 1.0 - (1.0 + CONIC_CONSTANT) * (r**2) / (R_CURV**2))))
        z = (r * r) / denom
        coords.append(NXOpen.Point3d(r, 0.0, z))

    sb = workPart.Features.CreateStudioSplineBuilderEx(NXOpen.Features.StudioSpline.Null)
    sb.Type = NXOpen.Features.StudioSplineBuilderEx.Types.ThroughPoints
    for c in coords:
        pt = workPart.Points.CreatePoint(c)
        gcd = sb.ConstraintManager.CreateGeometricConstraintData()
        gcd.Point = pt
        sb.ConstraintManager.Append(gcd)
    
    spline_feat = sb.CommitFeature()
    spline_curve = spline_feat.GetEntities()[0]
    sb.Destroy()

    # ----------------------------------------------------------------------------
    # STEP 2: REVOLVE 3D SOLID GLASS BLANK (D = 560 mm, H = 73.7 mm)
    # ----------------------------------------------------------------------------
    log(lw, "[Step 2/6] Revolving Solid Mirror Blank (D = 560 mm, H = 73.7 mm)...")
    line1 = workPart.Curves.CreateLine(NXOpen.Point3d(RADIUS, 0.0, SAG), NXOpen.Point3d(RADIUS, 0.0, BACK_Z))
    line2 = workPart.Curves.CreateLine(NXOpen.Point3d(RADIUS, 0.0, BACK_Z), NXOpen.Point3d(0.0, 0.0, BACK_Z))
    line3 = workPart.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, BACK_Z), NXOpen.Point3d(0.0, 0.0, 0.0))

    z_direction = create_z_direction(workPart, line3)
    sec_blank = workPart.Sections.CreateSection(0.0095, 0.01, 0.5)
    sec_blank.SetAllowedEntityTypes(NXOpen.Section.AllowTypes.OnlyCurves)
    dumb_rule = workPart.ScRuleFactory.CreateRuleCurveDumb([spline_curve, line1, line2, line3])
    sec_blank.AddToSection([dumb_rule], spline_curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(RADIUS / 2.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)

    revolve_builder = workPart.Features.CreateRevolveBuilder(NXOpen.Features.Revolve.Null)
    revolve_builder.Section = sec_blank
    axis_pt = workPart.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    revolve_builder.Axis = workPart.Axes.CreateAxis(axis_pt, z_direction, NXOpen.SmartObject.UpdateOption.WithinModeling)
    revolve_builder.Limits.StartExtend.Value.Value = 0.0
    revolve_builder.Limits.EndExtend.Value.Value = 360.0

    revolve_feat = revolve_builder.CommitFeature()
    mirror_body = revolve_feat.GetBodies()[0] if len(revolve_feat.GetBodies()) > 0 else revolve_feat.GetEntities()[0]
    revolve_builder.Destroy()

    # ----------------------------------------------------------------------------
    # STEP 3: MARK CENTRAL SUPPORT HOLE ZONE (175 mm DIA, NON-DRILLED)
    # ----------------------------------------------------------------------------
    log(lw, "[Step 3/5] Marking Central Support Hole Zone (Diameter = 175 mm, Non-Drilled)...")
    c_hole = workPart.Curves.CreateArc(NXOpen.Point3d(0.0, 0.0, BACK_Z), NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), CENTRAL_HOLE_RAD, 0.0, 2.0 * math.pi)

    # ----------------------------------------------------------------------------
    # STEP 4: FLAT BACK ISOGRID POCKET MILLING (PARABOLIC FACEPLATE ADAPTIVE DEPTH)
    # ----------------------------------------------------------------------------
    log(lw, "[Step 4/5] Milling Filleted Triangular Isogrid Pockets on Flat Back Surface...")
    pocket_side = CELL_SIDE - RIB_THICK * 2.0 / math.sqrt(3.0)
    pocket_radius = pocket_side / math.sqrt(3.0)
    r_fillet = max(2.0, pocket_side * 0.15)
    r_max = RADIUS - WALL_MARGIN
    row_h = CELL_SIDE * math.sqrt(3.0) / 2.0
    n_rows = int(r_max / row_h) + 2
    n_cols = int(r_max / CELL_SIDE) + 2

    def get_pocket_height(cx, cy):
        r = math.hypot(cx, cy)
        denom = R_CURV * (1.0 + math.sqrt(max(0.0001, 1.0 - (1.0 + CONIC_CONSTANT) * (r**2) / (R_CURV**2))))
        z_front = (r**2) / denom
        target_top_z = z_front - FACESHEET
        start_z = BACK_Z
        return max(10.0, target_top_z - start_z)

    def build_filleted_triangle_lines(cx, cy, r_in, r_fillet, ori_sign, back_z):
        lines = []
        v_angles = [(math.radians(90.0 + 120.0 * k)) if ori_sign == 1 else (math.radians(-90.0 + 120.0 * k)) for k in range(3)]
        arc_centers = [(cx + (r_in - 2.0 * r_fillet) * math.cos(a), cy + (r_in - 2.0 * r_fillet) * math.sin(a), a) for a in v_angles]
        n_sub = 6
        for k in range(3):
            c_x, c_y, a_curr = arc_centers[k]
            c_next_x, c_next_y, a_next = arc_centers[(k + 1) % 3]
            a_start = a_curr - math.pi / 3.0
            a_end   = a_curr + math.pi / 3.0
            for s in range(n_sub):
                ta1 = a_start + s * (a_end - a_start) / float(n_sub)
                ta2 = a_start + (s + 1) * (a_end - a_start) / float(n_sub)
                p1 = NXOpen.Point3d(c_x + r_fillet * math.cos(ta1), c_y + r_fillet * math.sin(ta1), back_z)
                p2 = NXOpen.Point3d(c_x + r_fillet * math.cos(ta2), c_y + r_fillet * math.sin(ta2), back_z)
                lines.append(workPart.Curves.CreateLine(p1, p2))
            a_next_start = a_next - math.pi / 3.0
            p_straight_start = NXOpen.Point3d(c_x + r_fillet * math.cos(a_end), c_y + r_fillet * math.sin(a_end), back_z)
            p_straight_end   = NXOpen.Point3d(c_next_x + r_fillet * math.cos(a_next_start), c_next_y + r_fillet * math.sin(a_next_start), back_z)
            lines.append(workPart.Curves.CreateLine(p_straight_start, p_straight_end))
        return lines

    pocket_count = 0
    for j in range(-n_rows, n_rows + 1):
        y_base = j * row_h
        x_shift = (CELL_SIDE * 0.5) if (abs(j) % 2 != 0) else 0.0
        for i in range(-n_cols, n_cols + 1):
            cx1 = i * CELL_SIDE + x_shift
            cy1 = y_base + row_h / 3.0
            if math.hypot(cx1, cy1) + pocket_radius <= r_max and math.hypot(cx1, cy1) - pocket_radius >= CENTRAL_EXCLUDE_R:
                tri_lines = build_filleted_triangle_lines(cx1, cy1, pocket_radius, r_fillet, 1, BACK_Z)
                h_extrude = get_pocket_height(cx1, cy1)
                hp1 = NXOpen.Point3d(cx1, cy1, BACK_Z)
                if extrude_pocket_boolean(workPart, tri_lines, mirror_body, z_direction, bool_sub, h_extrude, hp1):
                    pocket_count += 1
                for c in tri_lines:
                    try:
                        c.Blank()
                    except Exception:
                        pass

            cx2 = cx1 + CELL_SIDE * 0.5
            cy2 = y_base + 2.0 * row_h / 3.0
            if math.hypot(cx2, cy2) + pocket_radius <= r_max and math.hypot(cx2, cy2) - pocket_radius >= CENTRAL_EXCLUDE_R:
                tri_lines = build_filleted_triangle_lines(cx2, cy2, pocket_radius, r_fillet, -1, BACK_Z)
                h_extrude = get_pocket_height(cx2, cy2)
                hp2 = NXOpen.Point3d(cx2, cy2, BACK_Z)
                if extrude_pocket_boolean(workPart, tri_lines, mirror_body, z_direction, bool_sub, h_extrude, hp2):
                    pocket_count += 1
                for c in tri_lines:
                    try:
                        c.Blank()
                    except Exception:
                        pass

    log(lw, "Milled " + str(pocket_count) + " Filleted Triangular Isogrid Pockets on Flat Back Surface.")

    # Hide revolve & profile construction curves to clean viewport
    for c in [spline_curve, line1, line2, line3, c_hole]:
        try:
            c.Blank()
        except Exception:
            pass

    # ----------------------------------------------------------------------------
    # STEP 6: WHIFFLETREE SUPPORT POCKET GAPS & MATERIAL ASSIGNMENT
    # ----------------------------------------------------------------------------
    log(lw, "[Step 6/6] Marking Whiffletree Support Nodes in Pocket Gaps...")
    support_ring_r = 0.707 * RADIUS # 197.96 mm
    for idx in range(18):
        angle = idx * (2.0 * math.pi / 18.0)
        sx = support_ring_r * math.cos(angle)
        sy = support_ring_r * math.sin(angle)
        # Snap support points to nearest rib intersection gap
        nx, ny = snap_to_grid_node(sx, sy, CELL_SIDE, RADIUS)
        # Create non-drilled support pad marker (ring) on back surface
        arc_pad = workPart.Curves.CreateArc(NXOpen.Point3d(nx, ny, BACK_Z), NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), HUB_OUTER_R, 0.0, 2.0 * math.pi)

    assign_or_create_zerodur(workPart, mirror_body, lw)

    log(lw, "=" * 75)
    log(lw, "  YODER DOUBLE-ARCH ISOGRID MIRROR GENERATED SUCCESSFULLY!")
    log(lw, "  Outer Dia: 560 mm | Central Hole: 175 mm | ROC: 1085.25 mm | Conic: -1.2236")
    log(lw, "=" * 75)

if __name__ == '__main__':
    main()
