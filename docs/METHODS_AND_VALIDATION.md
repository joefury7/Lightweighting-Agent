# Methods and validation (rewritten 18 Nov 2026)

This replaces the earlier pipeline. The old pipeline's mass came from fitted "packing factors", its "NASTRAN" check was a closed-form formula, and its surrogates were trained on that formula plus external datasets mapped onto invented geometry. Every number the app now shows is in one of three categories, and the UI labels which one:

| Quantity | Source | Status |
|---|---|---|
| Mass, volume, pocket count | Exact geometry of the NX journal | Identical to the NX part when every pocket cuts |
| RMS / PV gravity sag, 37 Zernike terms | Gaussian-process surrogate trained only on finite-element analyses of the exact geometry | Leave-one-out error reported in `data/fea/surrogate_validation.json` |
| Verification FEA | NX Nastran SOL 101 (if installed) or CalculiX, on the exact geometry | Genuine FEA, 1–3 min per design |
| Quilting, natural frequency | Textbook formulas (Yoder Eq. 2.35; Leissa free plate) | Labelled "analytic estimate" |

## 1. Mass: one geometry definition

The NX part is built by the journal that `app.js → generateNXCode()` writes. Mass is computed from that same geometry:

* `cad_engine/journal_replica.py` executes the journal text against a stand-in for the NXOpen API and records every operation:
  * the conic blank revolve,
  * every pocket extrude (polygon and height),
  * the outer and inner 5 mm wall-restore revolves.

  Volume = blank − Σ (pocket footprint ∩ cut annulus) × pocket height, computed with exact polygon–circle intersection.
* `cad_engine/exact_mass.py` (Python) and `calculateExactIsogridMass` in `app.js` (browser) are line-by-line ports of the journal's isogrid loop. They include:
  * the journal's 0.1 mm rounding of every parameter (`toFixed(1)`),
  * the chamfered corners (`n_sub = 1`),
  * the adaptive pocket height,
  * the extrude height rounded to 0.001 mm (`str(round(h, 3))`),
  * the restored wall rings.

**Validation**
* Replica vs a full OpenCascade B-rep solid (blank, 144–186 boolean pocket cuts, ring fuses): differences of 1e-8 % for the isogrid, radial, hex-radial and double-arch patterns.
* Python vs JavaScript vs replica on 25 random designs: worst difference 0.0000 g (`validation/test_exact_mass.py`).
* Design unchanged: the original and the modified `app.js` generate identical pocket geometry for all 8 patterns (`validation/test_design_unchanged.py <old app.js>`).

**NX check (do this once):** build any design with the app's Create 3D Part, or play the journal in NX. The journal now writes `nx_mass_report.json` next to the .prt with NX's own measured volume, the mass, and the centres of any pockets NX failed to cut. The NX listing window prints `NX measured mass | app predicted | difference`.

If NX fails to cut a pocket (a boolean failure), the NX mass is higher than the app's by that pocket's volume, and the report says which pocket. That is a CAD failure, not a prediction error.

## 2. FEA of the exact geometry (`fea_engine/mirror_fea.py`)

