"""Fetch the CDBS legacy engineering tables used to backfill stations that
have no matching engineering record in LMS (see parse_stations.py for why
that happens - roughly 54% of licensed AM and 29% of licensed FM stations).

CDBS was frozen on 2023-10-01, so unlike the LMS fetch this does not need
to run on a schedule - once fetched, it never changes.

Unlike the LMS host, ftp.fcc.gov is NOT behind Akamai (verified: no
akamai-grn/AkamaiGHost headers). The other mirror, transition.fcc.gov,
IS behind Akamai and blocks headless Chromium outright (unlike the LMS
host's WAF rule, which only blocks plain HTTP clients) - confirmed with
a fresh GitHub Actions runner getting an instant 403 there.

ftp.fcc.gov's HTTPS gateway turned out to be broken for GET specifically
(HEAD succeeds, GET hangs/times out) - confirmed across three unrelated
networks. The underlying FTP service itself is fine over plain ftp://
(verified instant with curl) - but Python's own urllib/ftplib FTP
support hung indefinitely against this same server, so this shells out
to curl rather than trusting urllib's FTP handling.

Only the AM-side tables (am_eng_data, am_ant_sys) have been verified
against real records. fm_eng_data's schema is confirmed from the CDBS
DDL but hasn't been byte-verified yet - worth a spot check the first
time this actually runs successfully.
"""
import os
import subprocess
import sys
import zipfile

BASE = "ftp://ftp.fcc.gov/pub/Bureaus/MB/Databases/cdbs"

TABLES = [
    "am_eng_data",
    "am_ant_sys",
    "fm_eng_data",
]

OUT_DIR = os.environ.get("CDBS_RAW_DIR", "raw_cdbs")


def download_table(table):
    url = f"{BASE}/{table}.zip"
    zip_path = os.path.join(OUT_DIR, f"{table}.zip")
    subprocess.run(
        ["curl", "-sS", "--fail", "--max-time", "120", url, "-o", zip_path],
        check=True,
    )
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
