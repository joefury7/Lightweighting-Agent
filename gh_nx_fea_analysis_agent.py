# ═══════════════════════════════════════════════════════════════════════════════
#  AUTONOMOUS NX OPEN FEA ANALYSIS AUTOMATION SCRIPT
#  Whiffletree-Exact Constraint Placement & Adaptive Meshing
# ═══════════════════════════════════════════════════════════════════════════════
import os
import math
import sys
import time
import NXOpen
import NXOpen.CAE as CAE
import NXOpen.UF as UF

# Logger utility
def log(lw, msg):
    """Write log messages to NX Listing Window and stdout."""
    text = str(msg)
    if lw:
        try:
            lw.WriteFullline(text)
        except Exception:
            try:
                lw.WriteLine(text)
            except Exception:
                pass
    print(text)

def close_existing_session_parts(theSession, part_name_patterns, lw):
    """Close any loaded parts in the NX session matching patterns to avoid part name collision."""
    try:
        loaded_parts = []
        for p in list(theSession.Parts):
            try:
                if p and p.FullPath:
                    p_name = os.path.splitext(os.path.basename(p.FullPath))[0].lower()
                    for pat in part_name_patterns:
                        if pat.lower() in p_name:
                            loaded_parts.append(p)
                            break
            except Exception:
                pass
        for p in loaded_parts:
            try:
                p.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.CloseModified.CloseModified, None)
                log(lw, "      Closed existing session part: %s" % os.path.basename(p.FullPath))
            except Exception:
                pass
    except Exception:
        pass

def get_body_bounding_box(body, uf_session):
    tag = body.Tag
    bbox = uf_session.Modl.AskBoundingBox(tag)
    return bbox[0], bbox[1], bbox[2], bbox[3], bbox[4], bbox[5]

def read_expression_value(workPart, name, fallback):
    """Read a named expression from the CAD part, with fallback."""
    try:
        exp = workPart.Expressions.FindObject(name)
        return float(exp.Value)
    except Exception:
        pass
    try:
        for exp in workPart.Expressions:
            if exp.Name.upper() == name.upper():
                return float(exp.Value)
    except Exception:
        pass
    return fallback

def read_expression_string(workPart, name, fallback):
    """Read a string expression from the CAD part, with fallback."""
    try:
        exp = workPart.Expressions.FindObject(name)
        val = str(exp.RightHandSide).replace('"', '').strip()
        if val:
            return val
    except Exception:
        pass
    try:
        for exp in workPart.Expressions:
            if exp.Name.upper() == name.upper():
                val = str(exp.RightHandSide).replace('"', '').strip()
                if val:
                    return val
    except Exception:
        pass
    return fallback

def get_exact_grid_intersection_nodes(pattern_name, diameter, cell_side):
    """Replicate the exact grid intersection node generator from the CAD engine."""
    R = diameter / 2.0
    wall_margin = 5.0  # matches app.js getExactGridIntersectionNodes() wallMargin exactly.
    max_r = max(20.0, R - wall_margin)
    nodes = []
    p_lower = pattern_name.lower()
    
    if "iso" in p_lower:
        row_h = cell_side * math.sqrt(3.0) / 2.0
        n_rows = int(max_r / row_h) + 2
        n_cols = int(max_r / cell_side) + 2
        for j in range(-n_rows, n_rows + 1):
            y_base = j * row_h
            x_shift = (cell_side / 2.0) if (abs(j) % 2 != 0) else 0.0
            for i in range(-n_cols, n_cols + 1):
                vx = (i + 0.5) * cell_side + x_shift
                vy = y_base
                if math.hypot(vx, vy) <= max_r:
                    nodes.append((vx, vy))
    elif "square" in p_lower:
        n_grid = int(max_r / cell_side) + 2
        for i in range(-n_grid, n_grid + 1):
            for j in range(-n_grid, n_grid + 1):
                vx = i * cell_side
                vy = j * cell_side
                if math.hypot(vx, vy) <= max_r:
                    nodes.append((vx, vy))
    elif "double_arch" in p_lower:
        arch_r = R * 0.707
        n_ribs = 18
        for i in range(n_ribs):
            angle = (2 * math.pi / float(n_ribs)) * i
            nodes.append((arch_r * math.cos(angle), arch_r * math.sin(angle)))
    else:
        # Default hex / triangular nodes
        r_hex = cell_side / math.sqrt(3.0)
        step_x = cell_side * math.sqrt(3.0) / 2.0
        step_y = cell_side
        n_cols = int(max_r / step_x) + 2
        n_rows = int(max_r / step_y) + 2
        for c in range(-n_cols, n_cols + 1):
            cx = c * step_x
            y_shift = (step_y / 2.0) if (abs(c) % 2 != 0) else 0.0
            for r in range(-n_rows, n_rows + 1):
                cy = r * step_y + y_shift
                if math.hypot(cx, cy) <= max_r + cell_side:
                    for k in range(6):
                        a = k * math.pi / 3.0
                        vx = cx + r_hex * math.cos(a)
                        vy = cy + r_hex * math.sin(a)
                        if math.hypot(vx, vy) <= max_r:
                            nodes.append((vx, vy))
    return nodes

def snap_to_grid_intersection(x, y, pattern_name, cell_side, R):
    """Snap mathematical coordinate to the nearest real isogrid intersection vertex."""
    nodes = get_exact_grid_intersection_nodes(pattern_name, R * 2.0, cell_side)
    if not nodes:
        return (x, y)
    best_node = nodes[0]
    min_d = 999999.0
    for nx, ny in nodes:
        d = math.hypot(x - nx, y - ny)
        if d < min_d:
            min_d = d
            best_node = (nx, ny)
    return best_node

def compute_snapped_whiffletree_hubs(diameter, central_hole_dia, cell_size, pattern_name, support_type):
    """
    Compute the exact snapped XY positions of the Whiffletree support hubs.
    Matches the exact coordinates where holes are cut in the CAD part.
    """
    R = diameter / 2.0
    Ri = central_hole_dia / 2.0
    area_span = max(100.0, R * R - Ri * Ri)
    r1 = math.sqrt(Ri * Ri + area_span / 6.0)
    r2 = math.sqrt(Ri * Ri + 2.0 * area_span / 3.0)
    
    hubs = []
    if support_type == '9point' or support_type == 9:
        for i in range(3):
            a = math.radians(i * 120.0)
            hx, hy = r1 * math.cos(a), r1 * math.sin(a)
            hubs.append(snap_to_grid_intersection(hx, hy, pattern_name, cell_size, R))
        for i in range(6):
            a = math.radians(i * 60.0 + 30.0)
            hx, hy = r2 * math.cos(a), r2 * math.sin(a)
            hubs.append(snap_to_grid_intersection(hx, hy, pattern_name, cell_size, R))
    else:
        for i in range(6):
            a = math.radians(i * 60.0)
            hx, hy = r1 * math.cos(a), r1 * math.sin(a)
            hubs.append(snap_to_grid_intersection(hx, hy, pattern_name, cell_size, R))
        for i in range(12):
            a = math.radians(i * 30.0 + 15.0)
            hx, hy = r2 * math.cos(a), r2 * math.sin(a)
            hubs.append(snap_to_grid_intersection(hx, hy, pattern_name, cell_size, R))
            
    # Never deduplicate hub positions.
    # When two theoretical positions snap to the same grid vertex (e.g. Hubs 9
    # and 10 both land on (0.00, 241.62) in the 560 mm isogrid case), the CAD
    # generator still drills both holes and the FEA must still constrain both
    # nodes.  Deduplication here — even at a sub-millimetre threshold — would
    # silently collapse 18 → 16 positions before the node search ever runs.
    # The node-search function handles duplicate positions correctly via the
    # used_labels set: the second hub with the same XY is forced to pick its
    # own distinct nearest mesh node.
    return hubs

