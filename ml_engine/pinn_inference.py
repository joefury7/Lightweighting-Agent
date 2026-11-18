"""
Zernike-resolved surrogate prediction (replaces the former "PINN").

The previous network was trained mostly on closed-form formulas plus external datasets mapped
onto invented geometry; its sag predictions were uncorrelated with physics (r = -0.18).
This module now serves predictions from ml_engine/fea_surrogate.py, which is trained only on
finite-element results of the exact NX-journal geometry, including 37 Fringe Zernike
coefficients fitted to the FE surface deflection.

`PINNMirrorPredictor` is kept as an alias so existing imports / the /pinn/predict endpoint work.
"""
import os
import sys
import time

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor  # noqa: E402


class ZernikeSurrogatePredictor:
    def __init__(self, models_dir=None):
        self.base = MirrorSurrogatePredictor()

    def predict(self, D_mm=560.0, Dc_mm=175.0, H_mm=73.7, tf_mm=1.0, tw_mm=3.0, L_mm=55.5, rf_mm=3.0,
                material="zerodur", topology="triangular_isogrid"):
        t0 = time.perf_counter()
        if topology not in ("triangular_isogrid", "isogrid"):
            raise ValueError(f"No FEA training data for topology '{topology}' (only triangular isogrid).")
        r = self.base.predict(D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm, material=material, topology=topology)
        z = r["zernike_fringe_37_nm"]
        r["zernike_37_coefficients"] = z
        r["dominant_zernike_modes"] = {
            "Z4_Defocus_nm": round(z[3], 3),
            "Z9_Primary_Spherical_nm": round(z[8], 3),
            "Z10_Primary_Trefoil_3Fold_nm": round(z[9], 3),
            "Z16_Secondary_Spherical_nm": round(z[15], 3),
            "Z37_Hexafoil_6Fold_Whiffletree_nm": round(z[36], 3),
        }
        r["inference_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        r["surrogate_architecture"] = "Gaussian-process surrogate trained on FEA of the exact geometry"
        r["material"], r["topology"] = material, topology
        return r


PINNMirrorPredictor = ZernikeSurrogatePredictor   # backwards-compatible name
