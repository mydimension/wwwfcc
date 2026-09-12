"""Fetch raw LMS (FCC Licensing Management System) table dumps.

enterpriseefiling.fcc.gov sits behind an Akamai WAF rule that blocks plain
HTTP clients (curl, wget, requests) with a 403, even though the same
request succeeds from a real browser. This script drives headless Chromium
via Playwright so the fetch presents a genuine browser fingerprint.

The nightly dump lives under a folder named for the dump date (e.g.
"09-12-2026"), so we scrape the index page for that folder name each run
rather than computing today's date ourselves.

Output: one pipe-delimited .dat file per table, extracted into OUT_DIR.
This is raw intermediate data, not meant to be committed to the site.
"""
import asyncio
import os
import re
import shutil
import sys
import zipfile
from playwright.async_api import async_playwright

BASE = "https://enterpriseefiling.fcc.gov"
INDEX_URL = f"{BASE}/dataentry/public/tv/lmsDatabase.html"

# Tables needed to resolve a facility to its current licensed AM/FM
# technical parameters. See docs/lms-joins.md for the join path.
TABLES = [
    "facility",
    "facility_history",
    "facility_applicant",
    "application_facility",
    "assigned_authorization",
    "app_location",
    "app_antenna",
    "app_am_antenna",
    "app_am_tower",
    "app_am_augmentation",
    "lkp_facility_status",
    "lkp_service_code",
    "lkp_state",
    "lkp_city",
    "lkp_county",
]

OUT_DIR = os.environ.get("LMS_RAW_DIR", "raw_lms")


async def discover_date_folder(page):
    await page.goto(INDEX_URL, wait_until="networkidle", timeout=60000)
    html = await page.content()
    m = re.search(r"/dataentry/api/download/dbfile/(\d{2}-\d{2}-\d{4})/", html)
    if not m:
        raise RuntimeError("Could not find dated dump folder on LMS database page")
    return m.group(1)


async def download_table(page, date_folder, table):
    url = f"{BASE}/dataentry/api/download/dbfile/{date_folder}/{table}.zip"
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
        date_folder = await discover_date_folder(page)
        print(f"Using dump date folder: {date_folder}")
        failures = []
        for table in TABLES:
            try:
                await download_table(page, date_folder, table)
            except Exception as e:
                print(f"FAILED {table}: {e!r}")
                failures.append(table)
        await browser.close()
    if failures:
        print(f"Failed tables: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
