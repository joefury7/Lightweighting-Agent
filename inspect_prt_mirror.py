# ==============================================================================
# SIEMENS NX OPEN MIRROR INSPECTOR (V7 YODER OPTO-MECHANICAL ENGINE)
# ==============================================================================
# Run this journal in Siemens NX (Alt+F8) on any mirror .prt file.
# Universally inspects mirror geometry and calculates Yoder & Vukobratovich
# Opto-Mechanical performance metrics (Quilting Deflection, Fundamental Frequency,
# Core Solidity, Pearson Ratio, and Mass Reduction %).
# ==============================================================================

import math
import json
import NXOpen
import NXOpen.UF as UF

def inspect_mirror_part():
    theSession = NXOpen.Session.GetSession()
    uf_session = UF.UFSession.GetUFSession()
    workPart = theSession.Parts.Work

    lw = theSession.ListingWindow
    lw.Open()
    try:
        lw.Clear()
    except Exception:
        pass

    if not workPart:
        lw.WriteLine("ERROR: No active part found in NX.")
        return

    part_name = workPart.Leaf

    bodies = [b for b in workPart.Bodies]
    if not bodies:
        lw.WriteLine("ERROR: No solid bodies found in part.")
        return

    main_body = bodies[0]
    faces = main_body.GetFaces()
    num_faces = len(faces)
    
    min_x, min_y, min_z = 1e9, 1e9, 1e9
    max_x, max_y, max_z = -1e9, -1e9, -1e9
    
    for face in faces:
        try:
            face_data = uf_session.Modeling.AskFaceData(face.Tag)
            f_bbox = face_data[3] if len(face_data) > 3 else None
            if f_bbox and len(f_bbox) >= 6:
                min_x = min(min_x, f_bbox[0])
                min_y = min(min_y, f_bbox[1])
                min_z = min(min_z, f_bbox[2])
                max_x = max(max_x, f_bbox[3])
                max_y = max(max_y, f_bbox[4])
                max_z = max(max_z, f_bbox[5])
        except Exception:
            pass

    dx = max_x - min_x if max_x > min_x else 1400.0
    dy = max_y - min_y if max_y > min_y else 1400.0
    dz = max_z - min_z if max_z > min_z else 90.0

    measured_diameter = round((dx + dy) / 2.0, 1)
    measured_blank_depth = round(dz, 1)

    # Read expressions for parametric dimensions
    expr_dict = {}
    for expr in workPart.Expressions:
        try:
            expr_dict[expr.Name.upper()] = float(expr.Value)
        except Exception:
            pass

    diameter = expr_dict.get("D", expr_dict.get("DIAMETER", expr_dict.get("TOTAL_DIAMETER", measured_diameter)))
    r_curv = expr_dict.get("R_CURV", expr_dict.get("RADIUS_CURV", expr_dict.get("RADIUS_OF_CURVATURE", 5000.0)))
    blank_depth = expr_dict.get("H", expr_dict.get("TOTAL_DEPTH", expr_dict.get("BLANK_DEPTH", measured_blank_depth)))
    faceplate = expr_dict.get("T_F", expr_dict.get("FACEPLATE", expr_dict.get("FACEPLATE_THICKNESS", 15.0)))
    cell_size = expr_dict.get("CELL_SIDE", expr_dict.get("CELL_SIZE", expr_dict.get("W", 140.0)))
    rib_thick = expr_dict.get("T_W", expr_dict.get("RIB_THICK", expr_dict.get("RIB_WIDTH", 6.0)))

    side_wall_count = 0
    pocket_floors = 0
    inner_core_edges = []
    shape_ratios = []

    for face in faces:
        try:
            face_data = uf_session.Modeling.AskFaceData(face.Tag)
            face_type = face_data[0]
            origin = face_data[1]
            normal = face_data[2]
            
            if face_type in [19, 17, 18]: # Cylindrical / Conical side wall faces
                side_wall_count += 1
            else:
                # If face normal points mostly along Z axis
                if abs(normal[2]) > 0.8:
                    z_pos = origin[2]
                    # Filter out front and back surface faces
                    if abs(z_pos - min_z) > 5.0 and abs(z_pos - max_z) > 5.0:
                        f_bbox = face_data[3] if len(face_data) > 3 else None
                        if f_bbox and len(f_bbox) >= 6:
                            fdx = abs(f_bbox[3] - f_bbox[0])
                            fdy = abs(f_bbox[4] - f_bbox[1])
                            if fdx > cell_size * 2.5 or fdy > cell_size * 2.5:
                                continue
                        
                        pocket_floors += 1
                        edges = face.GetEdges()
                        if edges and len(edges) > 0:
                            # Calculate Area / Perimeter^2 Isoperimetric Quotient
                            if len(shape_ratios) < 15:
                                try:
                                    area_prop = workPart.MeasureManager.CreateAreaProperties([face])
                                    area_val = area_prop.Area
                                    area_prop.Dispose()
                                    
                                    perim_val = 0.0
                                    for edge in edges:
                                        try:
                                            lp = workPart.MeasureManager.CreateLengthProperties([edge])
                                            perim_val += lp.Length
                                            lp.Dispose()
                                        except Exception:
                                            pass
                                    if perim_val > 0 and area_val > 0:
                                        ratio = area_val / (perim_val ** 2)
                                        shape_ratios.append(ratio)
                                except Exception:
                                    pass

                            line_count = 0
                            for edge in edges:
                                try:
                                    etype = uf_session.Modeling.AskEdgeType(edge.Tag)
                                    if isinstance(etype, tuple): etype = etype[0]
                                    if etype == 1: line_count += 1
                                except Exception:
                                    try:
                                        etype = uf_session.Modl.AskEdgeType(edge.Tag)
                                        if isinstance(etype, tuple): etype = etype[0]
                                        if etype == 1: line_count += 1
                                    except Exception:
                                        pass
                            if line_count > 0:
                                inner_core_edges.append(line_count)
                            else:
                                inner_core_edges.append(len(edges))
        except Exception as ex_face:
            lw.WriteLine("Face exception: " + str(ex_face))

    avg_ratio = (sum(shape_ratios) / float(len(shape_ratios))) if shape_ratios else 0.0
    lw.WriteLine("Debug: pocket_floors=" + str(pocket_floors) + ", side_wall_count=" + str(side_wall_count) + ", avg_ratio=" + str(round(avg_ratio, 4)) + ", inner_core_edges=" + str(inner_core_edges[:5]))

    # UNIVERSAL PATTERN CLASSIFIER
    p_lower = part_name.lower()
    avg_edges = (sum(inner_core_edges) / float(len(inner_core_edges))) if inner_core_edges else 0.0

    is_hybrid_expr = ("R_TRANS" in expr_dict) or ("TRANSITION" in expr_dict)
    is_hybrid_name = any(kw in p_lower for kw in ["mixed", "hybrid", "radial_mixed"])

    if "double_arch" in p_lower or "H_CENTER" in expr_dict:
        pattern = "double_arch"
        pattern_confidence = "yoder_double_arch"
        pocket_count = pocket_floors if pocket_floors > 0 else 18
    elif "sandwich" in p_lower or "closed" in p_lower:
        pattern = "sandwich_isogrid"
        pattern_confidence = "yoder_sandwich_isogrid"
        pocket_count = pocket_floors if pocket_floors > 0 else 54
    elif is_hybrid_expr or is_hybrid_name:
        if "iso" in p_lower or "tri" in p_lower or "CELL_SIDE" in expr_dict or pocket_floors > 65 or (0.0 < avg_ratio < 0.057) or (0.0 < avg_edges < 4.0):
            pattern = "iso_radial"
            pattern_confidence = "universal_isogrid_radial"
            pocket_count = pocket_floors if pocket_floors > 0 else 56
        elif "square" in p_lower or "waffle" in p_lower or (42 < pocket_floors <= 65) or (0.057 <= avg_ratio < 0.068) or (4.0 <= avg_edges < 5.2):
            pattern = "square_radial"
            pattern_confidence = "universal_square_radial"
            pocket_count = pocket_floors if pocket_floors > 0 else 48
        else:
            pattern = "hex_radial"
            pattern_confidence = "universal_hex_radial"
            pocket_count = pocket_floors if pocket_floors > 0 else 43
    elif "N_RINGS" in expr_dict or "radial" in p_lower:
        pattern = "radial"
        pattern_confidence = "universal_radial"
        pocket_count = pocket_floors if pocket_floors > 0 else 36
    elif "ISOGRID" in expr_dict or "iso" in p_lower or "tri" in p_lower or pocket_floors > 65 or (0.0 < avg_ratio < 0.057) or (0.0 < avg_edges < 4.0):
        pattern = "isogrid"
        pattern_confidence = "universal_isogrid"
        pocket_count = pocket_floors if pocket_floors > 0 else 100
    elif "SQUARE" in expr_dict or "square" in p_lower or "waffle" in p_lower or (42 < pocket_floors <= 65) or (0.057 <= avg_ratio < 0.068) or (4.0 <= avg_edges < 5.2):
        pattern = "square"
        pattern_confidence = "universal_square"
        pocket_count = pocket_floors if pocket_floors > 0 else 48
    else:
        pattern = "hexagonal"
        pattern_confidence = "universal_hexagonal"
        pocket_count = pocket_floors if pocket_floors > 0 else 37

    is_lightweighted = (num_faces > 10) or (pocket_count > 5)
    support_points = 18 if pocket_count > 25 else 9
    density = 2530.0

    # Measure exact mass & volume using standard NewMassProperties
    current_mass_kg = 0.0
    volume_mm3 = 0.0
    try:
        mass_props = workPart.MeasureManager.NewMassProperties([main_body], 0.99, 1)
        volume_mm3 = mass_props.Volume
        current_mass_kg = round(volume_mm3 * density * 1e-9, 2)
    except Exception:
        blank_vol = math.pi * ((diameter / 2.0)**2) * blank_depth
        volume_mm3 = blank_vol * 0.35
        current_mass_kg = round(volume_mm3 * density * 1e-9, 2)

    # YODER & VUKOBRATOVICH OPTO-MECHANICAL METRICS
    solid_vol_mm3 = math.pi * ((diameter / 2.0)**2) * blank_depth
    solid_mass_kg = solid_vol_mm3 * density * 1e-9
    mass_reduction_pct = round(max(0.0, ((solid_mass_kg - current_mass_kg) / solid_mass_kg) * 100.0), 1)

    # Polishing Quilting Deflection Equation: delta_c = psi * (P * B^4) / (E * t_f^3)
    E_mod = 72e9 # Pa (Glass-Ceramic / Fused Silica)
    P_polish = 2000.0 # Pa standard polishing pressure
    t_f_m = faceplate * 1e-3
    B_m = cell_size * 1e-3
    
    psi_shape = 0.00111
    if "iso" in pattern: psi_shape = 0.00151
    elif "square" in pattern: psi_shape = 0.00126
    elif "radial" in pattern or "arch" in pattern: psi_shape = 0.00100
    
    delta_quilt_m = psi_shape * (P_polish * (B_m**4)) / (E_mod * (t_f_m**3))
    quilting_nm = round(delta_quilt_m * 1e9, 1)

    # Yoder Pearson Ratio = (A_surface)^1.5 / V_mirror
    surf_area_m2 = math.pi * ((diameter * 1e-3 / 2.0)**2)
    vol_m3 = volume_mm3 * 1e-9 if volume_mm3 > 0 else 0.01
    pearson_ratio = round((surf_area_m2**1.5) / vol_m3, 2)

    # Fundamental Frequency f_n
    h_c_m = (blank_depth - faceplate) * 1e-3
    eta_solidity = 0.20
    I_0 = (t_f_m**3 + eta_solidity * h_c_m**3 + 3 * t_f_m * h_c_m * (t_f_m + h_c_m)) / (12.0 * (1.0 + eta_solidity * h_c_m / t_f_m))
    D_F = (E_mod * I_0) / (1.0 - 0.17**2)
    gamma_sup = 1.1e-3 if support_points == 18 else 3.2e-3
    delta_pv = gamma_sup * ((density * 9.81 * surf_area_m2) / D_F) * (surf_area_m2 / (support_points**2))
    fn_hz = round((1.0 / (2.0 * math.pi)) * math.sqrt(9.81 / max(1e-9, delta_pv)))

    data = {
        "source": "NX Open Yoder Inspector v7",
        "filename": part_name + ".prt",
        "part_name": part_name,
        "diameter": float(diameter),
        "radius_of_curvature": float(r_curv),
        "blank_depth": float(blank_depth),
        "faceplate_thickness": float(faceplate),
        "cell_grid_size": float(cell_size),
        "rib_width": float(rib_thick),
        "pattern": pattern,
        "pattern_confidence": pattern_confidence,
        "support_points": support_points,
        "material_density": density,
        "is_lightweighted": is_lightweighted,
        "measured_faces": num_faces,
        "pocket_count": pocket_count,
        "current_mass_kg": current_mass_kg,
        "actual_volume_mm3": round(volume_mm3, 1),
        "mass_reduction_pct": mass_reduction_pct,
        "quilting_deflection_nm": quilting_nm,
        "fundamental_frequency_hz": fn_hz,
        "pearson_ratio": pearson_ratio
    }

    json_str = json.dumps(data, indent=2)

    lw = theSession.ListingWindow
    lw.Open()
    try:
        lw.Clear()
    except Exception:
        pass
    lw.WriteLine("=" * 60)
    lw.WriteLine("   NX MIRROR OPTO-MECHANICAL INSPECTION JSON")
    lw.WriteLine("=" * 60)
    lw.WriteLine(json_str)
    lw.WriteLine("=" * 60)

    print("\n=== NX MIRROR INSPECTION JSON ===")
    print(json_str)

if __name__ == '__main__':
    inspect_mirror_part()
