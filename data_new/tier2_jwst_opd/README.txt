JWST measured OPD maps — STScI / MAST
=====================================

WHAT THIS IS
  Real in-flight James Webb Space Telescope wavefront-sensing results:
  Optical Path Difference (OPD) phase maps (FITS) plus an RMS WFE trending
  table (nm). Updated continuously by STScI from 2022 to the present.
  Fit Zernike coefficients directly from the OPD arrays.

WHY IT IS NOT A STATIC FILE HERE
  STScI serves these through the `stpsf` package against live MAST, not as a
  single frozen download. The old static bundle (stpsf-data-2.3.0.tar.gz) now
  404s. Use the retrieval functions below so you always get current data and a
  citable provenance (MAST query date).

PROVENANCE / CITATION
  STScI STPSF (successor to WebbPSF), measured OPDs doc:
  https://stpsf.readthedocs.io/en/latest/jwst_measured_opds.html
  Data source: MAST (Mikulski Archive for Space Telescopes), JWST WSS products.

HOW TO PULL IT (run fetch_jwst_opds.py in this folder)
  pip install stpsf astropy numpy
  # STPSF needs its reference data dir set once:
  #   export STPSF_PATH=/path/to/stpsf-data   (see STPSF install docs)
  python fetch_jwst_opds.py

ROLE IN THE PROJECT
  Validation + light fine-tuning of the surface-figure-error / 37-term Zernike
  head against genuine flight metrology. NOT parametric training data (it is the
  as-built JWST over time, not a geometry sweep).
