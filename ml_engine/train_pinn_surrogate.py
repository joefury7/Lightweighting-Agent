"""
Physics-Informed Neural Network (PINN) Multi-Head Surrogate Trainer (Objective 2)
Predicts [mass, rms_sag, pv_sag, quilting, f1] AND 37-Term Fringe Zernike Coefficients
Across Zerodur, SiC, ULE, and Beryllium with integrated 18-point whiffletree physics.
"""

import os
import sys
import math
import time
import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.zernike_decomposition import synthesize_37_zernike_coefficients
from cad_engine.cad_generator import TOPOLOGY_CATALOG

MATERIALS_PROPERTIES = {
    "zerodur": {"E": 90.3, "rho": 2530.0, "nu": 0.24},
    "sic": {"E": 420.0, "rho": 3160.0, "nu": 0.14},
    "ule": {"E": 67.6, "rho": 2210.0, "nu": 0.17},
    "beryllium": {"E": 303.0, "rho": 1850.0, "nu": 0.08},
    "fused_silica": {"E": 72.7, "rho": 2200.0, "nu": 0.17}
}

SCALAR_TARGETS = ["mass_kg", "rms_sag_nm", "pv_sag_nm", "quilting_nm", "frequency_hz"]


class ResidualBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.fc1 = nn.Linear(dim, dim)
        self.ln1 = nn.LayerNorm(dim)
        self.act1 = nn.SiLU()
        self.fc2 = nn.Linear(dim, dim)
        self.ln2 = nn.LayerNorm(dim)
        self.act2 = nn.SiLU()

    def forward(self, x):
        res = x
        x = self.act1(self.ln1(self.fc1(x)))
        x = self.act2(self.ln2(self.fc2(x)))
        return x + res


class PhysicsInformedMirrorSurrogate(nn.Module):
    """
    Multi-Head Physics-Informed Neural Network (PINN) for Spaceborne Mirror Lightweighting.
    Input Dimension: 18
      - 7 continuous geometric parameters (D, Dc, H, tf, tw, L, rf)
      - 3 continuous material properties (E_GPa, rho_kg_m3, nu)
      - 8 one-hot topology categories
    Output Heads:
      - Head 1 (Scalar Mechanical): 5 outputs [mass_kg, rms_sag_nm, pv_sag_nm, quilting_nm, f1_hz]
      - Head 2 (Optical Wavefront): 37 outputs [Z_1, ..., Z_37] (Fringe Zernike coefficients)
    """
    def __init__(self, in_features=18, hidden_dim=256):
        super().__init__()
        self.in_features = in_features

        # Shared Feature Extractor Backbone
        self.input_layer = nn.Sequential(
            nn.Linear(in_features, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU()
        )
        self.res1 = ResidualBlock(hidden_dim)
        self.res2 = ResidualBlock(hidden_dim)

        # Head 1: Scalar Optomechanical Properties
        self.scalar_head = nn.Sequential(
            nn.Linear(hidden_dim, 128),
            nn.SiLU(),
            nn.Linear(128, len(SCALAR_TARGETS))
        )

        # Head 2: 37-Term Fringe Zernike Wavefront Spectrum
        self.zernike_head = nn.Sequential(
            nn.Linear(hidden_dim, 128),
            nn.SiLU(),
            nn.Linear(128, 37)
        )

    def forward(self, x):
        feat = self.input_layer(x)
        feat = self.res1(feat)
        feat = self.res2(feat)
        scalars = self.scalar_head(feat)
        zernike = self.zernike_head(feat)
        return scalars, zernike


def compute_r2(y_true, y_pred):
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true, axis=0)) ** 2)
    return float(1.0 - (ss_res / (ss_tot + 1e-9)))


