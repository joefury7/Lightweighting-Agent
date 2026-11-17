#!/usr/bin/env python3
"""
Fetch real JWST measured OPD maps + RMS WFE trending table from STScI/MAST.
Writes into ./ (this folder). See README.txt for context.

Requires: pip install stpsf astropy numpy  (and STPSF_PATH reference data configured)
"""
import os
import sys

OUT = os.path.dirname(os.path.abspath(__file__))

def main():
    try:
        import stpsf
        from stpsf import mast_wss
    except Exception as e:
        sys.exit(
            "stpsf not available (%s).\n"
            "Install with: pip install stpsf astropy numpy\n"
            "and set STPSF_PATH to the STPSF reference-data directory "
            "(see https://stpsf.readthedocs.io/en/latest/installation.html)." % e
        )

    # 1. Trending table of RMS WFE (OTE-only and OTE+SI) in nm, over the mission.
    try:
        tbl = mast_wss.retrieve_mast_opd_table()
        csv_path = os.path.join(OUT, "jwst_wfe_trending_table.csv")
        tbl.write(csv_path, format="ascii.csv", overwrite=True)
        print("Wrote", csv_path, "(%d rows)" % len(tbl))
    except Exception as e:
        print("WFE trending table fetch failed:", e)

    # 2. All available measured OPD FITS maps (phase maps; fit Zernikes from these).
    try:
        opd_dir = os.path.join(OUT, "opd_maps")
        os.makedirs(opd_dir, exist_ok=True)
        mast_wss.download_all_opds(opd_dir)
        n = len([f for f in os.listdir(opd_dir) if f.endswith((".fits", ".fits.gz"))])
        print("Downloaded", n, "OPD FITS maps into", opd_dir)
    except Exception as e:
        print("OPD map download failed:", e)

if __name__ == "__main__":
    main()