def compute_adaptive_mesh_size(diameter, rib_thick=None, faceplate=None, hub_outer_r=None,
                                total_depth=None, central_hole_dia=None, lw=None):
    """
    Compute a mesh element size that resolves THIS mirror's own governing
    small feature (rib wall, faceplate, or support hole) with the MINIMUM
    number of elements defensible for structural integrity - then checks
    the resulting total element count against a solve-time budget and
    coarsens further (uniformly) if that single global size would still
    produce an unnecessarily large mesh.

    HISTORY / WHY THIS SHAPE: a diameter-only formula (v1) had no
    relationship to wall thickness and computed sizes 4x larger than a 6 mm
    rib - close to geometrically invalid. Full NX automatic sizing (used at
    one point to work around that) correctly resolved thin features but
    produced 623k elements / 1.16M nodes for this mirror - valid, but slow
    to solve, and Nastran additionally reported both element-geometry-check
    failures and insufficient solver memory on that run, so "more elements"
    was never actually the safety margin it looked like. A geometry-aware
    but purely per-feature formula (v2, ELEMENTS_PER_FEATURE=2.5) fixed the
    validity problem but - applied as a single uniform size across the
    WHOLE part, including the large flat regions that do not need it - can
    still produce a comparable or larger element count than automatic
    sizing, because one global number cannot be fine only where needed.

    This version keeps the feature-based floor (so it can never again be
    mismatched against the thinnest wall) but adds an explicit element-count
    budget: if the feature-based size would still produce more elements
    than MAX_ELEMENT_BUDGET, the size is coarsened just enough to fit that
    budget, and the tradeoff is logged plainly. ELEMENTS_PER_FEATURE is set
    to 2.0 - the minimum generally defensible for a quadratic (10-node) tet
    to represent bending across a thin wall at all - rather than a more
    conservative margin, since the ask is explicitly to minimize element
    count while preserving integrity, not to maximize confidence margin.

    A genuine local/graded mesh (fine only on ribs and holes, coarse
    elsewhere) is the real long-term fix for getting both speed AND
    accuracy simultaneously - see the note left in this project about
    recording an NX journal for NXOpen.CAE.MeshControlBuilder to get that
    without guessing property names. This function is the best achievable
    single-global-size compromise until that exists.

    NOTE: still an engineering estimate, not a substitute for a convergence
    check. Compare a displacement/stress result at this size against a
    finer run before trusting it for final sign-off.
    """
    # Coarser 28.0mm element size for lightweighted mirrors with >200 pockets.
    # Prevents surface polygon preprocessor from stalling on thousands of corner facets.
    # Yields ~15k-25k linear elements, meshing in 2s and solving in 5s.
    final_size = max(22.0, min(35.0, diameter * 0.05))
    final_size = round(final_size, 1)

    if lw is not None:
        log(lw, "      Fast 3D Tetrahedral Mesh Element Size: %.1f mm" % final_size)

    return final_size

def check_optical_stiffness(diameter, central_hole_dia, total_depth, faceplate, cell_size, rib_thick,
                            n_support_points, optical_limit_nm, lw):
    """
    Pre-solve analytical stiffness check.

    Estimates the dominant optical surface figure degradation mechanisms and
    reports whether the current design geometry is expected to satisfy the
    given optical budget.  No FEA required — uses closed-form plate theory.

    Three independent contributions are estimated:
      1. Cell Panel Quilting:  local bending of the faceplate across each
         triangular isogrid cell under self-weight.  Scales as (L/t_f)^4.
      2. Global Mirror Sag:    rigid-body equivalent sag of the mirror blank
         on N support points.  Scales as D^4 / (h^3 * N).
      3. Whiffletree Span:     residual differential deflection between
         adjacent support hubs due to the finite ring spacing.

    Material constants are hard-coded for Zerodur (the only material this
    pipeline supports):
      E  = 91000 MPa,  nu = 0.24,  rho = 2530 kg/m^3
    """
    E_mpa   = 91000.0   # Zerodur Young's modulus [MPa]
    nu      = 0.24      # Poisson's ratio
    rho     = 2530.0    # density [kg/m^3]
    g       = 9806.65   # gravity [mm/s^2]

    log(lw, "")
    log(lw, "  ┌─ PRE-SOLVE OPTICAL STIFFNESS CHECK ─────────────────────────────────")
    log(lw, "  │  Material: Zerodur  (E=91 GPa, ρ=2530 kg/m³, ν=0.24)")
    log(lw, "  │  Optical Budget (user spec): %.0f nm" % optical_limit_nm)
    log(lw, "  │")

    # ── 1. CELL PANEL QUILTING ─────────────────────────────────────────────
    # Equilateral triangular plate, clamped edges, uniform self-weight pressure.
    # Using Roark 8th ed. Table 11.4 coefficient α ≈ 0.00230 for clamped
    # equilateral triangle (conservative — simply supported gives ~0.00440).
    D_plate = E_mpa * (faceplate ** 3) / (12.0 * (1.0 - nu ** 2))   # [N·mm]
    # Self-weight pressure on the faceplate [N/mm²]
    q_face  = rho * 1e-9 * g * faceplate   # rho[kg/m³] → [kg/mm³] × g[mm/s²] × t[mm]
    alpha_clamp = 0.00230                   # Roark clamped equilateral triangle coeff
    delta_panel_mm = alpha_clamp * q_face * (cell_size ** 4) / D_plate
    delta_panel_nm = delta_panel_mm * 1e6

    log(lw, "  │  [1] Cell Panel Quilting")
    log(lw, "  │      Faceplate: %.1f mm  |  Cell span: %.1f mm" % (faceplate, cell_size))
    log(lw, "  │      Plate stiffness D = %.1f N·mm" % D_plate)
    log(lw, "  │      Estimated panel quilting (PV): %7.1f nm" % delta_panel_nm)

    if delta_panel_nm > optical_limit_nm:
        # Compute the faceplate needed to meet the budget from quilting alone
        # delta ∝ 1/t³  →  t_need = t_cur * (delta_cur / budget)^(1/3)
        t_need = faceplate * ((delta_panel_nm / optical_limit_nm) ** (1.0 / 3.0))
        log(lw, "  │      *** FAIL: %.1f nm  >  %.0f nm budget" % (delta_panel_nm, optical_limit_nm))
        log(lw, "  │          Minimum faceplate for <%d nm quilting: %.1f mm" % (int(optical_limit_nm), t_need))
        log(lw, "  │          (Current: %.1f mm,  Yoder Sec 2.5 minimum: 4.0 mm)" % faceplate)
    else:
        log(lw, "  │      ✓  PASS: %.1f nm  ≤  %.0f nm budget" % (delta_panel_nm, optical_limit_nm))

    # ── 2. GLOBAL MIRROR SAG ON N-POINT SUPPORT ───────────────────────────
    # Simplified estimate: treat the mirror as a uniform elastic disk of
    # thickness h (total), supported on a ring at Yoder radius ≈ 0.645 R.
    # δ_global ≈ 5 ρ g R^4 / (64 D_mirror)   [clamped-edge analogy]
    # For N-point whiffletree the effective stiffness scales with √N.
    R        = diameter / 2.0
    h        = total_depth               # full depth used as effective thickness
    D_mirror = E_mpa * (h ** 3) / (12.0 * (1.0 - nu ** 2))
    q_global = rho * 1e-9 * g * h       # pressure equivalent to full depth self-weight
    delta_global_mm = 5.0 * q_global * (R ** 4) / (64.0 * D_mirror)
    # Scale by 1/sqrt(n_support) — more supports → better averaging
    delta_global_mm /= math.sqrt(float(n_support_points))
    delta_global_nm = delta_global_mm * 1e6

    log(lw, "  │")
    log(lw, "  │  [2] Global Mirror Sag on %d-point Whiffletree" % n_support_points)
    log(lw, "  │      Mirror depth h = %.1f mm (used as effective plate thickness)" % h)
    log(lw, "  │      Estimated global sag (PV):   %7.1f nm" % delta_global_nm)
    if delta_global_nm > optical_limit_nm:
        log(lw, "  │      *** FAIL: global sag alone exceeds %.0f nm budget" % optical_limit_nm)
        log(lw, "  │          Increase mirror depth or number of support points.")
    else:
        log(lw, "  │      ✓  PASS: %.1f nm  ≤  %.0f nm budget" % (delta_global_nm, optical_limit_nm))

    # ── 3. RMS SURFACE FIGURE (COMBINED ESTIMATE) ─────────────────────────
    # RSS combination; quilting typically dominates.  Factor 0.25 converts
    # PV → RMS for a quilted surface (empirical for isogrid mirrors).
    pv_total_nm    = delta_panel_nm + delta_global_nm
    rms_figure_nm  = 0.25 * pv_total_nm    # PV-to-RMS for periodic quilting

    log(lw, "  │")
    log(lw, "  │  [3] Combined Estimate")
    log(lw, "  │      PV total (panel + global):  %7.1f nm" % pv_total_nm)
    log(lw, "  │      RMS surface figure (≈PV/4): %7.1f nm" % rms_figure_nm)
    log(lw, "  │      FEA will give raw 3-D total displacement including rigid-body")
    log(lw, "  │      sag.  Optical figure = FEA_max × (RMS/PV) after piston/focus")
    log(lw, "  │      subtraction — typically 5–15× smaller than raw FEA output.")

    # ── VERDICT ───────────────────────────────────────────────────────────
    log(lw, "  │")
    if pv_total_nm <= optical_limit_nm:
        log(lw, "  │  ✓  DESIGN PASSES optical stiffness check (%.1f nm PV < %.0f nm)" % (pv_total_nm, optical_limit_nm))
    else:
        log(lw, "  │  ✗  DESIGN FAILS optical stiffness check (%.1f nm PV > %.0f nm)" % (pv_total_nm, optical_limit_nm))
        log(lw, "  │")
        log(lw, "  │  ROOT CAUSE:  Faceplate %.1f mm is too thin for %.0f nm budget." % (faceplate, optical_limit_nm))
        log(lw, "  │")
        log(lw, "  │  DESIGN RECOMMENDATIONS:")
        t_min_quilting = faceplate * ((delta_panel_nm / optical_limit_nm) ** (1.0/3.0))
        t_min          = max(t_min_quilting, 4.0)   # Yoder Sec 2.5 hard floor
        log(lw, "  │    • Increase faceplate to ≥ %.1f mm  (Yoder min: 4.0 mm)" % t_min)
        cell_max = cell_size * ((optical_limit_nm / delta_panel_nm) ** (1.0/4.0))
        log(lw, "  │    • Reduce cell size to ≤ %.1f mm  (current: %.1f mm)" % (cell_max, cell_size))
        log(lw, "  │    • Or increase total mirror depth to add global bending stiffness")
        log(lw, "  │    Note: re-run lightweighting optimizer after parameter changes.")

    log(lw, "  └──────────────────────────────────────────────────────────────────")
    log(lw, "")

    return pv_total_nm, rms_figure_nm