def build_training_tensors(data_csv="data/multi_material_mirror_dataset_25k.csv", num_samples=15000):
    print(f"[PINN Data Loader] Loading dataset from '{data_csv}'...")
    if not os.path.exists(data_csv):
        raise FileNotFoundError(f"Dataset not found at {data_csv}")

    df = pd.read_csv(data_csv, nrows=num_samples)
    print(f"[PINN Data Loader] Loaded {len(df):,} samples. Synthesizing 37 Fringe Zernike ground truths...")

    # Geometric Features (7)
    geom_cols = ["D_mm", "Dc_mm", "H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm"]
    geom_matrix = df[geom_cols].values.astype(np.float32)

    # Material Properties (3)
    mat_cols = ["Youngs_Modulus_GPa", "Density_kg_m3", "Poisson_Ratio"]
    mat_matrix = df[mat_cols].values.astype(np.float32)

    # Topology One-Hot Encoding (8)
    # Default distribution among TOPOLOGY_CATALOG if not explicitly columnized
    num_rows = len(df)
    if "Topology" in df.columns:
        top_indices = [TOPOLOGY_CATALOG.index(t) if t in TOPOLOGY_CATALOG else 0 for t in df["Topology"]]
    else:
        # Uniformly distribute across 8 topologies
        top_indices = np.random.randint(0, len(TOPOLOGY_CATALOG), size=num_rows)

    top_one_hot = np.zeros((num_rows, len(TOPOLOGY_CATALOG)), dtype=np.float32)
    top_one_hot[np.arange(num_rows), top_indices] = 1.0

    X_all = np.column_stack([geom_matrix, mat_matrix, top_one_hot]).astype(np.float32)

    # Scalar Targets (5)
    y_scalar_all = df[SCALAR_TARGETS].values.astype(np.float32)

    # Optical Wavefront Targets (37 Zernike coefficients)
    rms_sags = df["rms_sag_nm"].values
    quilts = df["quilting_nm"].values
    zernike_all = np.zeros((num_rows, 37), dtype=np.float32)

    for i in range(num_rows):
        top_str = TOPOLOGY_CATALOG[top_indices[i]]
        zernike_all[i] = synthesize_37_zernike_coefficients(
            rms_sag_nm=rms_sags[i], quilting_nm=quilts[i], topology=top_str
        )

    # Compute normalization parameters (Mean and Std)
    x_mean = np.mean(X_all, axis=0)
    x_std = np.std(X_all, axis=0) + 1e-6
    y_scalar_mean = np.mean(y_scalar_all, axis=0)
    y_scalar_std = np.std(y_scalar_all, axis=0) + 1e-6
    z_std = np.std(zernike_all, axis=0) + 1e-6

    norm_stats = {
        "x_mean": x_mean.tolist(),
        "x_std": x_std.tolist(),
        "y_scalar_mean": y_scalar_mean.tolist(),
        "y_scalar_std": y_scalar_std.tolist(),
        "z_std": z_std.tolist()
    }

    # Normalize data
    X_norm = (X_all - x_mean) / x_std
    y_scalar_norm = (y_scalar_all - y_scalar_mean) / y_scalar_std
    zernike_norm = zernike_all / z_std

    return X_norm, y_scalar_norm, zernike_norm, norm_stats, (X_all, y_scalar_all, zernike_all)


