# data/

## What trains the model

**Only `data/fea/`.** It holds finite-element analyses of the exact NX-journal geometry, run with CalculiX, plus NX Nastran results in `nx_nastran_results.jsonl` when present.
- The Gaussian-process surrogate (`ml_engine/fea_surrogate.py`) is fitted from these files every time it loads.
- No pre-trained model file exists for it.
- The old synthetic datasets (`data/analytic/*`, 10k-25k rows of closed-form formulas), their generator scripts and the old XGBoost/PINN models were deleted in commits `ea86570` and the follow-up.
- Proof: `python validation/prove_training_provenance.py`, results in `data/fea/training_provenance_proof.json`.

| Folder | Content | Role |
|---|---|---|
| `fea/` | 81 FEA runs, mesh convergence, surrogate config and validation | **Training** (the only training data) |
| `external_validation/` | Results of checks against JWST, Rubin and COMSOL data | Verification only, see its README |
| `real/` | Copies of the third-party downloads also in `data_new/` (Rubin, NAH, Harbin, SELTO, MetaXFam, NTRS) | Not used for training. Rubin and NAH are used for verification. |
| `mendeley_mirror_deformation/` | Harbin Mendeley dataset (duplicate of `real/tier2_harbin_mendeley`) | Not used |
| `nasa_reports/`, `material_datasheets/`, `20160007974.pdf` | Reference documents | Literature only |

`data/real/*/provenance.json` files describe where each download came from. Their "role" fields were written for the old pipeline; the table above is current.
