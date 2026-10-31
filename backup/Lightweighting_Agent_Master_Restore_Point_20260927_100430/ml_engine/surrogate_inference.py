"""
Instant Physics Surrogate Predictor Class (Pillar 2)
Loads native XGBoost JSON models for ultra-fast, robust inference.
"""

import os
import sys
import json
import numpy as np
import xgboost as xgb

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

FEATURE_COLS = ["D_mm", "Dc_mm", "H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm"]
TARGET_COLS = ["mass_kg", "rms_sag_nm", "pv_sag_nm", "quilting_nm", "frequency_hz"]

class MirrorSurrogatePredictor:
    def __init__(self, models_dir=None):
        if models_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            models_dir = os.path.join(base_dir, "models")
            
        manifest_path = os.path.join(models_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Surrogate models not found in {models_dir}. Train them first using train_surrogate.py.")
            
        self.features = FEATURE_COLS
        self.targets = TARGET_COLS
        self.boosters = {}
        
        for col in TARGET_COLS:
            model_path = os.path.join(models_dir, f"xgb_{col}.json")
            booster = xgb.Booster()
            booster.load_model(model_path)
            self.boosters[col] = booster

    def predict(self, D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm):
        """
        Evaluate a single mirror design in < 0.5 ms.
        """
        x = np.array([[float(D_mm), float(Dc_mm), float(H_mm), float(tf_mm), float(tw_mm), float(L_mm), float(rf_mm)]], dtype=np.float32)
        dmat = xgb.DMatrix(x, feature_names=self.features)
        
        preds = {col: float(self.boosters[col].predict(dmat)[0]) for col in self.targets}
        
        return {
            "mass_kg": round(preds["mass_kg"], 3),
            "rms_sag_nm": round(preds["rms_sag_nm"], 3),
            "pv_sag_nm": round(preds["pv_sag_nm"], 3),
            "quilting_nm": round(preds["quilting_nm"], 3),
            "frequency_hz": round(preds["frequency_hz"], 1),
            "status": "PASS" if preds["rms_sag_nm"] <= 60.0 and preds["mass_kg"] <= 12.0 and preds["quilting_nm"] <= 30.0 else "REVIEW"
        }

    def predict_batch(self, feature_matrix):
        """
        Vectorized batch evaluation for tens of thousands of designs in milliseconds.
        """
        dmat = xgb.DMatrix(np.asarray(feature_matrix, dtype=np.float32), feature_names=self.features)
        cols = [self.boosters[col].predict(dmat) for col in self.targets]
        return np.column_stack(cols)

if __name__ == "__main__":
    predictor = MirrorSurrogatePredictor()
    res = predictor.predict(D_mm=560.0, Dc_mm=120.0, H_mm=73.7, tf_mm=1.0, tw_mm=3.0, L_mm=55.5, rf_mm=3.0)
    print("\n--- 560mm Benchmark Surrogate Test ---")
    for k, v in res.items():
        print(f"  {k}: {v}")
