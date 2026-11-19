"""Fetch the JWST wavefront-sensing OPD catalogue and a few measured OPD maps from MAST
(STScI) using only the Python standard library. Same MAST service and URIs as
stpsf.mast_wss (service 'Mast.Jwst.Filtered.Wss', uri mast:JWST/product/<fileName>)."""
import json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
INVOKE = "https://mast.stsci.edu/api/v0/invoke"
DL = "https://mast.stsci.edu/api/v0.1/Download/file?uri=mast:JWST/product/"


def service_request(service, params, pagesize=5000):
    req = {"service": service, "params": params, "format": "json", "pagesize": pagesize, "page": 1}
    data = urllib.parse.urlencode({"request": json.dumps(req)}).encode()
    with urllib.request.urlopen(urllib.request.Request(INVOKE, data=data, headers={
            "Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain"}), timeout=120) as r:
        return json.loads(r.read().decode())


def main(n_maps=6):
    res = service_request("Mast.Jwst.Filtered.Wss", {
        "columns": "*",
        "filters": [{"paramName": "ap_type", "values": ["OPD"]},
                    {"paramName": "apername", "values": ["NRCA3_FP1"]}]})
    rows = sorted(res.get("data", []), key=lambda r: r.get("date_obs_mjd") or 0)
    with open(os.path.join(HERE, "mast_wss_opd_catalogue.json"), "w") as f:
        json.dump({"fields": res.get("fields"), "data": rows}, f)
    print("catalogue rows:", len(rows))
    os.makedirs(os.path.join(HERE, "opd_maps"), exist_ok=True)
    picks = [rows[int(i * (len(rows) - 1) / (n_maps - 1))] for i in range(n_maps)] if rows else []
    for r in picks:
        fn = r["fileName"]
        out = os.path.join(HERE, "opd_maps", fn)
        if not os.path.exists(out):
            urllib.request.urlretrieve(DL + fn, out)
        print("downloaded", fn, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