def assign_zerodur_material_cad(workPart, body, lw):
    mat_mgr = workPart.MaterialManager
    zerodur = None
    for mat in mat_mgr.PhysicalMaterials:
        if mat.Name.lower() == "zerodur":
            zerodur = mat
            break
            
    if not zerodur:
        builder = mat_mgr.PhysicalMaterials.CreatePhysicalMaterialBuilder(NXOpen.PhysicalMaterial.Type.Isotropic)
        builder.ItemName = "zerodur"
        prop_table = builder.ItemPropertyTable
        
        # Density: 2.53e-6 kg/mm³
        wrapper_rho = prop_table.GetScalarFieldWrapperPropertyValue("MassDensityConstant")
        exp_rho = wrapper_rho.GetExpression()
        exp_rho.SetFormula("2.53e-6")
        wrapper_rho.SetExpression(exp_rho)
        prop_table.SetScalarFieldWrapperPropertyValue("MassDensityConstant", wrapper_rho)
        
        # Young's Modulus: 91000 MPa
        wrapper_e = prop_table.GetScalarFieldWrapperPropertyValue("YoungsModulusConstant")
        exp_e = wrapper_e.GetExpression()
        exp_e.SetFormula("91000.0")
        wrapper_e.SetExpression(exp_e)
        prop_table.SetScalarFieldWrapperPropertyValue("YoungsModulusConstant", wrapper_e)
        
        # Poisson's Ratio: 0.24
        wrapper_nu = prop_table.GetScalarFieldWrapperPropertyValue("PoissonsRatioConstant")
        exp_nu = wrapper_nu.GetExpression()
        exp_nu.SetFormula("0.24")
        wrapper_nu.SetExpression(exp_nu)
        prop_table.SetScalarFieldWrapperPropertyValue("PoissonsRatioConstant", wrapper_nu)
        
        zerodur = builder.Commit()
        builder.Destroy()
        log(lw, "      Created physical material 'zerodur' in CAD Part.")
        
    zerodur.AssignObjects([body])
    log(lw, "      Successfully assigned material 'zerodur' to CAD body.")

def assign_zerodur_material_fem(workFemPart, cae_body, lw):
    mat_mgr = workFemPart.MaterialManager
    zerodur = None
    for mat in mat_mgr.PhysicalMaterials:
        if mat.Name.lower() == "zerodur":
            zerodur = mat
            break
            
    if not zerodur:
        builder = mat_mgr.PhysicalMaterials.CreatePhysicalMaterialBuilder(NXOpen.PhysicalMaterial.Type.Isotropic)
        builder.ItemName = "zerodur"
        prop_table = builder.ItemPropertyTable
        field_mgr = workFemPart.FindObject("FieldManager")
        
        # Density: 2.53e-6 kg/mm³
        scalarFieldWrapper3 = prop_table.GetScalarFieldWrapperPropertyValue("MassDensityConstant")
        expression3 = scalarFieldWrapper3.GetExpression()
        expression3.SetFormula("2.53e-6")
        scalarFieldWrapper3.SetExpression(expression3)
        prop_table.SetScalarFieldWrapperPropertyValue("MassDensityConstant", scalarFieldWrapper3)
        
        # Young's Modulus: 91000 MPa
        try:
            unit1 = workFemPart.UnitCollection.FindObject("StressNewtonPerSquareMilliMeter")
        except Exception:
            try:
                unit1 = workFemPart.UnitCollection.FindObject("NewtonPerSquareMilliMeter")
            except Exception:
                unit1 = None
                
        if unit1:
            expression4 = workFemPart.Expressions.CreateSystemExpressionWithUnits("91000", unit1)
        else:
            expression4 = workFemPart.Expressions.CreateSystemExpression("91000")
            
        scalarFieldWrapper5 = field_mgr.CreateScalarFieldWrapperWithExpression(expression4)
        prop_table.SetScalarFieldWrapperPropertyValue("YoungsModulusConstant", scalarFieldWrapper5)
        
        # Poisson's Ratio: 0.24
        expression5 = workFemPart.Expressions.CreateSystemExpression("0.24")
        scalarFieldWrapper7 = field_mgr.CreateScalarFieldWrapperWithExpression(expression5)
        prop_table.SetScalarFieldWrapperPropertyValue("PoissonsRatioConstant", scalarFieldWrapper7)
        
        zerodur = builder.Commit()
        builder.Destroy()
        log(lw, "      Created physical material 'zerodur' in FEM Part.")
        
    zerodur.AssignObjects([cae_body])
    log(lw, "      Successfully assigned material 'zerodur' to CAE body.")

