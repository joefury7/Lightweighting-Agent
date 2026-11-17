# ML Engine Training Pipeline & Multi-Fidelity Architecture Notes

## 1. Codebase Audit of `ml_engine/`

1. **Surrogate Model Architectures:**
   - **PINN Dual-Head Surrogate (`ml_engine/train_pinn_surrogate.py`):**
     - Backbone: Deep Residual MLP with LayerNorm, SiLU activations, and skip connections (`ResidualBlock`).
     - Input dimensionality: 18 features (7 geometric continuous: $D, D_c, H, t_f, t_w, L, r_f$; 3 material properties: $E, \rho, \nu$; 8 one-hot pocket topologies).
     - Head 1 (Scalar Optomechanical): 5 targets [`mass_kg`, `rms_sag_nm`, `pv_sag_nm`, `quilting_nm`, `frequency_hz`].
     - Head 2 (Optical Wavefront): 37 outputs corresponding to Fringe Zernike modes $Z_1 \dots Z_{37}$.
     - Loss: Multi-task MSE + Physics-informed Parseval identity loss:
       $$\mathcal{L}_{\text{Parseval}} = \frac{1}{N}\sum \left(\sqrt{\sum_{j=4}^{37} Z_j^2} - \text{RMS}_{\text{sag}}\right)^2$$
   - **Native XGBoost Surrogates (`ml_engine/train_surrogate.py`):**
     - 5 independent Gradient Boosted Trees for scalar optomechanical properties saved as native C++ JSON.
   - **Active Learning Residual Engine (`ml_engine/active_learner.py`):**
     - Ridge regression compensator $\delta(X) = y_{\text{FEA}} - y_{\text{analytic}}$ trained from closed-loop FEA feedback buffer.

2. **Previous Shortcoming (P7 / P8):**
   - The original training script only ingested `data/multi_material_mirror_dataset_25k.csv`, which was generated via Latin Hypercube Sampling over closed-form plate equations (Nelson 18-point, Yoder quilting, NASA SP-8040).
   - Although mathematically rigorous as an analytic baseline, it represented **Fidelity 0** only.
   - Real FEA data from Mendeley and Zenodo was not piped into the training loop, causing the surrogate to learn closed-form simplifications rather than authentic finite element physics.

3. **Multi-Fidelity Solution Implemented:**
   - **Fidelity 0 (Analytic Prior):** Pre-training on 25k multi-material and 20k multi-topology datasets in `data/analytic/`.
   - **Fidelity 1 (Simulation):** SELTO topology optimization, NAH rectangular plate dataset, and MetaXFam metamaterial stiffness.
   - **Fidelity 2 (Real FEA & Optical):** Fine-tuning on Harbin Institute of Technology 37-term Zernike expansion & surface deformation data (2,200 rows x 49 columns, DOI: 10.17632/xpxhpdjgx9.1), Rubin LSST FEA gravity sag node grids (Zenodo: 8384326), and Rubin M1M3 bending modes (Zenodo: 8383823).
   - **Fidelity 3 (Measured Flight):** Held out strictly for validation (`data/real/flight_mirrors.csv` and NASA NTRS JWST reports).
   - **$\delta$-Correction Head:** Fitted on real FEA residual deltas $\delta = y_{\text{FEA}} - y_{\text{analytic}}$, saved to `ml_engine/models/active_learning_residual.json`.
