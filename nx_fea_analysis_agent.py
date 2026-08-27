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
    max_r = R - 30.0
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

def compute_adaptive_mesh_size(diameter):
    """
    Compute optimal FEA mesh element size based on mirror diameter.
    Targets approximately 4.5% of diameter, clamped between 8mm and 80mm.
    """
    raw_size = diameter * 0.045
    elem_size = max(8.0, min(80.0, raw_size))
    return round(elem_size, 1)

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
            
            # Support hole facet or pad face
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
    Find the closest FE mesh node to each Whiffletree hub.

    Returns a list of integer node labels (stable identifiers valid across
    part contexts). After the SIM part is created, resolve each label through
    workSimPart.Simulation.Femodel.FenodeLabelMap.GetNode(label) to get the
    FENode object that lives in the SIM part's own context — that is the object
    accepted by SetTargetSetMembers(..., CaeSetGroupFilterType.Node, ...).
    """
    smart_sel_mgr = workFemPart.SmartSelectionMgr
    try:
        related_node_method = smart_sel_mgr.CreateNewRelatedNodeMethodFromBodies([cae_body], False, False)
    except AttributeError:
        related_node_method = smart_sel_mgr.CreateRelatedNodeMethod([cae_body], False)

    all_nodes = related_node_method.GetNodes()
    log(lw, "      Retrieved %d FE mesh nodes from body via SmartSelectionMgr..." % len(all_nodes))

    # Build coordinate + label lookup in one pass
    node_data = []   # list of (label, x, y, z)
    for node in all_nodes:
        try:
            c = node.Coordinates
            node_data.append((node.Label, c.X, c.Y, c.Z))
        except Exception:
            pass

    log(lw, "      Resolved coordinates for %d of %d nodes..." % (len(node_data), len(all_nodes)))

    hub_node_labels = []
    used_labels = set()   # Prevents two hubs from sharing a node. When two hub
                          # positions snap to the same grid vertex (e.g. both at
                          # (0, 241.62)), the second hub is forced to pick the
                          # next-nearest distinct node.

    for i, (hx, hy) in enumerate(hubs):
        best_label = None
        min_dist = 999999.0
        best_coords = (0.0, 0.0, 0.0)
        for (label, nx_, ny_, nz_) in node_data:
            if label in used_labels:
                continue   # already claimed by an earlier hub
            d_xy = math.hypot(nx_ - hx, ny_ - hy)
            d_z  = abs(nz_ - back_z)
            total_d = d_xy + d_z * 1.5
            if total_d < min_dist:
                min_dist = total_d
                best_label = label
                best_coords = (nx_, ny_, nz_)

        # No distance threshold — always accept the nearest available node.
        # This guarantees exactly len(hubs) constraints are created even when
        # the CAD only has 16 physical holes (the 2 extra hubs land on nearby
        # rib nodes at the correct theoretical support positions).
        if best_label is not None:
            hub_node_labels.append(best_label)
            used_labels.add(best_label)
            log(lw, "        Hub %2d at (%6.1f, %6.1f) mm: Node label %d at (%6.1f, %6.1f, %6.1f) mm (dist=%.2f mm)"
                % (i + 1, hx, hy, best_label,
                   best_coords[0], best_coords[1], best_coords[2], min_dist))
        else:
            log(lw, "        Hub %2d at (%6.1f, %6.1f) mm: ERROR – mesh has no remaining unclaimed nodes!"
                % (i + 1, hx, hy))

    log(lw, "      Located %d of %d Whiffletree hub node labels." % (len(hub_node_labels), len(hubs)))
    if len(hub_node_labels) < len(hubs):
        log(lw, "      WARNING: Only %d nodes found for %d hubs — mesh may be too coarse." % (len(hub_node_labels), len(hubs)))
    return hub_node_labels

def main():
    theSession = NXOpen.Session.GetSession()
    uf_session = UF.UFSession.GetUFSession()
    
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
    
    central_hole_dia = read_expression_value(workPart, "CENTRAL_HOLE_DIA", 200.0)
    total_depth = read_expression_value(workPart, "TOTAL_DEPTH", 90.0)
    pocket_depth = read_expression_value(workPart, "POCKET_DEPTH", 75.0)
    faceplate = read_expression_value(workPart, "FACESHEET", 15.0)
    if faceplate <= 0:
        faceplate = read_expression_value(workPart, "FACEPLATE", 15.0)
    cell_size = read_expression_value(workPart, "CELL_SIDE", 93.0)
    if cell_size <= 0:
        cell_size = read_expression_value(workPart, "CELL_SIZE", 93.0)
    rib_thick = read_expression_value(workPart, "RIB_THICK", 6.0)
    hub_outer_r = read_expression_value(workPart, "HUB_OUTER_R", 6.0)
    hub_inner_r = read_expression_value(workPart, "HUB_INNER_R", 3.0)
    pattern_name = read_expression_string(workPart, "PATTERN", "isogrid")
    
    bodies = [b for b in workPart.Bodies]
    if not bodies:
        log(lw, "FATAL ERROR: No solid bodies found in part.")
        return
    mirror_body = bodies[0]
    
    if diameter < 100.0:
        try:
            min_x, min_y, min_z, max_x, max_y, max_z = get_body_bounding_box(mirror_body, uf_session)
            diameter = round(max(max_x - min_x, max_y - min_y), 1)
        except Exception:
            diameter = 560.0
            
    try:
        min_x, min_y, min_z, max_x, max_y, max_z = get_body_bounding_box(mirror_body, uf_session)
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
    
    # Compute the EXACT snapped Whiffletree positions matching CAD holes
    snapped_hubs = compute_snapped_whiffletree_hubs(diameter, central_hole_dia, cell_size, pattern_name, support_type)
    log(lw, "      Computed %d Exact Whiffletree Hub Positions (snapped to isogrid):" % len(snapped_hubs))
    for i, (hx, hy) in enumerate(snapped_hubs):
        log(lw, "        Hub %2d: (%6.2f, %6.2f) mm  r=%6.2f mm" % (i+1, hx, hy, math.hypot(hx, hy)))
        
    # Tag CAD support faces and create reference points
    tag_cad_support_faces_and_create_points(workPart, mirror_body, uf_session, snapped_hubs, back_z, hub_outer_r, lw)
    
    # Compute adaptive mesh size
    mesh_elem_size = compute_adaptive_mesh_size(diameter)
    log(lw, "      Auto Mesh Element Size: %.1f mm (for D=%.0f mm mirror)" % (mesh_elem_size, diameter))
    
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
    
    # Initialize polygon resolution
    workFemPart.PolygonGeometryMgr.SetPolygonBodyResolutionOnFemBodies(CAE.PolygonGeometryManager.PolygonBodyResolutionType.Standard)
    
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
    
    fem_options.SetCadData(workPart, ideal_path)
    
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
    mesh_builder.ElementType.ElementTypeName = "CTETRA(10)"  # Quadratic elements
    
    cae_bodies = [b for b in workFemPart.Bodies]
    if not cae_bodies:
        log(lw, "FATAL ERROR: No polygon bodies in FEM.")
        return
    cae_body = cae_bodies[0]
    assign_zerodur_material_fem(workFemPart, cae_body, lw)

    unit_mm = workFemPart.UnitCollection.FindObject("MilliMeter")
    mesh_builder.PropertyTable.SetBooleanPropertyValue("automatic size option bool", True)
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("quad mesh overall edge size", str(mesh_elem_size), unit_mm)
    except Exception:
        pass

    mesh_builder.SelectionList.Add(cae_body)
    mesh_builder.CommitMesh()
    mesh_builder.Destroy()
    log(lw, "      3D tetrahedral meshing completed successfully.")
    
    # -------------------------------------------------------------------------
    # STEP 4b: LOCATE WHIFFLETREE SUPPORT NODES IN FEM MESH (collect labels)
    # -------------------------------------------------------------------------
    # We find nodes now (while we have the meshed FEM part as the work part)
    # but store only their integer LABELS. FENode objects are owned by the FEM
    # part and cannot be handed directly to the SIM part's constraint builder —
    # that raises "Selected objects are not in the same file as the Targetset".
    # Labels are stable identifiers; we re-resolve them through the SIM's
    # FenodeLabelMap after creating the SIM part (Step 5).
    log(lw, "      Locating Whiffletree support node labels in FEM mesh...")
    hub_node_labels = locate_whiffletree_support_nodes_in_fem(
        workFemPart, cae_body, uf_session, snapped_hubs, back_z, hub_outer_r, lw
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
    
    # Configure output requests
    try:
        echo_table = None
        output_table = None
        for table in list(workSimPart.ModelingObjectPropertyTables):
            if "Bulk Data Echo Request1" in table.Name:
                echo_table = table
            if "Structural Output Requests1" in table.Name:
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
        constraint_name = "Whiffletree_Fixed_%02d" % (idx + 1)
        bc_builder = sim_simulation.CreateBcBuilderForConstraintDescriptor(
            "fixedConstraint", constraint_name, idx + 1)

        # Lock all 6 DOFs
        bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF1").EditFieldExpression("0", unit_mm_sim, [], False)
        bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF2").EditFieldExpression("0", unit_mm_sim, [], False)
        bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF3").EditFieldExpression("0", unit_mm_sim, [], False)
        bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF4").EditFieldExpression("0", unit_deg, [], False)
        bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF5").EditFieldExpression("0", unit_deg, [], False)
        bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF6").EditFieldExpression("0", unit_deg, [], False)

        set_obj = CAE.SetObject()
        set_obj.Obj = node_obj
        set_obj.SubType = CAE.CaeSetObjectSubType.NotSet
        set_obj.SubId = 0
        bc_builder.TargetSetManager.SetTargetSetMembers(0, CAE.CaeSetGroupFilterType.Node, [set_obj])

        constraint = bc_builder.CommitAddBc()
        bc_builder.Destroy()
        all_constraints.append(constraint)
        log(lw, "        ✓ Constraint %2d/%-2d created: %s" % (idx + 1, len(target_objs), constraint_name))

    log(lw, "      ✓ Applied %d individual Fixed constraints (one per Whiffletree hub node)." % len(all_constraints))
    
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
    log(lw, "      Summary: Fixed constraint at %d Whiffletree hubs + 1g Gravity (-Z)" % len(snapped_hubs))
    
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
    
    log(lw, "      Solving Solution 1 in background...")
    num_solved, num_failed, num_skipped = solve_mgr.SolveChainOfSolutions(
        solutions, 
        CAE.SimSolution.SolveOption.Solve, 
        CAE.SimSolution.SetupCheckOption.CompleteCheckAndOutputErrors, 
        CAE.SimSolution.SolveMode.Background
    )
    
    log(lw, "      Solve finished. Status: %d solved | %d failed" % (num_solved, num_failed))
    log(lw, "═" * 75)
    log(lw, "      FEA AUTOMATION COMPLETED SUCCESSFULLY!")
    log(lw, "      Constraints at exactly %d Whiffletree support points" % len(snapped_hubs))
    log(lw, "      Mesh size: %.1f mm (auto for D=%.0f mm)" % (mesh_elem_size, diameter))
    log(lw, "═" * 75)

if __name__ == '__main__':
    main()