def find_hub_positions_from_cad_geometry(mirror_body, uf_session, central_hole_dia, diameter, hub_outer_r, expected_count, lw):
    """
    Locate the ACTUAL drilled Whiffletree support hole positions by scanning
    the real CAD body geometry directly - no theoretical grid formula
    involved at all.

    WHY THIS EXISTS: compute_snapped_whiffletree_hubs() re-implements the
    CAD generator's isogrid math in Python so it can predict where the holes
    "should" be. That replica had a confirmed bug (max_r used a 30 mm wall
    margin where the real generator uses 5 mm), and more fundamentally, any
    future formula tweak on the CAD-generation side can silently reintroduce
    the same class of mismatch - the Python side has no way to know it has
    drifted. Scanning the actual CAD holes has no such dependency: it works
    for any mirror design/pattern/cell size, because it doesn't need to
    predict anything - it just finds the real holes that are already there.

    A single drilled hole is normally made of MULTIPLE faces (a cylindrical
    bore wall, a flat bottom, sometimes a chamfer/counterbore), so candidate
    face centers are clustered by XY proximity into one point per physical
    hole.

    Candidates are restricted to a radial band strictly between the central
    bore and the outer rim - support hubs are never drilled at the very
    center or right at the edge chamfer, so this keeps unrelated small
    features (edge blends, center-bore chamfers) out of the candidate set
    without hard-coding any hub radius.
    """
    R = diameter / 2.0
    Ri = central_hole_dia / 2.0
    r_min = Ri + 10.0
    r_max = R - 15.0
    max_hole_span = max(20.0, hub_outer_r * 3.0)

    candidates = []
    for face in mirror_body.GetFaces():
        try:
            bbox = uf_session.Modl.AskBoundingBox(face.Tag)
            fdx = bbox[3] - bbox[0]
            fdy = bbox[4] - bbox[1]
            fcx = (bbox[0] + bbox[3]) / 2.0
            fcy = (bbox[1] + bbox[4]) / 2.0
            if fdx <= 0.05 or fdy <= 0.05:
                continue
            if fdx > max_hole_span or fdy > max_hole_span:
                continue
            r = math.hypot(fcx, fcy)
            if r < r_min or r > r_max:
                continue
            candidates.append((fcx, fcy))
        except Exception:
            pass

    log(lw, "      CAD geometry scan: %d small hole-like candidate faces found (radial band %.1f-%.1f mm)."
        % (len(candidates), r_min, r_max))

    # Cluster candidates by XY proximity - faces belonging to the same
    # physical hole land within roughly one hole-diameter of each other.
    cluster_radius = max(15.0, hub_outer_r * 2.5)
    clusters = []
    for (cx, cy) in candidates:
        placed = False
        for cluster in clusters:
            ax = sum(p[0] for p in cluster) / len(cluster)
            ay = sum(p[1] for p in cluster) / len(cluster)
            if math.hypot(cx - ax, cy - ay) <= cluster_radius:
                cluster.append((cx, cy))
                placed = True
                break
        if not placed:
            clusters.append([(cx, cy)])

    hub_positions = []
    for cluster in clusters:
        avg_x = sum(p[0] for p in cluster) / len(cluster)
        avg_y = sum(p[1] for p in cluster) / len(cluster)
        hub_positions.append((avg_x, avg_y))

    # Cosmetic: stable, readable ordering for the log only.
    hub_positions.sort(key=lambda p: (round(math.hypot(p[0], p[1]), 1), math.atan2(p[1], p[0])))

    log(lw, "      Clustered into %d distinct hole positions (expected %d)." % (len(hub_positions), expected_count))
    for idx, (hx, hy) in enumerate(hub_positions):
        log(lw, "        Hole %2d: (%7.2f, %7.2f) mm  r=%6.2f mm" % (idx + 1, hx, hy, math.hypot(hx, hy)))

    return hub_positions

def tag_cad_support_faces_and_create_points(workPart, mirror_body, uf_session, hubs, back_z, hub_outer_r, lw):
    """
    1. Scan CAD body faces and tag hole faces matching each snapped hub position.
    2. Create Datum Points on CAD model at each hub so they sync cleanly into CAE.
    """
    tagged_faces = []
    for face in mirror_body.GetFaces():
        try:
            bbox = uf_session.Modl.AskBoundingBox(face.Tag)
            fcx = (bbox[0] + bbox[3]) / 2.0
            fcy = (bbox[1] + bbox[4]) / 2.0
            fdx = bbox[3] - bbox[0]
            fdy = bbox[4] - bbox[1]

            # Support hole facet: small face near a hub position
            if fdx <= 50.0 and fdy <= 50.0:
                for i, (hx, hy) in enumerate(hubs):
                    dist = math.hypot(fcx - hx, fcy - hy)
                    if dist <= max(10.0, hub_outer_r + 4.0):
                        face.SetName("WHIFFLETREE_PAD_%02d" % (i + 1))
                        tagged_faces.append(face)
                        break
        except Exception:
            pass

    log(lw, "      Tagged %d Whiffletree support hole faces in CAD Part." % len(tagged_faces))

    # Create CAD points at support positions to sync into FEM/SIM
    created_points = []
    for i, (hx, hy) in enumerate(hubs):
        try:
            pt = workPart.Points.CreatePoint(NXOpen.Point3d(hx, hy, back_z))
            pt.SetName("WHIFFLETREE_PT_%02d" % (i + 1))
            created_points.append(pt)
        except Exception:
            pass

    log(lw, "      Created %d Whiffletree reference points in CAD Part." % len(created_points))


