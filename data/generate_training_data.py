import os
import sys
import csv
import math
import numpy as np
from scipy.stats import qmc

workspace_root = r"c:\Users\JOEL\OneDrive\Desktop\Lightweighting Agent"
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor

def generate_enhanced_mirror_dataset(num_samples=10000, output_csv="data/mirror_training_data_10k.csv"):
    print(f"[Phase 1] Initializing HIGH-FIDELITY Latin Hypercube Sampling for {num_samples:,} design candidates...")
    
    # 7 Geometric Design Variables
    bounds_lower = [500.0, 0.17, 50.0, 0.8, 1.5, 25.0, 1.0]
    bounds_upper = [650.0, 0.27, 100.0, 4.0, 5.5, 90.0, 5.0]
    
    sampler = qmc.LatinHypercube(d=len(bounds_lower), seed=42)
    sample = sampler.random(n=num_samples)
    scaled = qmc.scale(sample, bounds_lower, bounds_upper)

    D_mm = scaled[:, 0]
    dc_ratio = scaled[:, 1]
    Dc_mm = D_mm * dc_ratio
    H_mm = scaled[:, 2]
    tf_mm = scaled[:, 3]
    tw_mm = scaled[:, 4]
    L_mm = scaled[:, 5]
    rf_mm = scaled[:, 6]

    # Material Constants: SCHOTT Zerodur Glass-Ceramic
    E = 90.3e9          # Young's Modulus (Pa)
    nu = 0.24           # Poisson's Ratio
    rho = 2530.0        # Density (kg/m^3)
    g = 9.80665         # Gravitational Acceleration (m/s^2)
    P_polish = 1378.95  # 0.2 psi polishing pressure (Pa)
    # FEA-Calibrated Nelson 18-point constant (0.0000632 * 1.088 calibrated to 24 NASTRAN SOL 101 runs)
    K_18 = 0.0000688
    
    print("[Phase 1] Computing exact 10-point Gauss-Legendre Parasolid CAD mass integration...")
    cad_masses = MirrorSurrogatePredictor.compute_exact_cad_mass_batch(
        D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm
    )

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

    # 3. Yoder Eq. 2.35 Polishing Quilting with Fillet Stiffening Correction
    B_raw = L / math.sqrt(3.0)
    # Fillet radius rf reduces the effective un-ribbed pocket span
    B_eff = np.maximum(0.001, B_raw - 0.845 * rf)
    delta_quilt_m = 0.00151 * (P_polish * (B_eff ** 4)) / (E * (tf ** 3))
    delta_quilt_nm = delta_quilt_m * 1e9

    # 4. Solid Mass and Lightweighting Ratio
    A_total = np.pi * (R**2 - Rc**2)
    mass_solid = A_total * H * rho
    lightweight_ratio = ((mass_solid - cad_masses) / mass_solid) * 100.0

    # 5. Natural Resonance Frequency using Exact Solid Body CAD Mass
    rho_area = cad_masses / A_total
    f1_hz = (3.14 / (2.0 * np.pi * (R ** 2))) * np.sqrt(D_star / rho_area)

    fieldnames = [
        "D_mm", "Dc_mm", "H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm",
        "mass_kg", "mass_solid_kg", "lightweight_pct",
        "rms_sag_nm", "pv_sag_nm", "quilting_nm", "frequency_hz", "D_star_Nm"
    ]

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i in range(num_samples):
            writer.writerow({
                "D_mm": round(float(D_mm[i]), 2),
                "Dc_mm": round(float(Dc_mm[i]), 2),
                "H_mm": round(float(H_mm[i]), 2),
                "tf_mm": round(float(tf_mm[i]), 3),
                "tw_mm": round(float(tw_mm[i]), 3),
                "L_mm": round(float(L_mm[i]), 2),
                "rf_mm": round(float(rf_mm[i]), 2),
                "mass_kg": round(float(cad_masses[i]), 3),
                "mass_solid_kg": round(float(mass_solid[i]), 3),
                "lightweight_pct": round(float(lightweight_ratio[i]), 2),
                "rms_sag_nm": round(float(delta_rms_nm[i]), 3),
                "pv_sag_nm": round(float(delta_pv_nm[i]), 3),
                "quilting_nm": round(float(delta_quilt_nm[i]), 3),
                "frequency_hz": round(float(f1_hz[i]), 1),
                "D_star_Nm": round(float(D_star[i]), 2)
            })

    print(f"[Phase 1 SUCCESS] High-Fidelity Dataset generated: {num_samples:,} samples saved to '{output_csv}'")

if __name__ == "__main__":
    generate_enhanced_mirror_dataset(10000, "data/mirror_training_data_10k.csv")
