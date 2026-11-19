# data_new/ — Tier 2 & Tier 3 real datasets (downloaded 2026-11-13)

> **Current status (19 Nov 2026):** no dataset in this folder is used for training. The surrogate is trained only on FEA of the exact NX geometry (`data/fea/`).
> Three datasets are used for verification only:
> - JWST OPD maps: measured RMS WFE check
> - Rubin M1M3 FEA: optical post-processing check against Rubin's own code
> - NAH plates: FEA-chain check against COMSOL
>
> See `data/external_validation/README.md`. The "Use" column below records the original download intent, not current use.

All files fetched and integrity-checked (gzip -t / unzip -t / MAT header / PDF size). All are genuine third-party downloads; note that some are themselves simulation or generated benchmarks (Harbin ellipse deformations, SELTO, MetaXFam) rather than measurements. Sizes are on-disk (`du`, 1024-based).

## Tier 2 — real external datasets (training / fine-tuning / validation)

| Folder | Source & citation | Year | License | Size / format | Supervises | Use |
|---|---|---|---|---|---|---|
| `tier2_rubin_lsst_fea/` | Rubin Observatory Simonyi Survey Telescope — FEA perturbation files. Zenodo `10.5281/zenodo.8384326` | 2023 | CC-BY-4.0 | 32 MB, 24× `.fits.gz` | gravity sag (horizon/zenith), thermal FEA, node grids, influence functions | Real analog for SOL-101 gravity cases; train/fine-tune sag head |
| `tier2_rubin_bending_modes/` | Rubin — Legacy bending-mode data (M1/M2/M3). Zenodo `10.5281/zenodo.8383823` | 2023 | CC-BY-4.0 | 28 MB, 13× `.fits.gz` + `bend.yaml` | surface figure → **Zernike** (modes stored as Zernike + bicubic spline) | Train/validate the surface→Zernike mapping |
| `tier2_harbin_mendeley/` | Harbin Inst. of Technology — mirror deformation + Zernike fitting. Mendeley `10.17632/xpxhpdjgx9.1` | 2026 | CC0-1.0 | 6.5 MB, 17× `.xlsx` | FE surface deformation grids, 37-term Zernike, PAWN/Sobol sensitivity | Primary real optical labels |
| `tier2_metaxfam/` | MetaXFam-D cross-topology metamaterial benchmark. Zenodo `10.5281/zenodo.22167146` (v2) | 2025 | CC-BY-4.0 | 1.2 MB, `.zip` (~5,072 unit cells, 22 families) | effective stiffness / buckling across topologies incl. auxetic | Multi-topology generalization |
| `tier2_selto_topology/` | SELTO Dataset — 3-D topology optimization (Ariane Group/Synera solver). Zenodo `10.5281/zenodo.7781392` | 2023 | CC-BY-4.0 | 132 MB, 8× `.tar.gz` (disc/sphere, simple/complex, train/test) | mass / compliance / generative topology | Structural/mass head pre-training |
| `tier2_nah_plate/` | NAH rectangular plate dataset (COMSOL). Zenodo `10.5281/zenodo.5702615` | 2021 | CC-BY-4.0 | 496 MB, `rectangular_simulation_nah.mat` + README/example | modal frequency + 2-D field maps (flat isotropic plates) | Physics pre-training for frequency/field head |
| `tier2_jwst_opd/` | JWST measured OPD maps — STScI/MAST via `stpsf` | 2022→live | STScI/MAST (US govt) | script + README (data pulled live) | RMS WFE + OPD phase maps (fit Zernikes) | Flight-truth validation / light fine-tune. **Run `fetch_jwst_opds.py`** |

### Geometry-regime caveat (Rubin)
The Rubin M1/M2/M3 mirrors are actively-supported thin meniscus mirrors, not pocketed lightweight substrates. The physics (gravity-load surface deformation → Zernike) transfers; the geometry regime does not. Use them to supervise optical *response*, not pocket geometry.

## Tier 3 — recent real validation baselines (extract values from tables/figures)

| File | Source | Year | What to extract |
|---|---|---|---|
| `tier3_ntrs_jwst/NTRS_20220013205.pdf` | Commissioning the JWST Optical Telescope Element (NTRS 20220013205) | 2022 | measured WFE / segment figures |
| `tier3_ntrs_jwst/NTRS_20230011349.pdf` | Phasing the Webb Telescope (Acton, NTRS 20230011349) | 2022 | measured phasing / WFS results |
| `tier3_ntrs_jwst/NTRS_20230002601.pdf` | Image-Based Wavefront Sensing (NTRS 20230002601) | 2023 | WFS methods supporting the Zernike-fit pipeline |

All three are U.S. Government works, publicly releasable. PDF links resolved via `https://ntrs.nasa.gov/api/citations/<ID>` (filenames are non-standard; the `<ID>.pdf` guess 404s).

## Not included here (by design)
- NAH `.mat` is a MATLAB v5 file — load with `scipy.io.loadmat`.
- JWST OPDs are retrieved live (see `tier2_jwst_opd/README.txt`) — not a frozen file.
- Leads needing a browser / author contact (ESO ELT, Keck, TMT, GMT, CIOMP/NIAOT via scidb.cn) are documented in `../sources/recent_flight_metrology.md` and were intentionally NOT downloaded (no machine-confirmable DOI).