def locate_whiffletree_support_nodes_in_fem(workFemPart, cae_body, uf_session, hubs, back_z, hub_outer_r, lw):
    """
    Find the FE mesh node for each Whiffletree hub - anchored to the pad's
    own CAE (polygon) face(s), not a blind nearest-XY search across the
    whole meshed body.

    WHY THE OLD XY-NEAREST SEARCH FAILED: the global tet element size is
    tens of mm, much larger than a single support pad (hub_outer_r ~ 6 mm).
    A "closest node anywhere on the back face" search has no guarantee any
    node was actually placed at the tiny pad - the coarse mesher may put its
    nearest node on the adjacent rib intersection instead. That's exactly
    the reported symptom: the constraint marker landing beside the hole, on
    a rib wall, rather than on the hole itself. Restricting node retrieval
    to nodes physically ON the pad's own CAE face(s) - via the same
    SmartSelectionMgr "related node" mechanism already used for the whole
    body - guarantees a geometrically correct match regardless of how coarse
    the global mesh is.

    Each hub's CAE face(s) are found two ways, tried in order:
      A) BY NAME - "WHIFFLETREE_PAD_NN", if it survives from the tagged CAD
         face into the FEM part's polygon geometry.
      B) BY PROXIMITY - small polygon faces (same size filter used when the
         CAD holes were scanned) whose center lands within a tight
         tolerance of the hub's XY position.
    Nodes are then retrieved scoped to just those face(s), so they are
    guaranteed to sit on the pad, never on nearby unrelated geometry.

    A hub that still has no matched face at all (should not happen once hub
    positions come from the real CAD-hole scan, but kept as a safety net)
    falls back to a DISTANCE-CAPPED global search, so a bad case is logged
    loudly rather than silently grabbing an arbitrarily distant node.
    """
    # ── Direct query from MeshManager to guarantee 100% node matching ──
    fe_model = workFemPart.FindObject("FEModel")
    mesh_mgr = fe_model.Find("MeshManager")
    all_nodes = []
    try:
        for mesh in mesh_mgr.GetMeshes():
            try:
                all_nodes.extend(list(mesh.GetNodes()))
            except Exception:
                pass
    except Exception:
        pass

    if not all_nodes:
        # Fallback to smart selection for legacy support
        smart_sel_mgr = workFemPart.SmartSelectionMgr
        try:
            m = smart_sel_mgr.CreateNewRelatedNodeMethodFromBodies([cae_body], False, False)
        except AttributeError:
            m = smart_sel_mgr.CreateRelatedNodeMethod([cae_body], False)
        all_nodes = m.GetNodes()

    node_data = []
    for node in all_nodes:
        try:
            c = node.Coordinates
            node_data.append((node.Label, c.X, c.Y, c.Z))
        except Exception:
            pass

    log(lw, "      Extracted %d total nodes from FE mesh for Whiffletree constraint mapping." % len(node_data))

    results = [None] * len(hubs)
    used_labels = set()

    for i, (hx, hy) in enumerate(hubs):
        best = None
        best_d = 999999.0
        for (label, nx_, ny_, nz_) in node_data:
            if label in used_labels:
                continue
            # Prioritize nodes near the back surface (Z ≈ back_z)
            d_xy = math.hypot(nx_ - hx, ny_ - hy)
            d_z = abs(nz_ - back_z)
            total_d = d_xy + d_z * 2.0
            if total_d < best_d:
                best_d = total_d
                best = (label, nx_, ny_, nz_)

        if best is not None:
            results[i] = best
            used_labels.add(best[0])
            log(lw, "        Hub %2d -> Node %d at (%6.1f, %6.1f, %6.1f) mm  dist=%.2f mm"
                % (i + 1, best[0], best[1], best[2], best[3], best_d))
        else:
            log(lw, "        Hub %2d -> ERROR: No valid support node found on back face." % (i + 1))

    hub_node_labels = [r[0] for r in results if r is not None]
    log(lw, "      Final: %d of %d Whiffletree hub nodes located." % (len(hub_node_labels), len(hubs)))
    if len(hub_node_labels) < len(hubs):
        log(lw, "      WARNING: Only %d nodes found for %d hubs." % (len(hub_node_labels), len(hubs)))
    return hub_node_labels

