"""Fetch the CDBS legacy engineering tables used to backfill stations that
have no matching engineering record in LMS (see parse_stations.py for why
that happens - roughly 54% of licensed AM and 29% of licensed FM stations).

CDBS was frozen on 2023-10-01, so unlike the LMS fetch this does not need
to run on a schedule - once fetched, it never changes. It's still run
through a headless browser because transition.fcc.gov sits behind the
same kind of Akamai bot protection as the LMS host, and plain HTTP
clients get a 403 there too.

Only the AM-side tables (am_eng_data, am_ant_sys) have been verified
against real records. fm_eng_data's schema is confirmed from the CDBS
DDL but hasn't been byte-verified yet - worth a spot check the first
time this actually runs somewhere with reliable network access to this
host.
"""
import asyncio
import os
import shutil
import sys
import zipfile
from playwright.async_api import async_playwright

BASE = "http://transition.fcc.gov/Bureaus/MB/Databases/cdbs"

TABLES = [
    "am_eng_data",
    "am_ant_sys",
    "fm_eng_data",
]

OUT_DIR = os.environ.get("CDBS_RAW_DIR", "raw_cdbs")


async def download_table(page, table):
    url = f"{BASE}/{table}.zip"
    zip_path = os.path.join(OUT_DIR, f"{table}.zip")
    async with page.expect_download(timeout=120000) as dl_info:
        try:
            await page.goto(url, timeout=120000)
        except Exception:
            pass
    download = await dl_info.value
    tmp_path = await download.path()
    shutil.copy(tmp_path, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(OUT_DIR)
    os.remove(zip_path)
    dat_path = os.path.join(OUT_DIR, f"{table}.dat")
    print(f"fetched {table}: {os.path.getsize(dat_path)} bytes")


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        failures = []
        for table in TABLES:
            try:
                await download_table(page, table)
            except Exception as e:
                print(f"FAILED {table}: {e!r}")
                failures.append(table)
        await browser.close()
    if failures:
        print(f"Failed tables: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