* **Geometry:** OpenCascade via gmsh, built from the recorded journal operations.
* **Symmetry:** the journal's lattice puts a rib midpoint at the origin, so the pocket layout is mirror-symmetric about X and Y. The 18 Hindle hubs are 6-fold symmetric. A quarter model with two symmetry planes is therefore exact for axial gravity.
* **Mesh:** 10-node tetrahedra (C3D10 / NX CTETRA10). Element size 8 mm with 1.2 mm refinement around each support pad.
* **Loads and supports:** 1 g along the optical axis. The 18 Hindle pads (radius = HUB_OUTER_R = 6 mm on the back face, hub positions identical to the journal's) are fixed axially.
* **Solver:** CalculiX 2.21 (SPOOLES; iterative Cholesky above 200k nodes). The same model is written as a Nastran bulk-data deck (`write_bdf`) and solved with NX Nastran when `nastran.exe` is found.
* **Optics:** normal surface displacement is mirrored to the full aperture and resampled on a uniform grid. Reported values:
  * RMS and PV with piston and tilt removed,
  * RMS with power removed,
  * 37 Fringe Zernike terms fitted by least squares.

**Validation**
* Closed-form check, simply supported circular plate under self-weight (Timoshenko): FE error is +0.17 % at 6 mm mesh and −0.004 % at 3 mm (h = 6 mm). It is −0.02 % for h = 1.5 mm at aspect ratio 4. See `validation/fea_analytic_benchmark.py`.
* Equilibrium: support reaction = weight to 6 significant figures in every run (stored per record).
* The Nastran deck is parsed by pyNastran without errors. Its FE mass agrees with the exact geometry to 0.06 % (coarse 14 mm mesh).
* Mesh convergence (pads refined), app default design: 8 mm → 11.23 nm, 6 mm → 11.45 nm (2 %). Current .prt design: 8 mm → 1.53 nm, 6 mm → 1.58 nm (3 %). The dataset uses 8 mm. Mesh-6 reruns are kept in `data/fea/convergence_mesh6.jsonl`.

## 3. Surrogate (`ml_engine/fea_surrogate.py`)

* **Training data:** `data/fea/isogrid_fea_dataset.jsonl` (CalculiX) and `data/fea/nx_nastran_results.jsonl` (NX Nastran, which takes precedence). Every record holds the design parameters, exact mass, solver, mesh, the reaction check, RMS/PV/power-removed RMS and 37 Zernike terms.
* **Design of experiments:** scrambled Sobol samples over tf 0.8–3.5, tw 1.5–5.5, L 38–92, rf 1–min(10, 0.45 r_in), H 55–95 mm, with D = 560 mm, Dc = 175 mm, R = 1085 mm, k = −1.22. Plus 4 named designs (the current .prt and earlier journals).
* **Model:** Gaussian process (Matern 5/2, ARD, white noise) on log-sag. Optionally it uses a physics prior and learns log(FEA / smeared-plate qR⁴/D*); the prior is kept only if it lowers the leave-one-out error. The Zernike shape (z/RMS) is learned by a second GP.
* **Materials:** gravity deflection of a fixed geometry scales with ρ/E; Poisson's ratio has a small residual effect.
* **Validity:** predictions outside the sampled domain, or for non-isogrid patterns, are flagged and not silently extrapolated.
* **Prediction gap:** `python ml_engine/train_fea_surrogate.py` writes the leave-one-out table to `data/fea/surrogate_validation.json`.
* **Active learning:** every genuine FEA run (`/fea/solve`) is appended to the dataset and the GP is refitted.

## 4. Getting NX Nastran truth into the loop

1. If NX Nastran is installed (`C:\Program Files\Siemens\NX2007\NXNASTRAN\bin\nastran.exe`, or set `NX_NASTRAN_EXE`), `/fea/solve` solves the quarter-model deck with NX Nastran automatically. Results go to `nx_nastran_results.jsonl`, which overrides CalculiX for the same design.
2. To compare with your own NX Simcenter study of the .prt, use the same boundary conditions:
   * gravity 1 g along −Z (optical axis), face up,
   * axial (Z) constraint on 6 mm-radius pads at the 18 hub points (listed in every optimisation result as `support_hubs_18`),
   * in-plane kinematic restraint only (no over-constraint),
   * Zerodur E = 90.3 GPa, ν = 0.24, ρ = 2530 kg/m³.

   Report surface RMS after piston and tilt removal.

## 5. What was removed and why

| Removed | Reason |
|---|---|
| `nx_fea_analysis_agent.run_fea_solve` formula labelled "NASTRAN SOL 101 CONVERGED" | Not FEA |
| `optimizer/retraining_buffer.json`, `ml_engine/active_learner.py` | The "FEA" values were that formula; active learning learned the ratio of two constants |
| XGBoost models, `train_surrogate.py` | Trained only on the synthetic formula dataset |
| PINN weights, `train_pinn_surrogate.py`, `data_loaders.py` | External data mapped onto invented geometry (an angle used as thickness, one fixed fake geometry for all Rubin rows); sag correlation with physics −0.18 |
| `synthesize_37_zernike_coefficients` | Hand-written fixed-ratio Zernike template |
| `sac_agent.py` | No training code existed |
| `cad_engine/cad_generator.py` | A second, different design generator (flat cylinder blank, packing-factor masses) |
| `audit_all_objectives.py` | 24 literature gaps hard-coded as "RESOLVED"; the Parseval check passed by construction |
| `create_3d_prt` journal "sanitize" patch, circular-pocket fallback journal | They changed the design NX built |
| UI fallback numbers (11.7 kg, 54 nm, 58.11 nm, "FEA Pass ✅"), "forced target mass" display | Displayed values that were not computed |

The external datasets in `data_new/` are kept. They are genuine downloads, but none describes this mirror's geometry, so none is used for training. Three of them are used for verification only (section 7).

## 6. Running everything

```
pip install -r requirements.txt          # gmsh, scikit-learn, scipy, shapely, fastapi, torch ...
# CalculiX: needed only if NX Nastran is unavailable (Windows build, or FreeCAD's ccx.exe; set CCX_EXE)
python fea_engine/generate_fea_dataset.py 8      # extend the FEA dataset (resumable)
python ml_engine/train_fea_surrogate.py          # model selection + prediction-gap report
python optimizer/ppo_agent.py                    # retrain PPO on the current evaluator (optional)
python validation/run_validation.py              # all checks
python validation/jwst_measured_wfe.py           # external data checks (section 7)
python validation/rubin_m1m3_gravity_optics.py
python validation/nah_plate_modal_benchmark.py 12
start_server.bat
```

## 7. Verification against authentic third-party data

None of these datasets trains a model or changes a result. See `data/external_validation/README.md` for details, caveats and paper wording.

| Data | Kind | Check | Result |
|---|---|---|---|
| JWST wavefront-sensing OPD maps (STScI/MAST) | measured in flight | RMS WFE and Zernike decomposition vs STScI `RMS_WFE` | within 0.005 % on 6 maps |
| Rubin Observatory M1M3 gravity FEA (Zenodo 8384326) | observatory FEA of a honeycomb mirror | PTT/power removal and RMS vs Rubin reference code | identical (2e-14 %) |
| COMSOL plate eigenfrequencies (Olivieri et al. 2021, Zenodo 5702615) | independent solver | gmsh + C3D10 + CalculiX chain | 230 modes, median 0.18 %, max 1.19 % |
