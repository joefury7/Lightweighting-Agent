# ml_engine — what is in here now

| File | Role |
|---|---|
| `fea_surrogate.py` | Gaussian-process surrogate trained ONLY on finite-element gravity analyses of the exact NX-journal geometry (`data/fea/*.jsonl`). Predicts RMS / PV / power-removed RMS sag with 1-sigma uncertainty and 37 Fringe Zernike terms. Optional physics prior (smeared-plate qR^4/D*), kept only if it lowers leave-one-out error. |
| `train_fea_surrogate.py` | Model selection + writes the honest prediction-gap report `data/fea/surrogate_validation.json`. |
| `surrogate_inference.py` | Predictor used everywhere: exact mass (cad_engine/exact_mass.py) + FEA surrogate sag; quilting and f1 are labelled analytic estimates. |
| `pinn_inference.py` | Zernike-resolved view of the same surrogate (kept the old class name as an alias for compatibility; there is no PINN any more). |
| `zernike_decomposition.py` | Fringe Zernike basis, least-squares fitting, wavefront reconstruction. |

Removed (see docs/METHODS_AND_VALIDATION.md §5): XGBoost and PINN models trained on a closed-form formula and on
external datasets mapped onto invented geometry, the formula-vs-formula "active learning" residual model, and the
hand-written Zernike "synthesis" template.
