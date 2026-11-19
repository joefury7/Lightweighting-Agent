"""
External data: JWST in-flight MEASURED wavefront error (optical path difference maps from the
observatory's wavefront-sensing system), run through our optical post-processing.

Data
----
STScI / MAST, service 'Mast.Jwst.Filtered.Wss' (the same source used by STScI's stpsf package).
Downloaded by data_new/tier2_jwst_opd/fetch_jwst_opds_stdlib.py: catalogue of all NIRCam
NRCA3_FP1 OPD products (mast_wss_opd_catalogue.json) and six maps spread evenly over 2022-2024
(opd_maps/*.fits). Extension RESULT_PHASE = measured OPD in micrometres; header RMS_WFE = the RMS
STScI reports for that measurement.

Checks
------
1. Our RMS over the pupil versus STScI's RMS_WFE (the maps are delivered piston/tip/tilt-free,
   so the plain RMS is the comparable quantity).
2. Our 37-term Fringe Zernike decomposition (fea_engine.mirror_fea.optical_metrics_points,
   evaluated directly at the pupil pixels) of the measured flight wavefront: how much of the
   RMS is low order (captured by 37 terms) versus segment-level/high order (fit residual).
3. Context for the paper: the mirror's predicted gravity error (dataset design) as a fraction of
   flight-measured telescope WFE levels.

Nothing here feeds the surrogate or the optimiser.
"""
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DIR = os.path.join(ROOT, "data_new", "tier2_jwst_opd")
OUT = os.path.join(ROOT, "data", "external_validation", "jwst_measured_wfe.json")


def analyse(path):
    from astropy.io import fits
    from fea_engine.mirror_fea import optical_metrics_points
    with fits.open(path) as h:
        P = h["RESULT_PHASE"].data.astype(float) * 1e3        # um -> nm
        rms_stsci = float(h["RESULT_PHASE"].header["RMS_WFE"]) * 1e3
        date = h[0].header.get("DATE-OBS")
        M = h["PUPIL_MASK"].data > 0 if h["PUPIL_MASK"].data.shape == P.shape else None
    if M is None:
        M = np.isfinite(P) & (P != 0)
    n = P.shape[0]
    yy, xx = np.mgrid[:n, :n]
    cx, cy = xx[M].mean(), yy[M].mean()
    x, y, w = xx[M] - cx, yy[M] - cy, P[M]
    R = float(np.hypot(x, y).max()) * 1.0005
    met = optical_metrics_points(x, y, w, R, 0.0, grid=None)
    rms_raw = float(np.sqrt(np.mean(w ** 2)))
    return {"file": os.path.basename(path), "date_obs": date, "pupil_pixels": int(M.sum()),
            "rms_stsci_nm": rms_stsci, "rms_ours_nm": rms_raw,
            "rms_diff_pct": 100 * (rms_raw - rms_stsci) / rms_stsci,
            "rms_ptt_removed_ours_nm": met["rms_sag_nm"],
            "fringe37_fit_residual_rms_nm": met["zernike_fit_residual_rms_nm"],
            "low_order_fraction_of_variance": float(1 - met["zernike_fit_residual_rms_nm"] ** 2 / met["rms_sag_nm"] ** 2),
            "fringe37_first11_nm": [round(c, 3) for c in met["zernike_fringe_37_nm"][:11]]}


def main():
    files = sorted(glob.glob(os.path.join(DIR, "opd_maps", "*.fits")))
    if not files:
        sys.exit("No OPD maps - run data_new/tier2_jwst_opd/fetch_jwst_opds_stdlib.py first")
    cat = json.load(open(os.path.join(DIR, "mast_wss_opd_catalogue.json")))
    res = [analyse(f) for f in files]
    for r in res:
        print(f"{r['file']:32s} {r['date_obs']}  STScI {r['rms_stsci_nm']:7.2f} nm  ours {r['rms_ours_nm']:7.2f} nm "
              f"({r['rms_diff_pct']:+.4f}%)  37-term residual {r['fringe37_fit_residual_rms_nm']:6.2f} nm")
    rec = json.loads(open(os.path.join(ROOT, "data", "fea", "isogrid_fea_dataset.jsonl")).readline())
    typical = [r["rms_stsci_nm"] for r in res if r["rms_stsci_nm"] < 200]
    out = {"source": "STScI/MAST JWST wavefront sensing OPD products (service Mast.Jwst.Filtered.Wss), "
                     "aperture NRCA3_FP1; same archive as STScI stpsf",
           "catalogue_products": len(cat["data"]),
           "maps": res,
           "max_abs_rms_diff_pct": float(max(abs(r["rms_diff_pct"]) for r in res)),
           "context": {"jwst_measured_wfe_nm_range_routine": [min(typical), max(typical)],
                       "our_dataset_design": rec["id"],
                       "our_gravity_rms_surface_nm": rec["rms_sag_nm"],
                       "our_gravity_rms_wavefront_nm (x2, reflection)": 2 * rec["rms_sag_nm"],
                       "note": "JWST values are full-telescope in-orbit WFE (zero-g, segmented 6.5 m); ours is the "
                               "1 g self-weight figure error of a single 560 mm mirror on its mount. Shown for "
                               "scale only, not as a like-for-like comparison."}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print("max |RMS diff| vs STScI: %.2e %%" % out["max_abs_rms_diff_pct"])
    return out


if __name__ == "__main__":
    main()
