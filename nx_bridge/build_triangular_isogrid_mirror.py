# ==============================================================================
# Siemens NX Open Python Journal: Automated 3D Spaceborne Mirror CAD
# Topology: TRIANGULAR_ISOGRID | Integrated 18-Point Whiffletree Mount
# Generated automatically by Autonomous Generative Lightweighting Agent
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

    D = 560.0
    Dc = 120.0
    H = 73.7
    tf = 1.0
    tw = 3.0
    L = 55.5
    rf = 3.0
    topology = "triangular_isogrid"
    material = "zerodur"

    hubs = [(83.25, 48.0644), (0.0, 96.1288), (-83.25, 48.0644), (-83.25, -48.0644), (0.0, -96.1288), (83.25, -48.0644), (194.25, 48.0644), (138.75, 144.1932), (55.5, 192.2576), (-55.5, 192.2576), (-138.75, 144.1932), (-194.25, 48.0644), (-194.25, -48.0644), (-138.75, -144.1932), (-55.5, -192.2576), (55.5, -192.2576), (138.75, -144.1932), (194.25, -48.0644)]  # 18-Point Kinematic Whiffletree Hub Coordinates

    prt_path = r"C:\Users\JOEL\OneDrive\Desktop\Lightweighting Agent\primary_mirror_triangular_isogrid_560mm.prt"
    try:
        if os.path.exists(prt_path):
            os.remove(prt_path)
    except Exception:
        pass

    workPart = theSession.Parts.NewDisplay(prt_path, NXOpen.Part.Units.Millimeters)
    theSession.LogFile.WriteLine(f"[NX Open] Synthesizing {topology} Mirror: D={D}mm, H={H}mm, tf={tf}mm...")

    # 1. Blank Solid Cylinder Feature
    cyl = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    cyl.Diameter.RightHandSide = str(D)
    cyl.Height.RightHandSide = str(H)
    cyl.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    cyl.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
    blank_feat = cyl.Commit()
    cyl.Destroy()
    blankBody = blank_feat.GetBodies()[0]

    # 2. Central Bore Hole Subtract
    if Dc > 0.0:
        bore = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        bore.Diameter.RightHandSide = str(Dc)
        bore.Height.RightHandSide = str(H + 20.0)
        bore.Origin = NXOpen.Point3d(0.0, 0.0, -10.0)
        bore.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        bore.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        bore.BooleanOption.SetTargetBodies([blankBody])
        bore_feat = bore.Commit()
        bore.Destroy()

    # 3. Mill Lightweighting Pocket Topologies (48 pockets synthesized)
    pockets = [{'x': -27.75, 'y': -240.322, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 27.75, 'y': -240.322, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -111.0, 'y': -192.258, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 0.0, 'y': -192.258, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 111.0, 'y': -192.258, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -194.25, 'y': -144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -83.25, 'y': -144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -27.75, 'y': -144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 27.75, 'y': -144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 83.25, 'y': -144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 194.25, 'y': -144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -222.0, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -166.5, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -111.0, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -55.5, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 55.5, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 111.0, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 166.5, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 222.0, 'y': -96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -138.75, 'y': -48.064, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 138.75, 'y': -48.064, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -222.0, 'y': 0.0, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -166.5, 'y': 0.0, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -111.0, 'y': 0.0, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 111.0, 'y': 0.0, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 166.5, 'y': 0.0, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 222.0, 'y': 0.0, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -138.75, 'y': 48.064, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 138.75, 'y': 48.064, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -222.0, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -166.5, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -111.0, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -55.5, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 55.5, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 111.0, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 166.5, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 222.0, 'y': 96.129, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -194.25, 'y': 144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -83.25, 'y': 144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -27.75, 'y': 144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 27.75, 'y': 144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 83.25, 'y': 144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 194.25, 'y': 144.193, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -111.0, 'y': 192.258, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 0.0, 'y': 192.258, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 111.0, 'y': 192.258, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': -27.75, 'y': 240.322, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}, {'x': 27.75, 'y': 240.322, 'shape': 'triangle', 'size': 52.036, 'depth': 72.7}]
    pockets_created = 0
    for p in pockets:
        px = p["x"]
        py = p["y"]
        p_dia = p["size"]
        p_depth = p["depth"]
        pBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        pBuilder.Diameter.RightHandSide = str(p_dia)
        pBuilder.Height.RightHandSide = str(p_depth + 5.0)
        pBuilder.Origin = NXOpen.Point3d(px, py, tf)
        pBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        pBuilder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        pBuilder.BooleanOption.SetTargetBodies([blankBody])
        pFeat = pBuilder.Commit()
        pBuilder.Destroy()
        pockets_created += 1

    theSession.LogFile.WriteLine(f"[NX Open SUCCESS] Successfully created {pockets_created} lightweight pocket cavities.")

    # 4. Create 18-Point Kinematic Whiffletree Retention Hubs
    for idx, (hx, hy) in enumerate(hubs):
        hubBuilder = workPart.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        hubBuilder.Diameter.RightHandSide = "20.0"
        hubBuilder.Height.RightHandSide = str(round(H - tf, 2))
        hubBuilder.Origin = NXOpen.Point3d(hx, hy, tf)
        hubBuilder.Direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        hubBuilder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
        hubBuilder.BooleanOption.SetTargetBodies([blankBody])
        hubFeat = hubBuilder.Commit()
        hubBuilder.Destroy()

    # Save Part
    workPart.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    theSession.LogFile.WriteLine(f"[NX Open COMPLETED] Part saved at {prt_path}")

if __name__ == "__main__":
    main()
