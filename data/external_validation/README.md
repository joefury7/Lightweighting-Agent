# External-data validation (authentic third-party data)

These checks use published, third-party datasets from `data_new/` to verify parts of the pipeline.
**None of this data is used to train the surrogate, drive the optimiser or change any design or result.**
Training stays on FEA of the exact NX-journal geometry (`data/fea/`), because no external dataset describes this mirror.
Removing this folder would not change a single number the app produces.

| # | Dataset (source, licence) | Kind of data | What it validates | Script | Result |
|---|---|---|---|---|---|
| 1 | **JWST wavefront sensing OPD maps**: STScI/MAST, service `Mast.Jwst.Filtered.Wss` (690 products in the NRCA3_FP1 catalogue; 6 maps 2022–2024 downloaded) | **Measured in flight** | RMS wavefront-error computation and 37-term Zernike decomposition on real measured wavefronts | `validation/jwst_measured_wfe.py` | Our RMS equals the STScI-reported `RMS_WFE` on all 6 maps (max difference 0.005 %) |
| 2 | **Rubin Observatory M1M3 FEA**: Zenodo 10.5281/zenodo.8384326, CC-BY-4.0 (8.4 m honeycomb, i.e. lightweighted, mirror; zenith and horizon gravity) | Observatory engineering FEA | Piston/tilt/power removal and RMS/PV of a gravity deflection field, against Rubin's reference implementation (batoid_rubin + galsim annular Zernikes) | `validation/rubin_m1m3_gravity_optics.py` | Identical to numerical precision (difference 2e-14 %) for both gravity cases |
| 3 | **COMSOL plate eigenfrequencies**: Olivieri et al., *Sensors* 21:7834 (2021), Zenodo 10.5281/zenodo.5702615, CC-BY-4.0 (672 plates × clamped/free/simply supported) | Independent commercial-solver results | Our FEA chain (gmsh → C3D10 → CalculiX), the same chain used for the mirror gravity analysis | `validation/nah_plate_modal_benchmark.py` | 230 modes on 12 plates (36 cases): median error 0.18 %, 90th percentile 0.71 %, max 1.19 % |

## Details and caveats

**JWST.**
- The OPD maps are delivered with piston/tip/tilt already removed, so the plain pupil RMS is the quantity STScI reports.
- The 37 Fringe terms capture only a small fraction of the measured variance. JWST's error is dominated by segment-level (high-order) structure, which is expected for a segmented telescope.
- The maps were fetched by `data_new/tier2_jwst_opd/fetch_jwst_opds_stdlib.py`.

**Rubin.**
- Fitting on the same sample points reproduces Rubin's reference exactly.
- The app additionally resamples node data to a uniform grid, which gives an area-weighted RMS. On Rubin's coarse legacy mesh, where the honeycomb print-through changes from node to node, node-sampled and area-weighted RMS differ by 13–41 %.
- On our own mirror mesh, the area-weighted value is converged: a 241 vs 481 grid differs by 0.04 %.
- Only the axial node displacement is used, on the M1 annulus (R = 2.558–4.18 m).

**NAH plates.**
- The dataset does not state the material. Nominal aluminium (E = 70 GPa, ρ = 2700 kg/m³, ν = 0.33) is used with no fitting. Closed-form Kirchhoff theory with these values reproduces the dataset's first simply-supported frequency of all 672 plates within 0.64 % median (1.74 % max).
- The boundary condition is stored as a MATLAB `string` object that scipy cannot read. The file is ordered in three contiguous blocks (clamped, free, simply supported), which the Kirchhoff check confirms.
- For two free plates, one extra mode falls just below the 2 kHz cut-off in our results, because our frequencies run about 0.2 % lower. That mode is excluded from the comparison.
- `nah_plate_meta.npz` is the extracted metadata; the 496 MB `.mat` stays in `data_new/`.

## Datasets in `data_new/` not used, and why

| Dataset | Reason |
|---|---|
| Harbin (Mendeley 10.17632/xpxhpdjgx9.1) | The deformations are parametric synthetic ellipses with random seeds, and the surface grids are stored without coordinates. Not authentic measured or engineering data. |
| SELTO topology optimisation | Optimiser-generated 2D/3D topologies; no counterpart in this design space. |
| MetaXFam | Pixel unit cells homogenised by the authors' own code; synthetic benchmark. |
| Rubin bending modes | Each mode is stored as Zernike terms plus a residual grid, so it is not an independent test of the fitting code. |
| NTRS JWST papers | Literature context and citations only. |

## Suggested wording for the paper

> The optical post-processing and the finite-element chain were verified against independent, authentic third-party data:
> - in-flight JWST wavefront measurements from the STScI/MAST archive (RMS agreement within 0.005 % on six maps from 2022–2024);
> - the Rubin Observatory's M1M3 gravity finite-element results, compared with the observatory's reference implementation (agreement to numerical precision);
> - a published COMSOL dataset of plate eigenfrequencies (Olivieri et al., 2021; 230 modes, median error 0.18 %, maximum 1.19 %).
>
> The surrogate model itself is trained exclusively on finite-element analyses of the exact as-built geometry, because no public dataset describes this mirror design.

Re-run: `python validation/jwst_measured_wfe.py`, `python validation/rubin_m1m3_gravity_optics.py`, `python validation/nah_plate_modal_benchmark.py 12`.
Dependencies: astropy, galsim (Rubin reference), scipy.
