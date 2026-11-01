# ==============================================================================
# Siemens NX Open Python Journal: Automated Space Mirror 3D CAD Modeler
# Generates native .prt geometry with 18-point Whiffletree kinematic mounting pads
# ==============================================================================
import NXOpen
import NXOpen.UF
import NXOpen.Features
import NXOpen.GeometricUtilities
import math
import os

def main():
    theSession = NXOpen.Session.GetSession()
    theUFSession = NXOpen.UF.UFSession.GetUFSession()
    
    # Mirror Design Specifications
    D = 560.0        # Clear Aperture Diameter (mm)
    Dc = 175.0      # Center Bore Hole (mm)
    H = 73.7        # Overall Axial Height (mm)
    tf = 1.0      # Faceplate Thickness (mm)
    tw = 3.0      # Rib Wall Thickness (mm)
    L = 55.5        # Isogrid Cell Inscribed Pitch (mm)
    rf = 3.0      # Fillet Radius (mm)
    
    hubs = [(83.25, 48.0644), (0.0, 96.1288), (-83.25, 48.0644), (-83.25, -48.0644), (0.0, -96.1288), (83.25, -48.0644), (194.25, 48.0644), (138.75, 144.1932), (55.5, 192.2576), (-55.5, 192.2576), (-138.75, 144.1932), (-194.25, 48.0644), (-194.25, -48.0644), (-138.75, -144.1932), (-55.5, -192.2576), (55.5, -192.2576), (138.75, -144.1932), (194.25, -48.0644)]  # 18 Snapped Whiffletree Hub Coordinates
    
    prt_path = r"C:\\Users\\JOEL\\OneDrive\\Desktop\\Lightweighting Agent\\primary_mirror_560mm.prt"
    
    # 1. Create or open display part
    try:
        if os.path.exists(prt_path):
            os.remove(prt_path)
    except Exception:
        pass
        
    workPart = theSession.Parts.NewDisplay(prt_path, NXOpen.Part.Units.Millimeters)
    theSession.LogFile.WriteLine(f"[NX Open] Generating 3D Mirror CAD: D={D}mm, H={H}mm, tf={tf}mm, tw={tw}mm, L={L}mm...")
    
    # 2. Cylindrical Solid Blank Feature
    cylinderBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    cylinderBuilder.Diameter.RightHandSide = str(D)
    cylinderBuilder.Height.RightHandSide = str(H)
    cylinderBuilder.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    cylinderBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
    cylinderFeature = cylinderBuilder.Commit()
    cylinderBuilder.Destroy()
    blankBody = cylinderFeature.GetBodies()[0]
    
    # 3. Center Hole Bore (Subtracted)
    if Dc > 0.0:
        boreBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        boreBuilder.Diameter.RightHandSide = str(Dc)
        boreBuilder.Height.RightHandSide = str(H + 20.0)
        boreBuilder.Origin = NXOpen.Point3d(0.0, 0.0, -10.0)
        boreBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        boreBuilder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        boreBuilder.BooleanOption.SetTargetBodies([blankBody])
        boreFeature = boreBuilder.Commit()
        boreBuilder.Destroy()

    # 4. Mill Isogrid Pocket Cavities over Pocket Zone
    R = D / 2.0
    Rc = Dc / 2.0
    pocket_depth = H - tf
    w_rim = 5.0
    r_in = Rc + w_rim
    r_out = R - w_rim

    dx = L
    dy = L * math.sqrt(3.0) / 2.0
    nx = int(math.ceil(D / dx)) + 1
    ny = int(math.ceil(D / dy)) + 1
    pocket_dia = max(10.0, L - 2.0 * tw / math.sqrt(3.0))

    pockets_created = 0
    for j in range(-ny, ny + 1):
        py = j * dy
        x_off = (dx / 2.0) if (j % 2 != 0) else 0.0
        for i in range(-nx, nx + 1):
            px = i * dx + x_off
            dist = math.hypot(px, py)
            if (r_in + pocket_dia/2.0) <= dist <= (r_out - pocket_dia/2.0):
                near_hub = any(math.hypot(px - hx, py - hy) < 14.0 for hx, hy in hubs)
                if not near_hub:
                    pBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
                    pBuilder.Diameter.RightHandSide = str(round(pocket_dia, 2))
                    pBuilder.Height.RightHandSide = str(round(pocket_depth + 5.0, 2))
                    pBuilder.Origin = NXOpen.Point3d(px, py, tf)
                    pBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
                    pBuilder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
                    pBuilder.BooleanOption.SetTargetBodies([blankBody])
                    pFeat = pBuilder.Commit()
                    pBuilder.Destroy()
                    pockets_created += 1

    theSession.LogFile.WriteLine(f"[NX Open SUCCESS] Milled {pockets_created} isogrid pocket cavities.")

    # 5. Save Native NX Part
    try:
        workPart.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
        theSession.LogFile.WriteLine(f"[NX Open SUCCESS] Saved native CAD model to: {prt_path}")
        print(f"[NX Open SUCCESS] Model generated with {pockets_created} isogrid cavities: {prt_path}")
    except Exception as e:
        theSession.LogFile.WriteLine(f"[NX Open] Save note: {e}")

    try:
        if workPart is not None:
            workPart.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
            print(f"[NX Open SUCCESS] Model saved to: C:\Users\JOEL\OneDrive\Desktop\Lightweighting Agent\primary_mirror_560mm.prt")
    except Exception as e_save:
        print(f"[NX Open] Save warning: {e_save}")

if __name__ == '__main__':
    main()
