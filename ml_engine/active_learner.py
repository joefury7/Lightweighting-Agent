"""
Active Learning Residual Engine (Pillar 2 & 3 Integration)
Learns from Siemens NX / NASTRAN FEA ground-truth residuals stored in retraining_buffer.json.
Provides online closed-loop calibration for ML surrogate predictions.
"""

import os
import sys
import json
import numpy as np
from sklearn.linear_model import Ridge

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

class ActiveLearningCompensator:
    def __init__(self, buffer_file=None, model_file=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if buffer_file is None:
            buffer_file = os.path.join(os.path.dirname(base_dir), "optimizer", "retraining_buffer.json")
        if model_file is None:
            model_file = os.path.join(base_dir, "models", "active_learning_residual.json")
            
        self.buffer_file = buffer_file
        self.model_file = model_file
        self.is_trained = False
        self.feature_names = ["D_mm", "Dc_mm", "H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm"]
        self.coef = np.zeros(len(self.feature_names))
        self.intercept = 0.0
        self.sample_count = 0
        self.rmse_before = 0.0
        self.rmse_after = 0.0
        self.mape_before = 0.0
        self.mape_after = 0.0
        
        # Load existing model if available, else train from buffer
        if os.path.exists(self.model_file):
            self._load_model()
        elif os.path.exists(self.buffer_file):
            self.train_from_buffer()

    def train_from_buffer(self):
        """
        Reads retraining_buffer.json, filters valid optical FEA runs, and trains
        a regularized residual compensation model Delta(X) = FEA_sag - ML_sag.
        """
        if not os.path.exists(self.buffer_file):
            return False
            
        try:
            with open(self.buffer_file, "r") as f:
                buffer = json.load(f)
        except Exception:
            return False
            
        X = []
        y_residual = []
        y_ml = []
        y_fea = []

        for e in buffer:
            p = e.get("params", {})
            ml_sag = float(e.get("ml_pred_sag_nm", 0))
            fea_sag = float(e.get("fea_actual_sag_nm", 0))
            
            # Optical regime filter: practical mirrors with deflection < 300 nm
            if ml_sag > 0 and fea_sag > 0 and fea_sag < 300.0:
                feat = [
                    float(p.get("D_mm", 560.0)),
                    float(p.get("Dc_mm", 120.0)),
                    float(p.get("H_mm", 73.7)),
                    float(p.get("tf_mm", 1.0)),
                    float(p.get("tw_mm", 3.0)),
                    float(p.get("L_mm", 55.5)),
                    float(p.get("rf_mm", 3.0))
                ]
                X.append(feat)
                y_residual.append(fea_sag - ml_sag)
                y_ml.append(ml_sag)
                y_fea.append(fea_sag)

        if len(X) < 3:
            # Need at least 3 points for meaningful fit
            return False

        X_arr = np.array(X, dtype=np.float64)
        y_res_arr = np.array(y_residual, dtype=np.float64)
        y_ml_arr = np.array(y_ml, dtype=np.float64)
        y_fea_arr = np.array(y_fea, dtype=np.float64)

        # Baseline errors before active learning
        self.rmse_before = float(np.sqrt(np.mean((y_fea_arr - y_ml_arr) ** 2)))
        self.mape_before = float(np.mean(np.abs((y_fea_arr - y_ml_arr) / y_fea_arr)) * 100.0)

        # Fit Ridge regression with regularization to avoid overfitting on small N
        model = Ridge(alpha=15.0, fit_intercept=True)
        model.fit(X_arr, y_res_arr)

        self.coef = model.coef_
        self.intercept = float(model.intercept_)
        self.sample_count = len(X)
        self.is_trained = True

        # Errors after active learning
        preds_res = model.predict(X_arr)
        preds_corrected = y_ml_arr + preds_res
        self.rmse_after = float(np.sqrt(np.mean((y_fea_arr - preds_corrected) ** 2)))
        self.mape_after = float(np.mean(np.abs((y_fea_arr - preds_corrected) / y_fea_arr)) * 100.0)

        self._save_model()
        print(f"[Active Learning] Retrained on {self.sample_count} FEA runs: RMSE {self.rmse_before:.2f}nm -> {self.rmse_after:.2f}nm (MAPE {self.mape_before:.1f}% -> {self.mape_after:.1f}%)")
        return True

    def _save_model(self):
        os.makedirs(os.path.dirname(self.model_file), exist_ok=True)
        data = {
            "is_trained": self.is_trained,
            "sample_count": self.sample_count,
            "feature_names": self.feature_names,
            "coef": [float(c) for c in self.coef],
            "intercept": float(self.intercept),
            "rmse_before_nm": round(self.rmse_before, 3),
            "rmse_after_nm": round(self.rmse_after, 3),
            "mape_before_pct": round(self.mape_before, 2),
            "mape_after_pct": round(self.mape_after, 2)
        }
        with open(self.model_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_model(self):
        try:
            with open(self.model_file, "r") as f:
                data = json.load(f)
            self.is_trained = data.get("is_trained", False)
            self.sample_count = data.get("sample_count", 0)
            self.coef = np.array(data.get("coef", np.zeros(7)), dtype=np.float64)
            self.intercept = float(data.get("intercept", 0.0))
            self.rmse_before = float(data.get("rmse_before_nm", 0.0))
            self.rmse_after = float(data.get("rmse_after_nm", 0.0))
            self.mape_before = float(data.get("mape_before_pct", 0.0))
            self.mape_after = float(data.get("mape_after_pct", 0.0))
        except Exception:
            self.is_trained = False

    def predict_residual(self, D_mm, Dc_mm, H_mm, tf_mm, tw_mm, L_mm, rf_mm):
        """Predicts Delta = FEA_sag - ML_sag (in nm)."""
        if not self.is_trained:
            return 0.0
        x = np.array([float(D_mm), float(Dc_mm), float(H_mm), float(tf_mm), float(tw_mm), float(L_mm), float(rf_mm)], dtype=np.float64)
        return float(np.dot(self.coef, x) + self.intercept)

    def predict_residual_batch(self, feature_matrix):
        """Vectorized prediction of Delta = FEA_sag - ML_sag for N candidate designs."""
        if not self.is_trained:
            return np.zeros(feature_matrix.shape[0], dtype=np.float32)
        fm = np.asarray(feature_matrix, dtype=np.float64)
        return (np.dot(fm, self.coef) + self.intercept).astype(np.float32)

    def get_status(self):
        return {
            "active_learning_enabled": self.is_trained,
            "sample_count": self.sample_count,
            "rmse_before_nm": self.rmse_before,
            "rmse_after_nm": self.rmse_after,
            "error_reduction_pct": round(((self.mape_before - self.mape_after) / max(0.01, self.mape_before)) * 100.0, 1) if self.mape_before > 0 else 0.0,
            "mape_before_pct": self.mape_before,
            "mape_after_pct": self.mape_after
        }

if __name__ == "__main__":
    al = ActiveLearningCompensator()
    print("Active Learning Status:", al.get_status())
    res = al.predict_residual(560.0, 120.0, 73.7, 1.0, 3.0, 55.5, 3.0)
    print(f"Predicted FEA correction at benchmark (560, 120, 73.7, 1, 3, 55.5, 3): {res:+.2f} nm")