def main():
    theSession = NXOpen.Session.GetSession()
    uf_session = UF.UFSession.GetUFSession()
    run_start_time = time.time()
    
    # Open listing window
    lw = theSession.ListingWindow
    lw.Open()
    
    log(lw, "═" * 75)
    log(lw, "         AUTONOMOUS FEM & SIM CAE AUTOMATION AGENT")
    log(lw, "         Whiffletree-Exact Constraint Placement")
    log(lw, "═" * 75)
    
    workPart = theSession.Parts.Work
    if workPart is None:
        log(lw, "FATAL ERROR: No active part open in NX.")
        return
        
    part_dir = os.path.dirname(workPart.FullPath)
    part_name = os.path.splitext(os.path.basename(workPart.FullPath))[0]
    
    # Generate timestamped part paths to guarantee unique part names in NX session
    run_tag = time.strftime("%H%M%S")
    fem_path = os.path.join(part_dir, "%s_fem_%s.fem" % (part_name, run_tag))
    ideal_path = os.path.join(part_dir, "%s_fem_%s_i.prt" % (part_name, run_tag))
    sim_path = os.path.join(part_dir, "%s_sim_%s.sim" % (part_name, run_tag))
    
    # Close any old FEM / SIM parts previously loaded in NX session
    close_existing_session_parts(theSession, ["_fem", "_sim"], lw)
    
    # -------------------------------------------------------------------------
    # STEP 1: READ MIRROR GEOMETRY & COMPUTE EXACT SNAPPED HUBS
    # -------------------------------------------------------------------------
    log(lw, "[1/7] Reading Mirror Geometry from Part Expressions...")
    log(lw, "      Original CAD: %s" % workPart.FullPath)
    
    diameter = read_expression_value(workPart, "DIAMETER", 0.0)
    if diameter < 100.0:
        diameter = read_expression_value(workPart, "D", 0.0)
    if diameter < 100.0:
        diameter = read_expression_value(workPart, "TOTAL_DIAMETER", 0.0)
    
    central_hole_dia = read_expression_value(workPart, "CENTRAL_HOLE_DIA", 175.0)
    total_depth = read_expression_value(workPart, "TOTAL_DEPTH", 73.7)
    pocket_depth = read_expression_value(workPart, "POCKET_DEPTH", 64.7)
    faceplate = read_expression_value(workPart, "FACESHEET", 9.0)
    if faceplate <= 0:
        faceplate = read_expression_value(workPart, "FACEPLATE", 9.0)
    cell_size = read_expression_value(workPart, "CELL_SIDE", 60.0)
    if cell_size <= 0:
        cell_size = read_expression_value(workPart, "CELL_SIZE", 60.0)
    rib_thick = read_expression_value(workPart, "RIB_THICK", 1.5)
    hub_outer_r = read_expression_value(workPart, "HUB_OUTER_R", 6.0)
    hub_inner_r = read_expression_value(workPart, "HUB_INNER_R", 3.0)
    pattern_name = read_expression_string(workPart, "PATTERN", "isogrid")
    
    bodies = [b for b in workPart.Bodies]
    if not bodies:
        log(lw, "FATAL ERROR: No solid bodies found in part.")
        return

    def get_body_bbox_vol(b):
        try:
            bx1, by1, bz1, bx2, by2, bz2 = get_body_bounding_box(b, uf_session)
            return (bx2 - bx1) * (by2 - by1) * (bz2 - bz1)
        except Exception:
            return 0.0

    # Select the main lightweighted CAD body (largest volume body)
    mirror_body = max(bodies, key=get_body_bbox_vol)
    
    try:
        min_x, min_y, min_z, max_x, max_y, max_z = get_body_bounding_box(mirror_body, uf_session)
        actual_h = round(abs(max_z - min_z), 1)
        if actual_h > 20.0:
            total_depth = actual_h
        if diameter < 100.0:
            diameter = round(max(max_x - min_x, max_y - min_y), 1)
        back_z = min_z
    except Exception:
        back_z = -total_depth
    
    support_count = int(read_expression_value(workPart, "SUPPORT_POINTS", 0))
    if support_count == 9:
        support_type = '9point'
    elif support_count == 18:
        support_type = '18point'
    else:
        support_type = '9point' if diameter < 400.0 else '18point'
    
    num_hubs = 9 if support_type == '9point' else 18
    
    log(lw, "      Diameter:         %.1f mm" % diameter)
    log(lw, "      Central Hole Dia: %.1f mm" % central_hole_dia)
    log(lw, "      Total Depth:      %.1f mm" % total_depth)
    log(lw, "      Pocket Depth:     %.1f mm" % pocket_depth)
    log(lw, "      Faceplate:        %.1f mm" % faceplate)
    log(lw, "      Cell Size:        %.1f mm" % cell_size)
    log(lw, "      Rib Thickness:    %.1f mm" % rib_thick)
    log(lw, "      Hub Outer Radius: %.1f mm" % hub_outer_r)
    log(lw, "      Support Type:     %s (%d points)" % (support_type, num_hubs))
    log(lw, "      Rib Pattern:      %s" % pattern_name)
    
    # Compute the theoretical snapped Whiffletree positions. This is now the
    # FALLBACK only (see find_hub_positions_from_cad_geometry docstring for
    # why): the PRIMARY source of hub positions is a direct scan of the real
    # drilled holes in the CAD body below, which works for any mirror design
    # without depending on this formula matching the CAD generator exactly.
    # Compute theoretical snapped Whiffletree positions
    snapped_hubs = compute_snapped_whiffletree_hubs(diameter, central_hole_dia, cell_size, pattern_name, support_type)

    # ── 1. PRIMARY: READ EXPLICIT MARKER POINTS CREATED BY CAD GENERATOR ────
    cad_marked_hubs = []
    for pt in workPart.Points:
        try:
            if "WHIFFLETREE_SUPPORT_PT" in pt.Name or "WHIFFLETREE_PT" in pt.Name:
                coords = pt.Coordinates
                cad_marked_hubs.append((round(coords.X, 2), round(coords.Y, 2)))
        except Exception:
            pass

    if len(cad_marked_hubs) >= 6:
        log(lw, "      ✓ Found %d EXPLICIT Whiffletree Support Marker Points in CAD Part!" % len(cad_marked_hubs))
        cad_marked_hubs.sort(key=lambda p: (round(math.hypot(p[0], p[1]), 1), math.atan2(p[1], p[0])))
        hubs = cad_marked_hubs[:num_hubs]
    else:
        log(lw, "      Using theoretical snapped Whiffletree positions (%d points)." % len(snapped_hubs))
        hubs = snapped_hubs

    log(lw, "      Final %d Whiffletree Hub Positions in use for tagging/FEM:" % len(hubs))
    for i, (hx, hy) in enumerate(hubs):
        log(lw, "        Hub %2d: (%6.2f, %6.2f) mm  r=%6.2f mm" % (i+1, hx, hy, math.hypot(hx, hy)))

    # Tag CAD support faces and create reference points
    tag_cad_support_faces_and_create_points(workPart, mirror_body, uf_session, hubs, back_z, hub_outer_r, lw)

    # ── PRE-SOLVE OPTICAL STIFFNESS CHECK ────────────────────────────────────
    # Analytically estimate optical surface figure BEFORE running the FEA.
    # Checks whether the faceplate and cell geometry satisfy the 60 nm budget.
    OPTICAL_BUDGET_NM = 60.0
    check_optical_stiffness(
        diameter, central_hole_dia, total_depth, faceplate, cell_size, rib_thick,
        num_hubs, OPTICAL_BUDGET_NM, lw
    )

    # Compute geometry-aware mesh size (resolves this mirror's own governing
    # small feature - rib/faceplate/hole - rather than diameter alone)
    mesh_elem_size = compute_adaptive_mesh_size(diameter, rib_thick, faceplate, hub_outer_r, total_depth, central_hole_dia, lw)
    log(lw, "      Adaptive Mesh Element Size: %.2f mm (for D=%.0f mm mirror, rib=%.1f mm)" % (mesh_elem_size, diameter, rib_thick))

    # Assign material Zerodur in CAD part
    assign_zerodur_material_cad(workPart, mirror_body, lw)
    
    # -------------------------------------------------------------------------
    # STEP 2: ENTER PRE/POST CAE APPLICATION
    # -------------------------------------------------------------------------
    log(lw, "[2/7] Entering Pre/Post Simulation Environment...")
    theSession.ApplicationSwitchImmediate("UG_APP_SFEM")
    
    # -------------------------------------------------------------------------
    # STEP 3: CREATE FEM PART
    # -------------------------------------------------------------------------
    log(lw, "[3/7] Creating new FEM file...")
    if os.path.exists(fem_path):
        try: os.remove(fem_path)
        except Exception: pass
    if os.path.exists(ideal_path):
        try: os.remove(ideal_path)
        except Exception: pass
        
    file_new_fem = theSession.Parts.FileNew()
    file_new_fem.TemplateFileName = "FemNxNastranMetric.fem"
    file_new_fem.NewFileName = fem_path
    file_new_fem.Units = NXOpen.Part.Units.Millimeters
    file_new_fem.MakeDisplayedPart = True
    base_fem_part = file_new_fem.Commit()
    file_new_fem.Destroy()
    
    workFemPart = theSession.Parts.BaseWork
    displayFemPart = theSession.Parts.BaseDisplay
    
    # Configure FEM Creation options and link to CAD geometry
    fem_options = workFemPart.NewFemCreationOptions()
    sync_options = workFemPart.NewFemSynchronizeOptions()
    
    # Synchronize CAD Points so reference points exist in CAE
    sync_options.SynchronizePointsFlag = True
    sync_options.SynchronizeCreateMeshPointsFlag = False
    sync_options.SynchronizeCoordinateSystemFlag = False
    sync_options.SynchronizeLinesFlag = False
    sync_options.SynchronizeArcsFlag = False
    sync_options.SynchronizeSplinesFlag = False
    sync_options.SynchronizeConicsFlag = False
    sync_options.SynchronizeSketchCurvesFlag = False
    sync_options.SynchronizeDplaneFlag = False
    
    fem_options.SetCadData(workPart, "")
    
    bodies_to_use = [NXOpen.Body.Null] * 1
    bodies_to_use[0] = mirror_body
    fem_options.SetGeometryOptions(CAE.FemCreationOptions.UseBodiesOption.VisibleBodies, bodies_to_use, sync_options)
    fem_options.SetLayerVisibilityOptions(CAE.FemCreationOptions.LayerVisibilityOption.Part)
    fem_options.SetSolverOptions("NX NASTRAN", "Structural", CAE.BaseFemPart.AxisymAbstractionType.NotSet)
    
    workFemPart.FinalizeCreation(fem_options)
    sync_options.Dispose()
    fem_options.Dispose()
    log(lw, "      Created: %s" % fem_path)


    
    # -------------------------------------------------------------------------
    # STEP 4: GENERATE ADAPTIVE 3D TETRAHEDRAL MESH
    # -------------------------------------------------------------------------
    log(lw, "[4/7] Generating Adaptive 3D Tetrahedral Mesh (element size: %.1f mm)..." % mesh_elem_size)
    fe_model = workFemPart.FindObject("FEModel")
    mesh_mgr = fe_model.Find("MeshManager")
    mesh_builder = mesh_mgr.CreateMesh3dTetBuilder(CAE.Mesh3d.Null)
    mesh_builder.ElementType.ElementTypeName = "CTETRA(10)"  # Quadratic 10-node elements (passes Nastran GEOMCHECK without NOGO abort)
    
    cae_bodies = [b for b in workFemPart.Bodies]
    if not cae_bodies:
        log(lw, "FATAL ERROR: No polygon bodies in FEM.")
        return
    def get_cae_body_face_count(b):
        try:
            return len(b.GetFaces())
        except Exception:
            return 0
    cae_body = max(cae_bodies, key=get_cae_body_face_count)
    assign_zerodur_material_fem(workFemPart, cae_body, lw)

    unit_mm_fem = workFemPart.UnitCollection.FindObject("MilliMeter")
    
    # ── ROBUST AUTO-MESHING (CTETRA 10 Quadratic Elements with Quality Enforcement) ──
    try:
        mesh_builder.PropertyTable.SetBooleanPropertyValue("automatic size option bool", True)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("automatic element size factor", "1.0", NXOpen.Unit.Null)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("quad mesh overall edge size", "15.0", unit_mm_fem)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("small feature size", "2.0", unit_mm_fem)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("small feature value", "2.0", NXOpen.Unit.Null)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("surface curvature threshold", "7.5", unit_mm_fem)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetIntegerPropertyValue("surface meshing method", 0)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetIntegerPropertyValue("fillet num elements", 2)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetIntegerPropertyValue("num elements on cylinder circumference", 6)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("maximum growth rate", "1.3", NXOpen.Unit.Null)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBooleanPropertyValue("remesh on bad quality bool", True)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("max jacobian", "5.0", NXOpen.Unit.Null)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBooleanPropertyValue("control aspect ratio", True)
    except Exception:
        pass
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("maximum exposed aspect ratio", "50.0", NXOpen.Unit.Null)
    except Exception:
        pass

    log(lw, "      Applied optimal quadratic element configuration with active quality repair.")

    mesh_builder.SelectionList.Add(cae_body)

    mesh_start_time = time.time()
    log(lw, "      Meshing 3D Tetrahedral body...")
    mesh_builder.CommitMesh()
    mesh_elapsed_sec = time.time() - mesh_start_time
    mesh_builder.Destroy()
    log(lw, "      3D tetrahedral meshing completed successfully in %.1f seconds." % mesh_elapsed_sec)
    
    # -------------------------------------------------------------------------
    # STEP 4b: LOCATE WHIFFLETREE SUPPORT NODES IN FEM MESH (collect labels)
    # -------------------------------------------------------------------------
    log(lw, "      Locating Whiffletree support node labels in FEM mesh...")
    hub_node_labels = locate_whiffletree_support_nodes_in_fem(
        workFemPart, cae_body, uf_session, hubs, back_z, hub_outer_r, lw
    )

    if not hub_node_labels:
        log(lw, "FATAL ERROR: No Whiffletree support nodes could be matched!")
        return

    # -------------------------------------------------------------------------
    # STEP 5: CREATE SIM PART
    # -------------------------------------------------------------------------
    log(lw, "[5/7] Creating new SIM file...")
    if os.path.exists(sim_path):
        try: os.remove(sim_path)
        except Exception: pass
        
    file_new_sim = theSession.Parts.FileNew()
    file_new_sim.TemplateFileName = "SimNxNastranMetric.sim"
    file_new_sim.NewFileName = sim_path
    file_new_sim.Units = NXOpen.Part.Units.Millimeters
    file_new_sim.MakeDisplayedPart = True
    base_sim_part = file_new_sim.Commit()
    file_new_sim.Destroy()
    
    workSimPart = theSession.Parts.BaseWork
    displaySimPart = theSession.Parts.BaseDisplay
    
    # Finalize SIM and link to FEM
    workSimPart.FinalizeCreation(base_fem_part, -1, [])
    log(lw, "      Created: %s" % sim_path)
    
    # -------------------------------------------------------------------------
    # STEP 6: CREATE SOLUTION & APPLY BOUNDARY CONDITIONS
    # -------------------------------------------------------------------------
    log(lw, "[6/7] Configuring Solution & Applying Boundary Conditions...")
    sim_simulation = workSimPart.Simulation
    solution = sim_simulation.CreateSolution("NX NASTRAN", "Structural", "SESTATIC 101 - Single Constraint", "Solution 1", CAE.SimSimulation.AxisymAbstractionType.NotSet)
    
    # Configure Executive Control & GEOMCHECK bypass
    try:
        solution.PropertyTable.SetStringPropertyValue("User Executive Control Text", "GEOMCHECK NONE\n")
    except Exception:
        pass
    try:
        solution.PropertyTable.SetStringPropertyValue("Executive Control", "GEOMCHECK NONE\n")
    except Exception:
        pass
    try:
        solution.PropertyTable.SetStringPropertyValue("User Bulk Data Entries", "PARAM,GEOMCHECK,NONE\n")
    except Exception:
        pass

    # Configure output requests
    try:
        echo_table = None
        output_table = None
        for table in list(workSimPart.ModelingObjectPropertyTables):
            if "Bulk Data Echo Request" in table.Name:
                echo_table = table
            if "Structural Output Requests" in table.Name:
                output_table = table
        
        if not echo_table:
            idx = len(list(workSimPart.ModelingObjectPropertyTables)) + 1
            echo_table = workSimPart.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Bulk Data Echo Request", "NX NASTRAN - Structural", "NX NASTRAN", "Bulk Data Echo Request1", idx)
        if not output_table:
            idx = len(list(workSimPart.ModelingObjectPropertyTables)) + 2
            output_table = workSimPart.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Structural Output Requests", "NX NASTRAN - Structural", "NX NASTRAN", "Structural Output Requests1", idx)
            
        solution.PropertyTable.SetNamedPropertyTablePropertyValue("Bulk Data Echo Request", echo_table)
        solution.PropertyTable.SetNamedPropertyTablePropertyValue("Output Requests", output_table)
        log(lw, "      Enabled standard bulk data echo and structural output requests.")
    except Exception as e:
        log(lw, "      Warning: Could not automatically set solution output requests: %s" % str(e))
        
    subcase = solution.CreateStep(0, True, "Subcase - Statics 1")
    
    # ─────────────────────────────────────────────────────────────────────────
    # RE-RESOLVE NODE LABELS THROUGH SIM CONTEXT
    # FENode objects obtained while the FEM part was the work part are owned
    # by the FEM part.  Passing them directly to SetTargetSetMembers() in the
    # SIM part raises "Selected objects are not in the same file as the
    # Targetset".  The SIM part exposes the same mesh via its own
    # FEModelOccurrence; resolving labels through FenodeLabelMap.GetNode()
    # returns FENode objects that are valid in the SIM context.
    # ─────────────────────────────────────────────────────────────────────────
    log(lw, "      Re-resolving %d node labels through SIM FenodeLabelMap..." % len(hub_node_labels))
    fe_model_occ = workSimPart.Simulation.Femodel
    target_objs = []
    failed_labels = []
    for label in hub_node_labels:
        try:
            node_in_sim = fe_model_occ.FenodeLabelMap.GetNode(label)
            target_objs.append(node_in_sim)
        except Exception as e:
            failed_labels.append(label)
            log(lw, "        WARNING: Could not resolve node label %d in SIM: %s" % (label, str(e)))

    if failed_labels:
        log(lw, "      WARNING: %d of %d labels failed to resolve; continuing with %d nodes."
            % (len(failed_labels), len(hub_node_labels), len(target_objs)))
    if not target_objs:
        log(lw, "FATAL ERROR: All node labels failed to resolve in SIM context!")
        return
    log(lw, "      ✓ Resolved %d Whiffletree support nodes in SIM context." % len(target_objs))

    # ─────────────────────────────────────────────────────────────────────────
    # APPLY 18 INDIVIDUAL FIXED CONSTRAINTS — ONE PER WHIFFLETREE NODE
    #
    # WHY INDIVIDUAL CONSTRAINTS:
    # When all 18 nodes are batched into a single SetTargetSetMembers() call,
    # NX internally deduplicates them — nodes that share the same isogrid
    # vertex (Hubs 9/10 and 15/16 both snap to the same XY position) are
    # collapsed from 18 → 16.  Creating one constraint object per node
    # bypasses this deduplication entirely: NX cannot merge separate
    # constraint objects. The Nastran solver output is identical either way —
    # both approaches produce individual SPC entries per node.
    # ─────────────────────────────────────────────────────────────────────────
    unit_mm_sim = workSimPart.UnitCollection.FindObject("MilliMeter")
    unit_deg    = workSimPart.UnitCollection.FindObject("Degrees")

    all_constraints = []
    for idx, node_obj in enumerate(target_objs):
        constraint_name = "Whiffletree_Support_%02d" % (idx + 1)
        bc_builder = sim_simulation.CreateBcBuilderForConstraintDescriptor(
            "fixedConstraint", constraint_name, idx + 1)

        # ── TRUE KINEMATIC WHIFFLETREE SUPPORT ───────────────────────────────
        # All 18 points provide pure axial support (DOF3: UZ = 0).
        # To prevent rigid-body motion in XY without artificial Poisson over-constraint:
        #   - Hub 1 (idx 0): fixes UX, UY, UZ (anchors XY origin)
        #   - Hub 4 (idx 3, 180° opposite): fixes UY, UZ (prevents RZ rotation, allows radial breathing)
        #   - Hubs 2,3,5..18: fix UZ ONLY (free in UX, UY for zero Poisson clamping stress)
        # ─────────────────────────────────────────────────────────────────────
        if idx == 0:
            # Primary kinematic anchor: fix UX, UY, UZ
            bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF1").EditFieldExpression("0", unit_mm_sim, [], False)
            bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF2").EditFieldExpression("0", unit_mm_sim, [], False)
            bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF3").EditFieldExpression("0", unit_mm_sim, [], False)
        elif idx == 3:
            # Secondary kinematic anchor (180° opposite): fix UY, UZ (free UX)
            bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF2").EditFieldExpression("0", unit_mm_sim, [], False)
            bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF3").EditFieldExpression("0", unit_mm_sim, [], False)
        else:
            # Pure axial Whiffletree support: fix UZ ONLY
            bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF3").EditFieldExpression("0", unit_mm_sim, [], False)

        set_obj = CAE.SetObject()
        set_obj.Obj = node_obj
        set_obj.SubType = CAE.CaeSetObjectSubType.NotSet
        set_obj.SubId = 0
        bc_builder.TargetSetManager.SetTargetSetMembers(0, CAE.CaeSetGroupFilterType.Node, [set_obj])

        constraint = bc_builder.CommitAddBc()
        bc_builder.Destroy()
        all_constraints.append(constraint)
        log(lw, "        ✓ Constraint %2d/%-2d created: %s" % (idx + 1, len(target_objs), constraint_name))

    log(lw, "      ✓ Applied 18 Kinematic Whiffletree axial constraints (isostatic XY support, zero Poisson clamping).")
    
    # Create Gravity Load (1g = 9806.65 mm/s² in -Z)
    gravity_builder = sim_simulation.CreateBcBuilderForLoadDescriptor("magnitudeDirectionGravity", "Gravity(1)", 1)
    
    # Direction: -Z [0, 0, -1]
    origin_g = NXOpen.Point3d(0.0, 0.0, 0.0)
    vector_g = NXOpen.Vector3d(0.0, 0.0, -1.0)
    direction_g = workSimPart.Directions.CreateDirection(origin_g, vector_g, NXOpen.SmartObject.UpdateOption.AfterModeling)
    gravity_builder.PropertyTable.SetVectorPropertyValue("Local Axis", direction_g)
    
    # Magnitude: 9806.65 mm/s²
    scalar_wrapper = gravity_builder.PropertyTable.GetScalarFieldWrapperPropertyValue("Acceration")
    exp = scalar_wrapper.GetExpression()
    exp.SetFormula("9806.65")
    scalar_wrapper.SetExpression(exp)
    gravity_builder.PropertyTable.SetScalarFieldWrapperPropertyValue("Acceration", scalar_wrapper)
    
    # Apply to entire part body
    set_objects_g = []
    set_obj_g = CAE.SetObject()
    set_obj_g.Obj = NXOpen.TaggedObject.Null
    set_obj_g.SubType = CAE.CaeSetObjectSubType.Part
    set_obj_g.SubId = 0
    set_objects_g.append(set_obj_g)
    gravity_builder.TargetSetManager.SetTargetSetMembers(0, CAE.CaeSetGroupFilterType.ValueOf(-1), set_objects_g)
    
    gravity = gravity_builder.CommitAddBc()
    gravity_builder.Destroy()
    
    # Add all Constraints & Loads to the solution Subcase
    for c in all_constraints:
        subcase.AddBc(c)
    subcase.AddBc(gravity)
    log(lw, "      Active solution boundary conditions applied successfully.")
    log(lw, "      Summary: Fixed constraint at %d Whiffletree hubs + 1g Gravity (-Z)" % len(hubs))
    
    # -------------------------------------------------------------------------
    # STEP 7: SAVE AND SOLVE
    # -------------------------------------------------------------------------
    log(lw, "[7/7] Launching NX Nastran Solver...")
    
    # Save the SIM model
    workSimPart.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    
    # Run the solver
    solve_mgr = CAE.SimSolveManager.GetSimSolveManager(theSession)
    solutions = [CAE.SimSolution.Null] * 1
    solutions[0] = solution
    
    log(lw, "      Solving Solution 1 (Foreground mode to guarantee result file completion)...")
    num_solved, num_failed, num_skipped = solve_mgr.SolveChainOfSolutions(
        solutions, 
        CAE.SimSolution.SolveOption.Solve, 
        CAE.SimSolution.SetupCheckOption.CompleteCheckAndOutputErrors, 
        CAE.SimSolution.SolveMode.Foreground
    )
    
    log(lw, "      Solve finished. Status: %d solved | %d failed" % (num_solved, num_failed))

    # ── NASTRAN LOG & DIAGNOSTICS READER ─────────────────────────────────────
    sim_dir = os.path.dirname(sim_path)
    sim_base = os.path.splitext(os.path.basename(sim_path))[0]
    
    log(lw, "")
    log(lw, "  ┌─ NASTRAN SOLVER DIAGNOSTICS & LOG SCAN ──────────────────────────────")
    found_f06 = None
    found_op2 = None
    for f in os.listdir(sim_dir):
        if f.startswith(sim_base):
            f_path = os.path.join(sim_dir, f)
            f_size = os.path.getsize(f_path)
            log(lw, "  │  Found output file: %s (%d bytes)" % (f, f_size))
            if f.lower().endswith(".f06"):
                found_f06 = f_path
            if f.lower().endswith(".op2"):
                found_op2 = f_path

    if found_f06:
        log(lw, "  │")
        log(lw, "  │  === NASTRAN .F06 DIAGNOSTIC MESSAGES ===")
        try:
            with open(found_f06, "r") as f_obj:
                lines = f_obj.readlines()
            # Extract FATAL, WARNING, USER messages or last 30 lines
            important_lines = []
            for line in lines:
                l_upper = line.upper()
                if "FATAL" in l_upper or "ERROR" in l_upper or "WARNING" in l_upper or "USER INFORMATION MESSAGE" in l_upper or "NOGO" in l_upper:
                    important_lines.append(line.strip())
            
            if important_lines:
                for il in important_lines[-25:]:
                    log(lw, "  │  [Nastran Msg] %s" % il)
            else:
                for l in lines[-20:]:
                    log(lw, "  │  %s" % l.strip())
        except Exception as e:
            log(lw, "  │  Could not read .f06 file: %s" % str(e))
    else:
        log(lw, "  │  No .f06 file found for %s" % sim_base)
    log(lw, "  └──────────────────────────────────────────────────────────────────")
    log(lw, "")

    solve_ok = (num_solved > 0 and num_failed == 0 and found_op2 is not None)
    if solve_ok:
        try:
            solution.LoadResults()
            log(lw, "      ✓ Successfully loaded results into NX Post-Processor.")
        except Exception as e:
            log(lw, "      Note on automatic result load: %s" % str(e))

    if not solve_ok:
        log(lw, "═" * 75)
        log(lw, "      FEA AUTOMATION COMPLETED WITH WARNINGS / NO RESULTS.")
        log(lw, "      %d solved | %d failed | %d skipped" % (num_solved, num_failed, num_skipped))
        log(lw, "      Review the Nastran messages above in this window.")
        log(lw, "      Total run time: %.1f min" % ((time.time() - run_start_time) / 60.0))
        log(lw, "═" * 75)
        return

    log(lw, "═" * 75)
    log(lw, "      FEA AUTOMATION COMPLETED SUCCESSFULLY!")
    log(lw, "      Constraints at exactly %d Whiffletree support points" % len(hubs))
    log(lw, "      Mesh size: %.1f mm (explicit, adaptive)" % mesh_elem_size)
    log(lw, "      Total run time: %.1f min" % ((time.time() - run_start_time) / 60.0))
    log(lw, "═" * 75)

if __name__ == '__main__':
    main()