def train_pinn_model(epochs=35, batch_size=128, lr=1e-3, num_samples=15000,
                     save_dir="ml_engine/models"):
    os.makedirs(save_dir, exist_ok=True)
    device = torch.device("cpu")
    print(f"\n[PINN Trainer] Initializing PyTorch Physics-Informed Training on {device}...")

    X_norm, y_scal_norm, z_norm, norm_stats, (X_raw, y_scal_raw, z_raw) = build_training_tensors(num_samples=num_samples)

    # Train/Validation Split (85% / 15%)
    n = len(X_norm)
    split = int(0.85 * n)
    indices = np.random.permutation(n)
    tr_idx, val_idx = indices[:split], indices[split:]

    train_dataset = TensorDataset(
        torch.tensor(X_norm[tr_idx], dtype=torch.float32),
        torch.tensor(y_scal_norm[tr_idx], dtype=torch.float32),
        torch.tensor(z_norm[tr_idx], dtype=torch.float32),
        torch.tensor(y_scal_raw[tr_idx], dtype=torch.float32)  # For unnormalized physics loss
    )
    val_dataset = TensorDataset(
        torch.tensor(X_norm[val_idx], dtype=torch.float32),
        torch.tensor(y_scal_norm[val_idx], dtype=torch.float32),
        torch.tensor(z_norm[val_idx], dtype=torch.float32),
        torch.tensor(y_scal_raw[val_idx], dtype=torch.float32)
    )

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    model = PhysicsInformedMirrorSurrogate(in_features=18, hidden_dim=256).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    mse_criterion = nn.MSELoss()

    y_scalar_mean_t = torch.tensor(norm_stats["y_scalar_mean"], dtype=torch.float32)
    y_scalar_std_t = torch.tensor(norm_stats["y_scalar_std"], dtype=torch.float32)
    z_std_t = torch.tensor(norm_stats["z_std"], dtype=torch.float32)

    t0 = time.time()
    for ep in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        train_data_loss = 0.0
        train_physics_loss = 0.0

        for b_x, b_y_scal, b_z, b_raw in train_loader:
            b_x, b_y_scal, b_z = b_x.to(device), b_y_scal.to(device), b_z.to(device)
            optimizer.zero_grad()

            pred_scal, pred_z = model(b_x)

            # Data-driven supervised loss
            loss_scalar = mse_criterion(pred_scal, b_y_scal)
            loss_zernike = mse_criterion(pred_z, b_z)
            data_loss = loss_scalar + loss_zernike

            # Physics-Informed Wavefront Loss (Parseval's Identity: sqrt(sum(Z_j^2)) == RMS_sag)
            # Unnormalize predicted zernike & predicted RMS sag
            pred_z_unnorm = pred_z * z_std_t
            pred_scal_unnorm = pred_scal * y_scalar_std_t + y_scalar_mean_t

            pred_rms_sag = pred_scal_unnorm[:, 1]  # Column 1 is rms_sag_nm
            wavefront_rms_computed = torch.sqrt(torch.sum(pred_z_unnorm[:, 3:]**2, dim=1) + 1e-6)
            loss_parseval = torch.mean((wavefront_rms_computed - pred_rms_sag)**2) / 100.0

            # Combined Loss
            total_loss = data_loss + 0.15 * loss_parseval
            total_loss.backward()
            optimizer.step()

            train_loss += total_loss.item()
            train_data_loss += data_loss.item()
            train_physics_loss += loss_parseval.item()

        scheduler.step()

        if ep % 5 == 0 or ep == epochs:
            # Evaluate Validation Set
            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for v_x, v_y_scal, v_z, _ in val_loader:
                    v_x, v_y_scal, v_z = v_x.to(device), v_y_scal.to(device), v_z.to(device)
                    v_pred_scal, v_pred_z = model(v_x)
                    val_loss += (mse_criterion(v_pred_scal, v_y_scal) + mse_criterion(v_pred_z, v_z)).item()

            avg_train = train_loss / len(train_loader)
            avg_val = val_loss / len(val_loader)
            print(f"  Epoch {ep:02d}/{epochs:02d} | Train Loss: {avg_train:.4f} (Physics: {train_physics_loss/len(train_loader):.4f}) | Val Loss: {avg_val:.4f}")

    train_duration = time.time() - t0
    print(f"\n[PINN Trainer] Training complete in {train_duration:.2f} seconds.")

    # Validation Metrics on Raw Unnormalized Targets
    model.eval()
    with torch.no_grad():
        v_x_all = torch.tensor(X_norm[val_idx], dtype=torch.float32)
        p_scal, p_z = model(v_x_all)
        p_scal_unnorm = (p_scal * y_scalar_std_t + y_scalar_mean_t).numpy()
        p_z_unnorm = (p_z * z_std_t).numpy()

    y_val_true = y_scal_raw[val_idx]
    z_val_true = z_raw[val_idx]

    print("\n" + "="*80)
    print("      OBJECTIVE 2: PINN MULTI-HEAD SURROGATE VALIDATION METRICS")
    print("="*80)
    for i, col in enumerate(SCALAR_TARGETS):
        r2 = compute_r2(y_val_true[:, i], p_scal_unnorm[:, i])
        rmse = float(np.sqrt(np.mean((y_val_true[:, i] - p_scal_unnorm[:, i])**2)))
        mape = float(np.mean(np.abs((y_val_true[:, i] - p_scal_unnorm[:, i]) / (y_val_true[:, i] + 1e-6))) * 100.0)
        print(f"  Target: {col:<18} | R² Score: {r2:.4f} | RMSE: {rmse:<8.3f} | MAPE: {mape:.2f}%")

    zernike_r2 = compute_r2(z_val_true, p_z_unnorm)
    print(f"  Target: {'37 Fringe Zernike':<18} | R² Score: {zernike_r2:.4f} (Across all Z1..Z37 optical modes)")

    # Save Model Weights & Metadata
    model_path = os.path.join(save_dir, "pinn_mirror_surrogate.pt")
    metadata_path = os.path.join(save_dir, "pinn_metadata.json")

    torch.save(model.state_dict(), model_path)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump({
            "model_architecture": "PhysicsInformedMirrorSurrogate (Deep Residual MLP with Dual-Heads)",
            "in_features": 18,
            "scalar_targets": SCALAR_TARGETS,
            "optical_modes": 37,
            "trained_epochs": epochs,
            "training_samples": num_samples,
            "norm_stats": norm_stats,
            "supported_materials": list(MATERIALS_PROPERTIES.keys()),
            "supported_topologies": TOPOLOGY_CATALOG,
            "scalar_r2": {col: float(compute_r2(y_val_true[:, i], p_scal_unnorm[:, i])) for i, col in enumerate(SCALAR_TARGETS)},
            "zernike_r2": float(zernike_r2)
        }, f, indent=2)

    print(f"\n[PINN Trainer SUCCESS] Saved PyTorch weights to {model_path}")
    print(f"[PINN Trainer SUCCESS] Saved metadata to {metadata_path}")
    return model_path


if __name__ == "__main__":
    train_pinn_model(epochs=30, batch_size=128, lr=1e-3, num_samples=15000)
