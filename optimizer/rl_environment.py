"""
Mirror lightweighting RL environment (Objective 3).

State (15): normalised geometry (D, Dc, H, tf, tw, L, rf), material (E, rho, nu) and current
performance (mass, RMS sag, PV sag, quilting, f1).  Action (5): bounded steps on (H, tf, tw, L, rf).
Rewards use the SAME evaluator as NSGA-II: exact NX-journal mass + FEA-trained sag surrogate
(the old environment used a broken neural network that predicted ~1 nm sag for real 90 nm designs).
"""
import os
import sys
import numpy as np

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from ml_engine.surrogate_inference import MirrorSurrogatePredictor  # noqa: E402
from ml_engine.fea_surrogate import BOUNDS, MATERIALS  # noqa: E402
from optimizer.closed_loop_optimizer import max_fillet  # noqa: E402

MAX_QUILT_NM = 30.0


class OptoMechanicalMirrorEnv:
    def __init__(self, D_mm=560.0, Dc_mm=175.0, target_mass_kg=12.0, target_sag_nm=60.0,
                 material="zerodur", topology="triangular_isogrid", max_steps=40,
                 mode="target", fine_tuning=False, initial_geom=None, seed=None):
        if topology not in ("triangular_isogrid", "isogrid"):
            raise ValueError("Only the triangular isogrid has FEA training data")
        self.D, self.Dc = float(D_mm), float(Dc_mm)
        self.target_mass, self.target_sag = float(target_mass_kg), float(target_sag_nm)
        self.material, self.topology = material.lower(), topology
        self.max_steps, self.mode, self.fine_tuning = max_steps, (mode or "target").lower(), fine_tuning
        self.predictor = MirrorSurrogatePredictor()
        self.rng = np.random.default_rng(seed)
        self.lo = np.array([BOUNDS["depth"][0], BOUNDS["faceplate"][0], BOUNDS["ribThick"][0], BOUNDS["cellSize"][0], BOUNDS["filletRadius"][0]])
        self.hi = np.array([BOUNDS["depth"][1], BOUNDS["faceplate"][1], BOUNDS["ribThick"][1], BOUNDS["cellSize"][1], BOUNDS["filletRadius"][1]])
        if initial_geom is not None:
            self.lo[0] = self.hi[0] = float(initial_geom[0])
        self.step_scales = np.array([0.0 if initial_geom is not None else 1.5, 0.1, 0.1, 1.5, 0.2] if fine_tuning
                                    else [0.0 if initial_geom is not None else 2.5, 0.2, 0.25, 3.0, 0.4])
        self.initial_geom = initial_geom
        self.reset(initial_geom=initial_geom)

    def _clip(self, g):
        g = np.clip(g, self.lo, self.hi)
        g[4] = min(g[4], max(self.lo[4], max_fillet(g[3], g[2])))
        return np.round(g, 1)

    def reset(self, initial_geom=None):
        self.current_step = 0
        if initial_geom is not None:
            self.geom = self._clip(np.array(initial_geom, float))
        else:
            self.geom = self._clip(self.lo + self.rng.random(5) * (self.hi - self.lo))
        return self._obs()

    def _eval(self):
        H, tf, tw, L, rf = self.geom
        p = self.predictor.predict(self.D, self.Dc, H, tf, tw, L, rf, material=self.material)
        self.last_preds = p
        return p

    def _obs(self):
        p = self._eval()
        m = MATERIALS[self.material]
        H, tf, tw, L, rf = self.geom
        return np.array([(self.D - 560) / 100, (self.Dc - 175) / 50, (H - 75) / 20, (tf - 2) / 1, (tw - 3.5) / 1.2,
                         (L - 65) / 15, (rf - 4) / 2.5, (m["E"] / 1e9 - 150) / 150, (m["rho"] - 2500) / 1000,
                         (m["nu"] - 0.2) / 0.1, (p["mass_kg"] - self.target_mass) / 5,
                         (p["rms_sag_nm"] - self.target_sag) / 30, (p["pv_sag_nm"] - 150) / 100,
                         (p["quilting_nm"] - 20) / 20, (p["frequency_hz"] - 800) / 500], dtype=np.float32)

    def score(self, p):
        """Lower is better. Same priorities as NSGA-II: constraints, then mass (target/min), then sag."""
        viol = max(0.0, p["rms_sag_nm"] - self.target_sag) / self.target_sag + max(0.0, p["quilting_nm"] - MAX_QUILT_NM) / MAX_QUILT_NM
        mass_term = abs(p["mass_kg"] - self.target_mass) if self.mode == "target" else p["mass_kg"]
        return 100.0 * viol + mass_term / 0.05 + 0.5 * p["rms_sag_nm"] / self.target_sag

    def step(self, action):
        self.current_step += 1
        before = self.score(self.last_preds)
        self.geom = self._clip(self.geom + np.clip(action, -1, 1) * self.step_scales)
        obs = self._obs()
        p = self.last_preds
        after = self.score(p)
        reward = float(before - after)          # improvement of the shared objective
        all_passed = p["rms_sag_nm"] <= self.target_sag and p["quilting_nm"] <= MAX_QUILT_NM and \
            (abs(p["mass_kg"] - self.target_mass) <= 0.1 if self.mode == "target" else p["mass_kg"] <= self.target_mass)
        done = self.current_step >= self.max_steps
        H, tf, tw, L, rf = self.geom
        info = {"mass_kg": p["mass_kg"], "rms_sag_nm": p["rms_sag_nm"], "pv_sag_nm": p["pv_sag_nm"],
                "quilting_nm": p["quilting_nm"], "frequency_hz": p["frequency_hz"],
                "lightweight_pct": p["lightweight_pct"], "all_passed": all_passed, "score": after,
                "H_mm": float(H), "tf_mm": float(tf), "tw_mm": float(tw), "L_mm": float(L), "rf_mm": float(rf),
                "material": self.material, "topology": self.topology}
        return obs, reward, done, info
