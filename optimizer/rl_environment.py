"""
Opto-Mechanical Mirror Lightweighting Reinforcement Learning Environment (Objective 3)
Custom Gymnasium-compatible environment for training PPO and SAC agents.
Balances mass reduction, optical surface figure error (RMS sag, Zernike), and launch stiffness (f1 >= 120 Hz)
across Zerodur, Silicon Carbide (SiC), ULE, and Beryllium.
"""

import os
import sys
import math
import numpy as np

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.pinn_inference import PINNMirrorPredictor
from ml_engine.train_pinn_surrogate import MATERIALS_PROPERTIES
from cad_engine.cad_generator import TOPOLOGY_CATALOG, MirrorCADGenerator


class OptoMechanicalMirrorEnv:
    """
    Continuous action RL environment for space telescope primary mirror lightweighting.
    State: 15-dimensional continuous state vector
      - Geometry: [D, Dc, H, tf, tw, L, rf]
      - Material properties: [E, rho, nu]
      - Current performance: [mass_kg, rms_sag_nm, pv_sag_nm, quilting_nm, frequency_hz]
    Action: 5-dimensional continuous action in [-1, 1]
      - Perturbations: [dH, d_tf, d_tw, dL, d_rf]
    """
    def __init__(self, D_mm=560.0, Dc_mm=120.0, target_mass_kg=12.0, target_sag_nm=60.0,
                 material="zerodur", topology="triangular_isogrid", max_steps=40,
                 mode="target", fine_tuning=False, initial_geom=None):
        self.D = float(D_mm)
        self.Dc = float(Dc_mm)
        self.target_mass = float(target_mass_kg)
        self.target_sag = float(target_sag_nm)
        self.material = material.lower().strip()
        self.topology = topology.lower().strip()
        self.max_steps = max_steps
        self.current_step = 0
        self.mode = mode.lower().strip() if mode else "target"
        self.fine_tuning = fine_tuning

        self.predictor = PINNMirrorPredictor()

        # Geometric action bounds (delta per step)
        if self.fine_tuning:
            # Fine-tuning scales for local micro-refinement from coarse seed
            # L (cell pitch) is the dominant mass lever — allow ±4mm/step
            # tf, tw ±0.15mm/step, H ±1.5mm/step, rf ±0.3mm/step
            self.step_scales = np.array([1.5, 0.15, 0.15, 4.0, 0.3], dtype=np.float32)
        else:
            self.step_scales = np.array([1.5, 0.15, 0.15, 2.5, 0.25], dtype=np.float32)

        # State bounds
        self.bounds_lower = np.array([45.0, 0.8, 1.5, 25.0, 1.0], dtype=np.float32)  # [H, tf, tw, L, rf]
        self.bounds_upper = np.array([110.0, 4.0, 5.5, 95.0, 5.0], dtype=np.float32)

        self.reset(initial_geom=initial_geom)

    def set_material(self, material):
        self.material = material.lower().strip()
        return self.reset()

    def reset(self, initial_geom=None):
        self.current_step = 0
        if initial_geom is not None:
            self.geom = np.clip(np.array(initial_geom, dtype=np.float32), self.bounds_lower, self.bounds_upper)
        else:
            # Initialize with nominal flight baseline parameters
            self.geom = np.array([75.0, 2.0, 3.0, 55.0, 3.0], dtype=np.float32) # [H, tf, tw, L, rf]
        return self._get_observation()

    def _get_observation(self):
        H, tf, tw, L, rf = self.geom
        mat_props = MATERIALS_PROPERTIES.get(self.material, MATERIALS_PROPERTIES["zerodur"])
        
        preds = self.predictor.predict(
            D_mm=self.D, Dc_mm=self.Dc, H_mm=H, tf_mm=tf, tw_mm=tw, L_mm=L, rf_mm=rf,
            material=self.material, topology=self.topology
        )

        self.last_preds = preds

        # Normalize observation components to roughly [-1, 1]
        obs = np.array([
            (self.D - 560.0) / 100.0,
            (self.Dc - 120.0) / 50.0,
            (H - 75.0) / 25.0,
            (tf - 2.0) / 1.0,
            (tw - 3.0) / 1.0,
            (L - 55.0) / 20.0,
            (rf - 3.0) / 1.5,
            (mat_props["E"] - 150.0) / 150.0,
            (mat_props["rho"] - 2500.0) / 1000.0,
            (mat_props["nu"] - 0.2) / 0.1,
            (preds["mass_kg"] - self.target_mass) / 5.0,
            (preds["rms_sag_nm"] - self.target_sag) / 30.0,
            (preds["pv_sag_nm"] - 150.0) / 100.0,
            (preds["quilting_nm"] - 20.0) / 20.0,
            (preds["frequency_hz"] - 200.0) / 150.0
        ], dtype=np.float32)

        return obs

    def step(self, action):
        """
        Executes one RL step with the continuous action vector.
        """
        self.current_step += 1
        act = np.clip(action, -1.0, 1.0) * self.step_scales
        self.geom = np.clip(self.geom + act, self.bounds_lower, self.bounds_upper)

        H, tf, tw, L, rf = self.geom
        preds = self.predictor.predict(
            D_mm=self.D, Dc_mm=self.Dc, H_mm=H, tf_mm=tf, tw_mm=tw, L_mm=L, rf_mm=rf,
            material=self.material, topology=self.topology
        )
        self.last_preds = preds

        mass = preds["mass_kg"]
        rms_sag = preds["rms_sag_nm"]
        quilt = preds["quilting_nm"]
        freq = preds["frequency_hz"]
        lw_pct = preds["lightweight_pct"]

        # -------------------------------------------------------------
        # Opto-Mechanical Multi-Objective Reward Function
        # -------------------------------------------------------------
        # 1. Mass Reduction / Tracking Reward
        if self.mode == "target":
            mass_err = abs(mass - self.target_mass)
            # Strong gradient: -20× per kg off target so the agent always moves toward target
            r_mass = -20.0 * mass_err
            if mass_err <= 0.02:
                r_mass += 50.0   # Exact sub-decimal target match bonus!
            elif mass_err <= 0.1:
                r_mass += 25.0
            elif mass_err <= 0.5:
                r_mass += 5.0
        else:
            r_mass = -1.2 * max(0.0, mass - self.target_mass) + (0.05 * lw_pct)

        # 2. Optical Surface Figure Error Penalty (RMS Sag <= target_sag)
        c_sag = max(0.0, rms_sag - self.target_sag)
        r_sag = -0.6 * c_sag

        # 3. Polishing Quilting Deflection Penalty (Quilting <= 30 nm)
        c_quilt = max(0.0, quilt - 30.0)
        r_quilt = -0.3 * c_quilt

        # 4. Launch Dynamic Stiffness Constraint (Launch frequency f1 >= 120 Hz)
        c_freq = max(0.0, 120.0 - freq)
        r_freq = -0.8 * c_freq

        # 5. NASA CR-124075 Thin-Wall Manufacturing Penalties
        r_mfg = 0.0
        if tf < 0.8:
            r_mfg -= 10.0 * (0.8 - tf)
        if tw < 1.5:
            r_mfg -= 10.0 * (1.5 - tw)

        # 6. Flight Mission Milestone Bonus (Mass Target Met AND Sag <= 60nm AND f1 >= 120Hz)
        if self.mode == "target":
            all_passed = (abs(mass - self.target_mass) <= 0.15) and (rms_sag <= self.target_sag) and (quilt <= 30.0) and (freq >= 120.0)
        else:
            all_passed = (mass <= self.target_mass) and (rms_sag <= self.target_sag) and (quilt <= 30.0) and (freq >= 120.0)
        bonus = 15.0 if all_passed else 0.0

        reward = float(r_mass + r_sag + r_quilt + r_freq + r_mfg + bonus)

        done = bool(self.current_step >= self.max_steps or (all_passed and lw_pct >= 75.0))
        obs = self._get_observation()

        info = {
            "mass_kg": mass,
            "rms_sag_nm": rms_sag,
            "quilting_nm": quilt,
            "frequency_hz": freq,
            "lightweight_pct": lw_pct,
            "all_passed": all_passed,
            "H_mm": round(float(H), 2),
            "tf_mm": round(float(tf), 2),
            "tw_mm": round(float(tw), 2),
            "L_mm": round(float(L), 2),
            "rf_mm": round(float(rf), 2),
            "material": self.material,
            "topology": self.topology
        }

        return obs, reward, done, info


if __name__ == "__main__":
    print("Testing OptoMechanicalMirrorEnv...")
    env = OptoMechanicalMirrorEnv(material="zerodur")
    obs = env.reset()
    print(f"Initial State Observation shape: {obs.shape}")
    obs, r, done, info = env.step(np.array([0.5, -0.2, -0.1, 0.4, 0.0]))
    print(f"Step Result -> Reward: {r:.2f} | Mass: {info['mass_kg']} kg | Sag: {info['rms_sag_nm']} nm | f1: {info['frequency_hz']} Hz")
