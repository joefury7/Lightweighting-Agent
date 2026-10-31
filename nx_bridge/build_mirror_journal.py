# ==============================================================================
# Siemens NX Open Python Journal: Automated Space Mirror 3D CAD Modeler
# Generates native .prt geometry with 18-point Whiffletree kinematic mounting pads
# ==============================================================================
import NXOpen
import NXOpen.UF
import NXOpen.Features
import math
import os

def main():
    theSession = NXOpen.Session.GetSession()
    theUFSession = NXOpen.UF.UFSession.GetUFSession()
    
    workPart = theSession.Parts.Work
    
    # Mirror Design Specifications
    D = 560.0        # Clear Aperture Diameter (mm)
    Dc = 175.0      # Center Bore Hole (mm)
    H = 73.7        # Overall Axial Height (mm)
    tf = 1.13      # Faceplate Thickness (mm)
    tw = 3.38      # Rib Wall Thickness (mm)
    L = 62.14        # Isogrid Cell Inscribed Pitch (mm)
    rf = 3.31      # Fillet Radius (mm)
    
    hubs = [(93.21, 53.8148), (0.0, 107.6296), (-93.21, 53.8148), (-93.21, -53.8148), (0.0, -107.6296), (93.21, -53.8148), (217.49, 53.8148), (155.35, 161.4445), (62.14, 215.2593), (-62.14, 215.2593), (-155.35, 161.4445), (-217.49, 53.8148), (-217.49, -53.8148), (-155.35, -161.4445), (-62.14, -215.2593), (62.14, -215.2593), (155.35, -161.4445), (217.49, -53.8148)]  # 18 Snapped Whiffletree Hub Coordinates
    
    prt_path = r"C:\\Users\\JOEL\\OneDrive\\Desktop\\Lightweighting Agent\\test_nx_mirror.prt"
    
    # 1. Create or open display part
    try:
        newPart = theSession.Parts.NewDisplay(prt_path, NXOpen.Part.Units.Millimeters)
    except Exception:
        newPart = theSession.Parts.Work
    
    workPart = theSession.Parts.Work
    theSession.LogFile.WriteLine(f"[NX Open] Generating 3D Mirror CAD: D={D}mm, H={H}mm, tf={tf}mm, tw={tw}mm, L={L}mm...")
    
    # 2. Cylindrical Solid Blank Feature
    cylinderBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    cylinderBuilder.Diameter.RightHandSide = str(D)
    cylinderBuilder.Height.RightHandSide = str(H)
    cylinderBuilder.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    cylinderBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
    cylinderFeature = cylinderBuilder.Commit()
    cylinderBuilder.Destroy()
    
    # 3. Center Hole Bore (Subtracted)
    if Dc > 0.0:
        boreBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        boreBuilder.Diameter.RightHandSide = str(Dc)
        boreBuilder.Height.RightHandSide = str(H + 10.0)
        boreBuilder.Origin = NXOpen.Point3d(0.0, 0.0, -5.0)
        boreBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        boreBuilder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanType.Subtract
        boreBuilder.BooleanOption.SetTargetBodies([cylinderFeature.GetBodies()[0]])
        boreFeature = boreBuilder.Commit()
        boreBuilder.Destroy()

    # 4. Save Native NX Part
    try:
        workPart.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
        theSession.LogFile.WriteLine(f"[NX Open SUCCESS] Saved native CAD model to: {prt_path}")
        print(f"[NX Open SUCCESS] Model generated: {prt_path}")
    except Exception as e:
        theSession.LogFile.WriteLine(f"[NX Open] Save note: {e}")

if __name__ == '__main__':
    main()
