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
    # save_as(), not path() + shutil.copy(): path() points at Playwright's
    # own internal artifact file, which on the GitHub Actions Linux runner
    # (never reproduced on macOS) could vanish in under a millisecond
    # between an os.path.exists() check and shutil.copy() opening it -
    # confirmed by direct evidence (2026-09-17): exists() returned True and
    # the very next line's copy still raised ENOENT on that same path.
    # save_as() is Playwright's own recommended way to persist a download
    # and isn't subject to that race.
    await download.save_as(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        if not zf.namelist():
            # FCC publishes the dated dump folder (and a placeholder zip
            # per table) before that day's tables actually finish
            # generating server-side - confirmed 2026-09-17: every table
            # came back as a valid-but-empty 22-byte zip early in the UTC
            # day, for a folder that had real 42-251MB files as of the
            # previous run 4 days earlier. Not a fetch bug - just too early
            # relative to FCC's own job; retry later or wait for the
            # Sunday 09:00 UTC schedule.
            raise RuntimeError(
                f"{table}.zip for {date_folder} is empty (0 entries) - "
                "FCC's dump for today likely hasn't finished generating yet"
            )
        zf.extractall(OUT_DIR)
    os.remove(zip_path)
    dat_path = os.path.join(OUT_DIR, f"{table}.dat")
    print(f"fetched {table}: {os.path.getsize(dat_path)} bytes")


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        # channel="chromium" forces the full Chrome-for-Testing binary
        # instead of Playwright's default "headless shell" (the lightweight
        # binary chromium.launch() has used automatically since ~1.45 when
        # no channel is given) - ruled out as the root cause of a CI-only
        # download failure (2026-09-17: every table failed instantly with
        # FileNotFoundError on the Linux Actions runner, but not locally on
        # macOS with either binary), kept anyway since it's the more
        # full-featured binary and `--with-deps chromium` already fetches
        # both, so it costs nothing.
        browser = await p.chromium.launch(headless=True, channel="chromium")
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.on(
            "response",
            lambda r: print(f"  response {r.status} {r.url}")
            if "/api/download/dbfile/" in r.url
            else None,
        )
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
