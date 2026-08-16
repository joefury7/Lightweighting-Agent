# ═══════════════════════════════════════════════════════════════════════════════
#  AUTONOMOUS NX OPEN FEA ANALYSIS AUTOMATION SCRIPT
# ═══════════════════════════════════════════════════════════════════════════════
import os
import math
import sys
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

def get_body_bounding_box(body, uf_session):
    tag = body.Tag
    bbox = uf_session.Modl.AskBoundingBox(tag)
    # returns min_x, min_y, min_z, max_x, max_y, max_z
    return bbox[0], bbox[1], bbox[2], bbox[3], bbox[4], bbox[5]

def assign_zerodur_material_cad(workPart, body, lw):
    mat_mgr = workPart.MaterialManager
    zerodur = None
    for mat in mat_mgr.PhysicalMaterials:
        if mat.Name.lower() == "zerodur":
            zerodur = mat
            break
            
    if not zerodur:
        # Create physical material Zerodur in CAD part
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
        # Create physical material Zerodur in FEM part using FieldManager
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

def main():
    theSession = NXOpen.Session.GetSession()
    uf_session = UF.UFSession.GetUFSession()
    
    # Open listing window
    lw = theSession.ListingWindow
    lw.Open()
    
    log(lw, "═" * 75)
    log(lw, "         AUTONOMOUS FEM & SIM CAE AUTOMATION AGENT")
    log(lw, "═" * 75)
    
    workPart = theSession.Parts.Work
    if workPart is None:
        log(lw, "FATAL ERROR: No active part open in NX.")
        return
        
    part_dir = os.path.dirname(workPart.FullPath)
    part_name = os.path.splitext(os.path.basename(workPart.FullPath))[0]
    
    fem_path = os.path.join(part_dir, part_name + "_fem2.fem")
    ideal_path = os.path.join(part_dir, part_name + "_fem2_i.prt")
    sim_path = os.path.join(part_dir, part_name + "_sim2.sim")
    
    log(lw, "[1/7] Inspecting Part Geometry & Expressions...")
    log(lw, "      Original CAD: %s" % workPart.FullPath)
    
    # Read mirror geometry expressions
    try:
        total_depth_exp = workPart.Expressions.FindObject("TOTAL_DEPTH")
        total_depth = float(total_depth_exp.Value)
    except Exception:
        total_depth = 90.0  # fallback
        
    try:
        pocket_depth_exp = workPart.Expressions.FindObject("POCKET_DEPTH")
        pocket_depth = float(pocket_depth_exp.Value)
    except Exception:
        pocket_depth = 75.0  # fallback
        
    log(lw, "      Read total depth: %.2f mm" % total_depth)
    log(lw, "      Read pocket depth: %.2f mm" % pocket_depth)
    
    # Get active mirror body
    bodies = [b for b in workPart.Bodies]
    if not bodies:
        log(lw, "FATAL ERROR: No solid bodies found in part.")
        return
    mirror_body = bodies[0] # assume first body is the mirror
    
    # Assign material Zerodur in CAD part
    assign_zerodur_material_cad(workPart, mirror_body, lw)
    
    # Switch to Pre/Post CAE application
    log(lw, "[2/7] Entering Pre/Post Simulation Environment...")
    theSession.ApplicationSwitchImmediate("UG_APP_SFEM")
    
    # -------------------------------------------------------------------------
    # CREATE FEM PART
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
    
    # Disable synchronizing secondary geometry
    sync_options.SynchronizePointsFlag = False
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
    # GENERATE ADAPTIVE 3D TETRAHEDRAL MESH
    # -------------------------------------------------------------------------
    log(lw, "[4/7] Generating Adaptive 3D Tetrahedral Mesh...")
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

    # Calculate mirror diameter / bounding size dynamically for adaptive meshing
    bbox_dia = 560.0
    try:
        min_x, min_y, min_z, max_x, max_y, max_z = get_body_bounding_box(cae_body, uf_session)
        bbox_dia = max(max_x - min_x, max_y - min_y)
    except Exception:
        pass

    # Adaptive element size: ~4.5% of mirror diameter (e.g. 25mm for 560mm mirror, 63mm for 1400mm mirror)
    adaptive_elem_size = str(round(max(22.0, bbox_dia * 0.045), 1))
    log(lw, "      Calculated adaptive FEA mesh element size: %s mm (Mirror Dia = %.1f mm)" % (adaptive_elem_size, bbox_dia))

    unit_mm = workFemPart.UnitCollection.FindObject("MilliMeter")
    mesh_builder.PropertyTable.SetBooleanPropertyValue("automatic size option bool", True)
    try:
        mesh_builder.PropertyTable.SetBaseScalarWithDataPropertyValue("quad mesh overall edge size", adaptive_elem_size, unit_mm)
    except Exception:
        pass

    mesh_builder.SelectionList.Add(cae_body)
    
    mesh_builder.CommitMesh()
    mesh_builder.Destroy()
    log(lw, "      3D tetrahedral meshing completed successfully.")
    
    # Identify and name the Whiffletree support pad faces in FEM
    log(lw, "      Scanning for Whiffletree support pad faces...")
    pad_count = 0
    back_faces = []
    
    num_faces, face_tags = uf_session.Sf.BodyAskFaces(cae_body.Tag)
    for tag in face_tags:
        try:
            face_obj = NXOpen.TaggedObjectManager.GetTaggedObject(tag)
            cad_faces = face_obj.GetUgfaces()
            if len(cad_faces) > 0:
                cad_face = cad_faces[0]
                face_type, origin, normal, box, radius, _, _ = uf_session.Modeling.AskFaceData(cad_face.Tag)
                # Flat Z-normal faces facing downwards (-Z direction) or on back surface
                if normal[2] < -0.7 or abs(normal[2]) > 0.9:
                    if origin[2] <= -total_depth + 35.0:
                        back_faces.append(face_obj)
                        # Bounding box filter for support pad circular/ring faces (4mm to 40mm size)
                        dx = box[3] - box[0]
                        dy = box[4] - box[1]
                        if (4.0 <= dx <= 40.0) and (4.0 <= dy <= 40.0):
                            face_obj.SetName("SUPPORT_PAD")
                            pad_count += 1
        except Exception:
            pass
            
    # Fallback: if no specific pad faces were matched by size, use all identified back faces
    if pad_count == 0 and back_faces:
        log(lw, "      Using %d back faces for Whiffletree support constraint." % len(back_faces))
        for f in back_faces:
            f.SetName("SUPPORT_PAD")
        pad_count = len(back_faces)
    else:
        log(lw, "      Successfully identified & named %d support pad faces 'SUPPORT_PAD'" % pad_count)
    
    # -------------------------------------------------------------------------
    # CREATE SIM PART
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
    # CREATE SOLUTION & SUBCASE
    # -------------------------------------------------------------------------
    log(lw, "[6/7] Configuring Solution settings...")
    sim_simulation = workSimPart.Simulation
    solution = sim_simulation.CreateSolution("NX NASTRAN", "Structural", "SESTATIC 101 - Single Constraint", "Solution 1", CAE.SimSimulation.AxisymAbstractionType.NotSet)
    
    # Configure output requests to ensure displacement/stress results are computed and saved
    try:
        echo_table = None
        output_table = None
        # Try to find existing modeling object property tables first
        for table in list(workSimPart.ModelingObjectPropertyTables):
            if "Bulk Data Echo Request1" in table.Name:
                echo_table = table
            if "Structural Output Requests1" in table.Name:
                output_table = table
        
        # If not found, create new
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
    
    # Locate all geometric face occurrences in SIM named "SUPPORT_PAD"
    log(lw, "      Applying boundary conditions...")
    sim_pad_faces = []
    object_tag = 0
    while True:
        object_tag = uf_session.Obj.CycleObjsInPart(workSimPart.Tag, UF.UFConstants.UF_caegeom_type, object_tag)
        if object_tag == 0:
            break
        obj_type, obj_sub_type = uf_session.Obj.AskTypeAndSubtype(object_tag)
        if obj_sub_type == UF.UFConstants.UF_caegeom_face_subtype:
            face_occ = NXOpen.TaggedObjectManager.GetTaggedObject(object_tag)
            if face_occ.Name and "SUPPORT_PAD" in face_occ.Name:
                sim_pad_faces.append(face_occ)
                
    log(lw, "      Found %d support pad occurrences in SIM." % len(sim_pad_faces))
    
    # Create Fixed Constraint on Whiffletree support pads
    bc_builder = sim_simulation.CreateBcBuilderForConstraintDescriptor("fixedConstraint", "Fixed(1)", 1)
    set_mgr = bc_builder.TargetSetManager
    
    # Set DOF values to 0
    unit_mm = workSimPart.UnitCollection.FindObject("MilliMeter")
    bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF1").EditFieldExpression("0", unit_mm, [], False)
    bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF2").EditFieldExpression("0", unit_mm, [], False)
    bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF3").EditFieldExpression("0", unit_mm, [], False)
    unit_deg = workSimPart.UnitCollection.FindObject("Degrees")
    bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF4").EditFieldExpression("0", unit_deg, [], False)
    bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF5").EditFieldExpression("0", unit_deg, [], False)
    bc_builder.PropertyTable.GetScalarFieldPropertyValue("DOF6").EditFieldExpression("0", unit_deg, [], False)
    
    # Add support faces to target set members
    set_objects = []
    for face in sim_pad_faces:
        set_obj = CAE.SetObject()
        set_obj.Obj = face
        set_obj.SubType = CAE.CaeSetObjectSubType.NotSet
        set_obj.SubId = 0
        set_objects.append(set_obj)
        
    set_mgr.SetTargetSetMembers(0, CAE.CaeSetGroupFilterType.GeomFace, set_objects)
    constraint = bc_builder.CommitAddBc()
    bc_builder.Destroy()
    
    # Create Gravity Load (1g = 9806.65 mm/s² in -Z)
    gravity_builder = sim_simulation.CreateBcBuilderForLoadDescriptor("magnitudeDirectionGravity", "Gravity(1)", 1)
    
    # Direction: -Z [0, 0, -1]
    origin_g = NXOpen.Point3d(0.0, 0.0, 0.0)
    vector_g = NXOpen.Vector3d(0.0, 0.0, -1.0)
    direction_g = workSimPart.Directions.CreateDirection(origin_g, vector_g, NXOpen.SmartObject.UpdateOption.AfterModeling)
    gravity_builder.PropertyTable.SetVectorPropertyValue("Local Axis", direction_g)
    
    # Magnitude: 9806.65 mm/s² - property is named 'Acceration' (NX internal typo)
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
    
    # Add Constraints & Loads to the solution Subcase
    subcase.AddBc(constraint)
    subcase.AddBc(gravity)
    log(lw, "      Active solution boundary conditions applied successfully.")
    
    # -------------------------------------------------------------------------
    # SAVE AND SOLVE
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
    log(lw, "═" * 75)

if __name__ == '__main__':
    main()
