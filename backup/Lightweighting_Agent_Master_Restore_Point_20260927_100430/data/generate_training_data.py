"""
Physics-Grounded Dataset Generator for Space Mirror Lightweighting (Pillar 2)
FOCUSED VERSION: Tightly bounded around the 500-650mm Zerodur design space.
Generates 10,000 synthetic design samples using Latin Hypercube Sampling (LHS)
and analytical optomechanical physics equations (NASA SP-8040 + Nelson K18 + Yoder).
"""

import os
import csv
import math
import numpy as np
from scipy.stats import qmc

def generate_mirror_dataset(num_samples=10000, output_csv="data/mirror_training_data_10k.csv"):
    print(f"[Phase 1] Initializing FOCUSED Latin Hypercube Sampling for {num_samples:,} design candidates...")
    print(f"[Phase 1] Bounds: D=500-650mm | tf=0.8-4.0mm | tw=1.5-5.5mm | L=25-90mm")
    
    # FOCUSED 7 Geometric Design Variables — tightly bounded on 500-650mm Zerodur mirror design space
    # 1. Diameter D (mm)               [500 to 650]   <- Focused on benchmark range
    # 2. Center Hole Ratio (Dc/D)      [0.17 to 0.27] <- Reasonable hub sizes
    # 3. Overall Height H (mm)         [50.0 to 100.0] <- Practical mirror heights
    # 4. Faceplate Thickness tf (mm)   [0.8 to 4.0]   <- Thin to moderate faceplates
    # 5. Rib Thickness tw (mm)         [1.5 to 5.5]   <- Standard rib sizes
    # 6. Triangular Cell Diam L (mm)   [25.0 to 90.0] <- Tight to wide isogrid cells
    # 7. Fillet Radius rf (mm)         [1.0 to 5.0]   <- CNC tool radius
    
    bounds_lower = [500.0, 0.17, 50.0, 0.8, 1.5, 25.0, 1.0]
    bounds_upper = [650.0, 0.27, 100.0, 4.0, 5.5, 90.0, 5.0]
    
    sampler = qmc.LatinHypercube(d=len(bounds_lower), seed=42)
    sample = sampler.random(n=num_samples)
    scaled = qmc.scale(sample, bounds_lower, bounds_upper)

    # Material Constants: SCHOTT Zerodur Glass-Ceramic
    E = 90.3e9          # Young's Modulus (Pa)
    nu = 0.24           # Poisson's Ratio
    rho = 2530.0        # Density (kg/m^3)
    g = 9.80665         # Gravitational Acceleration (m/s^2)
    P_polish = 1378.95  # 0.2 psi polishing pressure (Pa)
    K_18 = 0.0000632   # NASTRAN-Calibrated Nelson 18-point constant (Run 306: 58.11nm @ 560mm Zerodur)
    # C_quilt = 0.00151 (triangular isogrid, Yoder Eq.2.35) — embedded directly in formula below
    # NOTE: 0.00126 was the wrong hex/square constant; 0.00151 is correct for triangular isogrid
    
    fieldnames = [
        "D_mm", "Dc_mm", "H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm",
        "mass_kg", "mass_solid_kg", "lightweight_pct",
        "rms_sag_nm", "pv_sag_nm", "quilting_nm", "frequency_hz", "D_star_Nm"
    ]

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in scaled:
            D_mm, dc_ratio, H_mm, tf_mm, tw_mm, L_mm, rf_mm = row
            Dc_mm = D_mm * dc_ratio
            
            # Convert to SI units (meters)
            D = D_mm / 1000.0
            Dc = Dc_mm / 1000.0
            H = H_mm / 1000.0
            tf = tf_mm / 1000.0
            tw = tw_mm / 1000.0
            L = L_mm / 1000.0
            rf = rf_mm / 1000.0
            
            R = D / 2.0
            Rc = Dc / 2.0
            pocket_depth = H - tf
            
            # 1. NASA SP-8040 Isogrid Equivalent Plate Flexural Rigidity D* (N*m)
            D_solid = (E * (tf ** 3)) / (12.0 * (1.0 - nu ** 2))
            rib_enhancement = 1.0 + (tw / L) * ((pocket_depth / tf) ** 3)
            D_star = D_solid * rib_enhancement
            
            # 2. Nelson 18-Point Whiffletree RMS Gravity Sag (m -> nm)
            delta_rms_m = K_18 * (rho * g * (R ** 4)) / D_star
            delta_rms_nm = delta_rms_m * 1e9
            delta_pv_nm = delta_rms_nm * 3.82
            
            # 3. Yoder Eq. 2.35 Polishing Quilting Deformation (m -> nm)
            # B = inscribed pocket diameter for equilateral-triangle isogrid cell of pitch L
            # B = L / sqrt(3)  (NOT raw pitch L — using L inflates quilting by (sqrt(3))^4 = 9x)
            # C_quilt = 0.00151 for triangular isogrid (NOT 0.00126 which is hex/square)
            B = L / math.sqrt(3.0)
            delta_quilt_m = 0.00151 * (P_polish * (B ** 4)) / (E * (tf ** 3))
            delta_quilt_nm = delta_quilt_m * 1e9
            
            # 4. Volumetric Mass Calculation (kg)
            # 0.8743 = CAD-volume calibration factor from Run 306 NX/NASTRAN verification
            # (accounts for 3D sag-corrected pocket volume vs simplified planar model)
            A_total = math.pi * (R**2 - Rc**2)
            mass_solid = A_total * H * rho
            
            rim_width = 0.012
            hub_width = 0.012
            R_pocket_max = max(Rc + hub_width, R - rim_width)
            R_pocket_min = Rc + hub_width
            
            if R_pocket_max > R_pocket_min:
                A_pocket_zone = math.pi * (R_pocket_max**2 - R_pocket_min**2)
                isogrid_pocket_fraction = max(0.2, min(0.85, 1.0 - (2.0 * math.sqrt(3.0) * tw / L)))
                V_removed = A_pocket_zone * pocket_depth * isogrid_pocket_fraction
                mass_actual = max(0.5, mass_solid - (V_removed * rho * 1.0173))
            else:
                mass_actual = mass_solid
                
            lightweight_ratio = ((mass_solid - mass_actual) / mass_solid) * 100.0
            
            # 5. First Natural Resonance Frequency f1 (Hz)
            rho_area = mass_actual / A_total
            f1_hz = (3.14 / (2.0 * math.pi * (R ** 2))) * math.sqrt(D_star / rho_area)
            
            writer.writerow({
                "D_mm": round(D_mm, 2),
                "Dc_mm": round(Dc_mm, 2),
                "H_mm": round(H_mm, 2),
                "tf_mm": round(tf_mm, 3),
                "tw_mm": round(tw_mm, 3),
                "L_mm": round(L_mm, 2),
                "rf_mm": round(rf_mm, 2),
                "mass_kg": round(mass_actual, 3),
                "mass_solid_kg": round(mass_solid, 3),
                "lightweight_pct": round(lightweight_ratio, 2),
                "rms_sag_nm": round(delta_rms_nm, 3),
                "pv_sag_nm": round(delta_pv_nm, 3),
                "quilting_nm": round(delta_quilt_nm, 3),
                "frequency_hz": round(f1_hz, 1),
                "D_star_Nm": round(D_star, 2)
            })
        
    print(f"[Phase 1 SUCCESS] Dataset generated: {num_samples:,} samples saved to '{output_csv}'")

if __name__ == "__main__":
    generate_mirror_dataset(10000, "data/mirror_training_data_10k.csv")
