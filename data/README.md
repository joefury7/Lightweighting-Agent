# Dataset Directory Architecture & Multi-Fidelity Hierarchy

This directory contains the datasets powering the **Parametric Generative CAD & Physics-Informed Neural Surrogate** for spaceborne lightweight mirrors.

In strict compliance with Scientific Integrity Guardrails (G1–G5), all datasets are explicitly tagged by their **fidelity level** and accompanied by provenance metadata. Synthetic or analytic closed-form approximations are never conflated with finite element analysis (FEA) or empirical lab/flight metrology.

---

## 1. Multi-Fidelity Hierarchy

| Fidelity Level | Description | Data Directory | Role in Pipeline |
|---|---|---|---|
| **Fidelity 0: Analytic / Synthetic** | Closed-form optomechanical equations (Nelson 18-point sag, Yoder quilting, NASA SP-8040 flexural rigidity) sampled across Latin Hypercube Design-of-Experiments (DOE). | `data/analytic/` | Cheap, abundant pre-training of PINN & XGBoost surrogate backbones across dense parameter spaces. |
| **Fidelity 1: Open Simulation** | Numerical solver results from open structural/modal physics benchmarks (SELTO topology, NAH plate acoustics/modes, MetaXFam-D stiffness). | `data/real/tier2_selto_topology/`<br>`data/real/tier2_nah_plate/`<br>`data/real/tier2_metaxfam/` | Generalization across complex rib topologies, modal vibration patterns, and effective cellular stiffness. |
| **Fidelity 2: Real FEA & Optical Benchmarks** | High-fidelity FEA simulation grids, 37-term Fringe Zernike wavefront expansions, and telescope structural perturbations. | `data/real/tier2_harbin_mendeley/`<br>`data/real/tier2_rubin_lsst_fea/`<br>`data/real/tier2_rubin_bending_modes/` | Ground-truth fine-tuning of 37-term Zernike optical wavefront head and residual ($\delta$) calibration. |
| **Fidelity 3: Measured Flight Metrology** | Published flight commissioning and lab interferometer metrology from NASA/ESA missions (JWST, HST, Spitzer, Kepler, Herschel, etc.). | `data/real/flight_mirrors.csv`<br>`data/real/tier3_ntrs_jwst/`<br>`data/real/tier2_jwst_opd/` | **Validation and hold-out testing only.** Never mixed into training splits. |

---

## 2. Directory Contents

### `data/analytic/` (Fidelity 0: Synthetic / Analytic)
- `multi_material_mirror_dataset_25k.csv`: 25,000 Latin Hypercube samples evaluated via closed-form optomechanical equations across Zerodur, SiC, ULE, and Beryllium.
- `multi_topology_mirror_dataset_20k.csv`: 20,000 multi-topology analytic evaluations covering 8 pocket geometries.
- `mirror_training_data_10k.csv`: 10,000 sample dataset for baseline surrogate verification.
- `isogrid_analytic_constraints_3884.csv`: 3,884 parameter evaluations based on NASA SP-8040 / NASA CR-124075 isogrid structural and buckling formulas.
- `material_properties_analytic_model.csv`: Analytical temperature-dependent material property curves based on SCHOTT TIE-48 and cryogenic reference models.

### `data/real/` (Fidelities 1, 2, and 3: Real Simulation & Metrology)
- `tier2_harbin_mendeley/`: Harbin Institute of Technology mirror surface deformation matrices and 37-term Fringe Zernike polynomial fits (DOI: 10.17632/xpxhpdjgx9.1, CC0-1.0).
- `tier2_rubin_lsst_fea/`: Rubin Observatory Simonyi Survey Telescope FEA perturbation files under gravity (zenith/horizon) and thermal loads (Zenodo: 10.5281/zenodo.8384326, CC-BY-4.0).
- `tier2_rubin_bending_modes/`: Rubin Observatory M1/M2/M3 bending modes decomposed into Zernike modes and spatial grids (Zenodo: 10.5281/zenodo.8383823, CC-BY-4.0).
- `tier2_selto_topology/`: 3D voxel topology optimization solutions for structural compliance and mass minimization (Zenodo: 10.5281/zenodo.7781392, CC-BY-4.0).
- `tier2_metaxfam/`: MetaXFam-D mechanical metamaterial benchmark covering 22 cell families and 5,072 unit cells (Zenodo: 10.5281/zenodo.22167146, CC-BY-4.0).
- `tier2_nah_plate/`: Nearfield Acoustic Holography (NAH) plate modal vibration simulation dataset (Zenodo: 10.5281/zenodo.5702615, CC-BY-4.0).
- `tier2_jwst_opd/`: Optical Path Difference (OPD) maps and wavefront error trending pipeline from STScI/MAST.
- `tier3_ntrs_jwst/`: Official NASA NTRS technical reports documenting JWST commissioning, phasing, and wavefront sensing (NTRS 20220013205, 20230011349, 20230002601).
- `flight_mirrors.csv`: Verified flight baseline table citing confirmed NASA/ESA mission specifications with verified HTTP 200 DOIs and NTRS records.

---

## 3. Scientific Integrity Guardrails

1. **G1 — Honesty in Nomenclature:** Closed-form parametric models are strictly labeled `analytic` / `synthetic`. No analytic dataset is ever labeled "empirical" or "ground truth".
2. **G2 — Verified Citations:** Every DOI and NTRS record is verified to return HTTP 200. No fabricated or unconfirmed identifiers exist in the repository.
3. **G3 — Loud Failures:** Automated harvesters never synthesize fallback records if remote endpoints are unavailable.
4. **G4 — Mandatory Provenance:** All real datasets are accompanied by a `*.provenance.json` sidecar detailing author, DOI/URL, license, fetch date, and fidelity level.
5. **G5 — Strict Validation Hold-Out:** Measured flight metrology is strictly reserved for validation and never leaked into training folds.
