"""
Fit + validate the FEA surrogate and write the honest prediction-gap report.

  python ml_engine/train_fea_surrogate.py

* Model selection (plain GP vs GP with the smeared-plate physics prior) by leave-one-out error.
* Writes data/fea/surrogate_config.json (chosen model) and data/fea/surrogate_validation.json
  (LOO metrics + per-design FEA vs prediction table).  The server reports these numbers.
"""
import json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ml_engine.fea_surrogate import FEASurrogate, load_records

def main():
    recs = load_records()
    results = {}
    for prior in (False, True):
        s = FEASurrogate(recs, use_prior=prior)
        summ, rows = s.loo_cv()
        results[prior] = (summ, rows)
        print(("physics-prior GP" if prior else "plain GP"), json.dumps({k: round(v["mape_pct"], 2) for k, v in summ.items()}))
    use_prior = results[True][0]["rms_sag_nm"]["mape_pct"] <= results[False][0]["rms_sag_nm"]["mape_pct"]
    summ, rows = results[use_prior]
    out_dir = os.path.join(ROOT, "data", "fea")
    json.dump({"use_prior": use_prior}, open(os.path.join(out_dir, "surrogate_config.json"), "w"), indent=2)
    report = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "n_fea_records": len(recs),
              "model": "GP + physics prior" if use_prior else "GP", "validation": "leave-one-out on FEA records",
              "loo_metrics_pct": summ, "per_design": rows}
    json.dump(report, open(os.path.join(out_dir, "surrogate_validation.json"), "w"), indent=2)
    print("chosen:", report["model"], "| LOO MAPE rms sag = %.2f %%" % summ["rms_sag_nm"]["mape_pct"])

if __name__ == "__main__":
    main()
