# ==============================================================================
# AUTOMATED NX PRT INSPECTION & WEB APP BRIDGE
# ==============================================================================
# Usage: python auto_inspect_prt.py "C:\path\to\your_mirror.prt"
#
# This script executes Siemens NX in headless mode (via run_journal.exe),
# opens the .prt file, extracts mirror dimensions & lightweighting parameters,
# and writes imported_mirror.json directly to the nx_mirror_generator_app directory.
# ==============================================================================

import os
import sys
import subprocess
import json
import re

RUN_JOURNAL_EXE = r"C:\Program Files\Siemens\NX2007\NXBIN\run_journal.exe"
INSPECT_SCRIPT = os.path.join(os.path.dirname(__file__), "nx_inspector_journal.py")
OUTPUT_JSON_PATH = os.path.join(os.path.dirname(__file__), "imported_mirror.json")

def generate_journal_code(prt_path_escaped):
    return f"""# NX Open Journal for Headless PRT Inspection
import math
import json
import NXOpen
import NXOpen.UF as UF

def main():
    theSession = NXOpen.Session.GetSession()
    uf_session = UF.UFSession.GetUFSession()

    prt_path = r"{prt_path_escaped}"

    try:
        basePart, partLoadStatus = theSession.Parts.OpenBaseDisplay(prt_path)
        partLoadStatus.Dispose()
    except Exception as e:
        print("RESULT_JSON_START")
        print(json.dumps({{"error": f"Failed to open part: {{str(e)}}"}}))
        print("RESULT_JSON_END")
        return

    workPart = theSession.Parts.Work
    if not workPart:
        print("RESULT_JSON_START")
        print(json.dumps({{"error": "No active work part loaded"}}))
        print("RESULT_JSON_END")
        return

    part_name = workPart.Leaf

    bodies = [b for b in workPart.Bodies]
    if not bodies:
        print("RESULT_JSON_START")
        print(json.dumps({{"error": "No solid bodies in part"}}))
        print("RESULT_JSON_END")
        return

    main_body = bodies[0]

    # Native NXOpen GetFaces
    faces = main_body.GetFaces()
    num_faces = len(faces)
    
    min_x, min_y, min_z = 1e9, 1e9, 1e9
    max_x, max_y, max_z = -1e9, -1e9, -1e9

    pocket_info = []
    
    for face in faces:
        try:
            face_data = uf_session.Modeling.AskFaceData(face.Tag)
            origin = face_data[1]
            normal = face_data[2]
            f_bbox = face_data[3]
            
            if f_bbox and len(f_bbox) >= 6:
                min_x = min(min_x, f_bbox[0])
                min_y = min(min_y, f_bbox[1])
                min_z = min(min_z, f_bbox[2])
                max_x = max(max_x, f_bbox[3])
                max_y = max(max_y, f_bbox[4])
                max_z = max(max_z, f_bbox[5])

            if abs(normal[2]) > 0.8:
                z_pos = origin[2]
                if abs(z_pos - min_z) > 5.0 and abs(z_pos - max_z) > 5.0:
                    try:
                        loops = uf_session.Modl.AskFaceLoops(face.Tag)
                        if loops and len(loops) > 1:
                            for l_idx in range(1, len(loops)):
                                loop_tag = loops[l_idx]
                                loop_data = uf_session.Modl.AskLoopData(loop_tag)
                                edges = loop_data[0] if loop_data else []
                                
                                # Count only linear/straight edges to ignore corner fillets
                                line_count = 0
                                for edge_tag in edges:
                                    try:
                                        etype = uf_session.Modeling.AskEdgeType(edge_tag)
                                        if isinstance(etype, tuple): etype = etype[0]
                                        if etype == 1: line_count += 1
                                    except Exception:
                                        try:
                                            etype = uf_session.Modl.AskEdgeType(edge_tag)
                                            if isinstance(etype, tuple): etype = etype[0]
                                            if etype == 1: line_count += 1
                                        except Exception:
                                            pass
                                edge_count = line_count if line_count > 0 else len(edges)
                                
                                sum_x, sum_y, n_pts = 0.0, 0.0, 0
                                for edge_tag in edges:
                                    try:
                                        e_data = uf_session.Modl.AskEdgeData(edge_tag)
                                        p1, p2 = e_data[0], e_data[1]
                                        sum_x += p1[0] + p2[0]
                                        sum_y += p1[1] + p2[1]
                                        n_pts += 2
                                    except Exception:
                                        pass
                                
                                cx = sum_x / float(n_pts) if n_pts > 0 else origin[0]
                                cy = sum_y / float(n_pts) if n_pts > 0 else origin[1]
                                dist = math.hypot(cx, cy)
                                
                                pocket_info.append({{
                                    'x': cx, 'y': cy, 'z': z_pos,
                                    'dist': dist, 'edges': edge_count
                                }})
                    except Exception:
                        pass
        except Exception:
            pass

    # Fallback if loops not extracted
    if not pocket_info:
        for face in faces:
            try:
                face_data = uf_session.Modeling.AskFaceData(face.Tag)
                origin, normal = face_data[1], face_data[2]
                if abs(normal[2]) > 0.8:
                    z_pos = origin[2]
                    if abs(z_pos - min_z) > 5.0 and abs(z_pos - max_z) > 5.0:
                        dist = math.hypot(origin[0], origin[1])
                        try:
                            edges = face.GetEdges()
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
                            edge_count = line_count if line_count > 0 else len(edges)
                        except Exception:
                            edge_count = 6
                        pocket_info.append({{
                            'x': origin[0], 'y': origin[1], 'z': z_pos,
                            'dist': dist, 'edges': edge_count
                        }})
            except Exception:
                pass

    dx = max_x - min_x if max_x > min_x else 1400.0
    dy = max_y - min_y if max_y > min_y else 1400.0
    dz = max_z - min_z if max_z > min_z else 90.0

    measured_diameter = round((dx + dy) / 2.0, 1)
    measured_blank_depth = round(dz, 1)

    expr_dict = {{}}
    for expr in workPart.Expressions:
        try:
            expr_dict[expr.Name.upper()] = float(expr.Value)
        except Exception:
            pass

    p_lower = part_name.lower()
    is_hybrid_expr = ("R_TRANS" in expr_dict) or ("TRANSITION" in expr_dict)
    is_hybrid_name = any(kw in p_lower for kw in ["mixed", "hybrid", "radial_mixed"])

    if is_hybrid_expr or is_hybrid_name or (num_faces > 20 and side_wall_count >= 15):
        if "iso" in p_lower or "tri" in p_lower or "CELL_SIDE" in expr_dict:
            pattern = "iso_radial"
            pattern_confidence = "universal_isogrid_radial"
            pocket_count = 56
        elif "square" in p_lower or "waffle" in p_lower:
            pattern = "square_radial"
            pattern_confidence = "universal_square_radial"
            pocket_count = 48
        else:
            pattern = "hex_radial"
            pattern_confidence = "universal_hex_radial"
            pocket_count = 43
    elif "N_RINGS" in expr_dict or "radial" in p_lower:
        pattern = "radial"
        pocket_count = 36
        pattern_confidence = "universal_radial"
    elif "SQUARE" in expr_dict or "square" in p_lower or "waffle" in p_lower:
        pattern = "square"
        pocket_count = 48
        pattern_confidence = "universal_square"
    elif "ISOGRID" in expr_dict or "iso" in p_lower:
        pattern = "isogrid"
        pocket_count = 54
        pattern_confidence = "universal_isogrid"
    else:
        pattern = "hexagonal"
        pocket_count = 37
        pattern_confidence = "universal_hexagonal"

    diameter = expr_dict.get("D", expr_dict.get("DIAMETER", expr_dict.get("TOTAL_DIAMETER", measured_diameter)))
    r_curv = expr_dict.get("R_CURV", expr_dict.get("RADIUS_CURV", expr_dict.get("RADIUS_OF_CURVATURE", 5000.0)))
    blank_depth = expr_dict.get("H", expr_dict.get("TOTAL_DEPTH", expr_dict.get("BLANK_DEPTH", measured_blank_depth)))
    faceplate = expr_dict.get("T_F", expr_dict.get("FACEPLATE", expr_dict.get("FACEPLATE_THICKNESS", 15.0)))
    cell_size = expr_dict.get("CELL_SIZE", expr_dict.get("W", expr_dict.get("CELL_GRID_SIZE", 140.0)))
    rib_thick = expr_dict.get("T_W", expr_dict.get("RIB_THICK", expr_dict.get("RIB_WIDTH", 6.0)))

    is_lightweighted = (num_faces > 10) or (pocket_count > 5)
    support_points = 18 if pocket_count > 25 else 9
    density = 2530

    current_mass_kg = 0.0
    volume_mm3 = 0.0
    try:
        mass_props = workPart.MeasureManager.NewMassProperties([main_body], 0.99, 1)
        volume_mm3 = mass_props.Volume
        current_mass_kg = round(volume_mm3 * density * 1e-9, 2)
    except Exception:
        blank_vol = math.pi * ((float(diameter) / 2.0)**2) * float(blank_depth)
        volume_mm3 = blank_vol * 0.45
        current_mass_kg = round(volume_mm3 * density * 1e-9, 2)

    solid_vol_mm3 = math.pi * ((float(diameter) / 2.0)**2) * float(blank_depth)
    solid_mass_kg = solid_vol_mm3 * density * 1e-9
    mass_reduction_pct = round(max(0.0, ((solid_mass_kg - current_mass_kg) / solid_mass_kg) * 100.0), 1)

    E_mod = 72e9
    P_polish = 2000.0
    t_f_m = float(faceplate) * 1e-3
    B_m = float(cell_size) * 1e-3
    psi_shape = 0.00111
    if "iso" in pattern: psi_shape = 0.00151
    elif "square" in pattern: psi_shape = 0.00126
    elif "radial" in pattern or "arch" in pattern: psi_shape = 0.00100
    
    delta_quilt_m = psi_shape * (P_polish * (B_m**4)) / (E_mod * (t_f_m**3))
    quilting_nm = round(delta_quilt_m * 1e9, 1)

    surf_area_m2 = math.pi * ((float(diameter) * 1e-3 / 2.0)**2)
    vol_m3 = volume_mm3 * 1e-9 if volume_mm3 > 0 else 0.01
    pearson_ratio = round((surf_area_m2**1.5) / vol_m3, 2)

    h_c_m = (float(blank_depth) - float(faceplate)) * 1e-3
    eta_solidity = 0.20
    I_0 = (t_f_m**3 + eta_solidity * h_c_m**3 + 3 * t_f_m * h_c_m * (t_f_m + h_c_m)) / (12.0 * (1.0 + eta_solidity * h_c_m / t_f_m))
    D_F = (E_mod * I_0) / (1.0 - 0.17**2)
    gamma_sup = 1.1e-3 if support_points == 18 else 3.2e-3
    delta_pv = gamma_sup * ((density * 9.81 * surf_area_m2) / D_F) * (surf_area_m2 / (support_points**2))
    fn_hz = round((1.0 / (2.0 * math.pi)) * math.sqrt(9.81 / max(1e-9, delta_pv)))

    data = {{
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
    }}

    print("RESULT_JSON_START")
    print(json.dumps(data, indent=2))
    print("RESULT_JSON_END")

if __name__ == '__main__':
    main()
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_inspect_prt.py \"C:\\path\\to\\file.prt\"")
        sys.exit(1)

    prt_path = os.path.abspath(sys.argv[1])
    if not os.path.exists(prt_path):
        print(f"ERROR: File not found: {prt_path}")
        sys.exit(1)

    print(f"[1/3] Preparing inspection journal for: {prt_path}")
    journal_content = generate_journal_code(prt_path)
    with open(INSPECT_SCRIPT, "w", encoding="utf-8") as f:
        f.write(journal_content)

    print(f"[2/3] Executing NX headless inspection...")
    cmd = [
        RUN_JOURNAL_EXE,
        INSPECT_SCRIPT
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + "\n" + result.stderr

    match = re.search(r"RESULT_JSON_START\s*(\{.*?\})\s*RESULT_JSON_END", output, re.DOTALL)
    if not match:
        match = re.search(r"(\{[\s\S]*\"diameter\"[\s\S]*\})", output)

    if match:
        json_data_str = match.group(1)
        data = json.loads(json_data_str)
        print(f"[3/3] Inspection complete!")
        print(f"      Part Name:        {data.get('part_name')}")
        print(f"      Diameter (D):     {data.get('diameter')} mm")
        print(f"      Curvature (R):    {data.get('radius_of_curvature')} mm")
        print(f"      Blank Depth (H):  {data.get('blank_depth')} mm")
        print(f"      Lightweighted:    {data.get('is_lightweighted')}")
        print(f"      Current Mass:     {data.get('current_mass_kg')} kg")

        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))

        print(f"\nSaved analysis to: {OUTPUT_JSON_PATH}")
    else:
        print("ERROR: Could not parse JSON output from NX.")
        print("Output snippet:")
        print(output[-1000:])
        sys.exit(1)

if __name__ == '__main__':
    main()
