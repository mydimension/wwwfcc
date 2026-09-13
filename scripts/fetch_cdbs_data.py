"""Fetch the CDBS legacy engineering tables used to backfill stations that
have no matching engineering record in LMS (see parse_stations.py for why
that happens - roughly 54% of licensed AM and 29% of licensed FM stations).

CDBS was frozen on 2023-10-01, so unlike the LMS fetch this does not need
to run on a schedule - once fetched, it never changes.

Unlike the LMS host, ftp.fcc.gov is NOT behind Akamai (verified: no
akamai-grn/AkamaiGHost headers, and a plain HEAD request succeeds where
enterpriseefiling.fcc.gov's plain HTTP clients get a 403). The other
mirror, transition.fcc.gov, IS behind Akamai and blocks headless
Chromium outright (unlike the LMS host's WAF rule, which only blocks
plain HTTP clients) - confirmed with a fresh GitHub Actions runner
getting an instant 403 there, so this isn't a session/IP reputation
thing, it's just a stricter rule. Plain urllib against ftp.fcc.gov is
the simpler and more reliable path.

Only the AM-side tables (am_eng_data, am_ant_sys) have been verified
against real records. fm_eng_data's schema is confirmed from the CDBS
DDL but hasn't been byte-verified yet - worth a spot check the first
time this actually runs successfully.
"""
import os
import sys
import urllib.request
import zipfile

BASE = "https://ftp.fcc.gov/pub/Bureaus/MB/Databases/cdbs"

TABLES = [
    "am_eng_data",
    "am_ant_sys",
    "fm_eng_data",
]

OUT_DIR = os.environ.get("CDBS_RAW_DIR", "raw_cdbs")


def download_table(table):
    url = f"{BASE}/{table}.zip"
    zip_path = os.path.join(OUT_DIR, f"{table}.zip")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(zip_path, "wb") as f:
        f.write(resp.read())
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(OUT_DIR)
    os.remove(zip_path)
    dat_path = os.path.join(OUT_DIR, f"{table}.dat")
    print(f"fetched {table}: {os.path.getsize(dat_path)} bytes")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    failures = []
    for table in TABLES:
        try:
            download_table(table)
        except Exception as e:
            print(f"FAILED {table}: {e!r}")
            failures.append(table)
    if failures:
        print(f"Failed tables: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
