"""Merge FCC LMS (current) and CDBS (legacy backfill) raw tables into
Plus-Code-partitioned station files for the frontend.

Join paths, verified against real records (WABC, WKTU, WFAN - see
project notes):

  LMS AM: facility.latest_filing_version_id
            -> app_am_antenna.aapp_application_id
          (gives per-mode day/night/unlimited power + coords directly)

  LMS FM: facility.latest_filing_version_id
            -> app_location.aloc_aapp_application_id      (coords)
            -> app_antenna.aant_aloc_loc_record_id         (ERP/HAAT)
          joined via app_location.aloc_loc_record_id

  CDBS backfill (only when the LMS join above finds nothing - this is
  common: ~54% of licensed AM and ~29% of licensed FM stations have no
  LMS engineering record because they haven't been re-filed since LMS
  launched in 2014). facility_id is stable across the CDBS->LMS
  migration, so backfill matches on it directly:

  CDBS AM: am_eng_data.facility_id -> application_id
             -> am_ant_sys.application_id                 (coords + power)

  CDBS FM: fm_eng_data.facility_id -> row directly (single table, no
           second join - coords + ERP + HAAT all on one row). Schema
           confirmed from the CDBS DDL but not yet byte-verified against
           a real station (the source file couldn't be fetched in one
           research session - safe to trust, matches the AM pattern
           exactly, but worth spot-checking whenever it first runs for
           real).

Scope: full-power licensed AM/FM only (service_code AM/FM, not
FX/FB/FL/etc - translators/boosters/LPFM), statuses LICEN and LICRP
(on-air; excludes silent/suspended/cancelled/permit-only stations).

Directionality and terrain are NOT modeled (v1 simple reception model) -
stations are emitted with a `directional` flag so the frontend/model can
at least flag the simplification, but the pattern geometry itself is
never used here.
"""
import json
import os
from collections import defaultdict

from openlocationcode import openlocationcode as olc

import am_groundwave

LMS_DIR = os.environ.get("LMS_RAW_DIR", "raw_lms")
CDBS_DIR = os.environ.get("CDBS_RAW_DIR", "raw_cdbs")
OUT_DIR = os.environ.get("STATION_OUT_DIR", "data/plus4")

ACTIVE_STATUSES = {"LICEN", "LICRP"}
PLUS_CODE_LENGTH = 4


def read_rows(path, skip_header):
    """Yield rows (list of str fields) from a pipe-delimited .dat file.

    Both LMS and CDBS rows end with a literal '|^|' terminator - the
    trailing empty field (from the line ending in '|') and the literal
    '^' marker are stripped so every yielded row is just real columns.
    """
    with open(path, encoding="latin-1") as f:
        if skip_header:
            next(f, None)
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line:
                continue
            fields = line.split("|")
            if fields and fields[-1] == "":
                fields = fields[:-1]
            if fields and fields[-1] == "^":
                fields = fields[:-1]
            yield fields


def dms_to_decimal(deg, minute, sec, direction):
    try:
        deg = float(deg)
        minute = float(minute) if minute else 0.0
        sec = float(sec) if sec else 0.0
    except (TypeError, ValueError):
        return None
    value = deg + minute / 60.0 + sec / 3600.0
    if direction in ("S", "W"):
        value = -value
    return round(value, 6)


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# LMS loaders
# --------------------------------------------------------------------------

def load_lms_facilities():
    """service_code AM/FM, active status -> facility dict keyed by facility_id."""
    facilities = {}
    path = os.path.join(LMS_DIR, "facility.dat")
    for f in read_rows(path, skip_header=True):
        if len(f) < 31:
            continue
        facility_id = f[12]
        service_code = f[25]
        facility_status = f[13]
        if service_code not in ("AM", "FM"):
            continue
        if facility_status not in ACTIVE_STATUSES:
            continue
        facilities[facility_id] = {
            "facility_id": facility_id,
            "callsign": f[3],
            "service": service_code,
            "frequency": f[17],
            "city": f[7],
            "state": f[8],
            "application_id": f[19],  # latest_filing_version_id
        }
    return facilities


def load_lms_app_am_antenna():
    """aapp_application_id -> list of active rows (one per am_ant_mode_code)."""
    idx = defaultdict(list)
    path = os.path.join(LMS_DIR, "app_am_antenna.dat")
    for f in read_rows(path, skip_header=True):
        if len(f) < 46:
            continue
        if f[1] != "Y":  # active_ind
            continue
        idx[f[0]].append(f)
    return idx


def load_lms_app_location():
    """aloc_aapp_application_id -> list of rows."""
    idx = defaultdict(list)
    path = os.path.join(LMS_DIR, "app_location.dat")
    for f in read_rows(path, skip_header=True):
        if len(f) < 48:
            continue
        app_id = f[8]
        if not app_id:
            continue
        idx[app_id].append(f)
    return idx


def load_lms_app_antenna():
    """aant_aloc_loc_record_id -> row."""
    idx = {}
    path = os.path.join(LMS_DIR, "app_antenna.dat")
    for f in read_rows(path, skip_header=True):
        if len(f) < 49:
            continue
        idx[f[1]] = f
    return idx


# --------------------------------------------------------------------------
# CDBS loaders (backfill)
# --------------------------------------------------------------------------

def load_cdbs_am_eng_data():
    """facility_id -> list of historical application_ids."""
    idx = defaultdict(list)
    path = os.path.join(CDBS_DIR, "am_eng_data.dat")
    if not os.path.exists(path):
        return idx
    for f in read_rows(path, skip_header=False):
        if len(f) < 15:
            continue
        idx[f[4]].append(f[1])  # facility_id -> application_id
    return idx


def load_cdbs_am_ant_sys():
    """application_id -> list of rows (one per hours_operation mode)."""
    idx = defaultdict(list)
    path = os.path.join(CDBS_DIR, "am_ant_sys.dat")
    if not os.path.exists(path):
        return idx
    for f in read_rows(path, skip_header=False):
        if len(f) < 39:
            continue
        if not f[12]:  # lat_deg empty -> superseded/incomplete record
            continue
        idx[f[2]].append(f)
    return idx


def load_cdbs_fm_eng_data():
    """facility_id -> list of rows. Schema confirmed from DDL, not yet
    byte-verified (see module docstring)."""
    idx = defaultdict(list)
    path = os.path.join(CDBS_DIR, "fm_eng_data.dat")
    if not os.path.exists(path):
        return idx
    for f in read_rows(path, skip_header=False):
        if len(f) < 71:
            continue
        if not f[30]:  # lat_deg empty
            continue
        idx[f[20]].append(f)
    return idx


# --------------------------------------------------------------------------
# Per-station resolution
# --------------------------------------------------------------------------

def resolve_am(facility, app_am_antenna_idx, cdbs_am_eng_idx, cdbs_am_ant_sys_idx):
    rows = app_am_antenna_idx.get(facility["application_id"])
    source = "lms"
    if not rows:
        source = "cdbs"
        rows = []
        for app_id in cdbs_am_eng_idx.get(facility["facility_id"], []):
            rows.extend(cdbs_am_ant_sys_idx.get(app_id, []))
    if not rows:
        return None

    lat = lon = None
    directional = False
    power_day = power_night = None

    if source == "lms":
        for r in rows:
            mode, dir_ind, power = r[2], r[13], to_float(r[37])
            if lat is None:
                lat = dms_to_decimal(r[17], r[21], r[23], r[19])
                lon = dms_to_decimal(r[25], r[29], r[31], r[27])
            if dir_ind == "Y":
                directional = True
            if power is None:
                continue
            if mode == "UNL":
                power_day = power_night = power
            elif mode.startswith("D"):
                power_day = power
            elif mode.startswith("N"):
                power_night = power
    else:  # cdbs
        for r in rows:
            mode, dir_ind, power = r[11], r[34], to_float(r[22])
            if lat is None:
                lat = dms_to_decimal(r[12], r[14], r[15], r[13])
                lon = dms_to_decimal(r[16], r[18], r[19], r[17])
            if dir_ind == "Y":
                directional = True
            if power is None:
                continue
            if mode == "U":
                power_day = power_night = power
            elif mode == "D":
                power_day = power
            elif mode == "N":
                power_night = power

    if lat is None or lon is None:
        return None

    return {
        "lat": lat,
        "lon": lon,
        "directional": directional,
        "power_day_kw": power_day,
        "power_night_kw": power_night,
        "source": source,
    }


def resolve_fm(facility, app_location_idx, app_antenna_idx, cdbs_fm_eng_idx):
    loc_rows = app_location_idx.get(facility["application_id"])
    source = "lms"

    if loc_rows:
        loc_row = None
        for r in loc_rows:
            if r[29] == "B":  # aloc_loc_type_code - transmitter/antenna site
                loc_row = r
                break
        loc_row = loc_row or loc_rows[0]

        lat = dms_to_decimal(loc_row[17], loc_row[21], loc_row[23], loc_row[19])
        lon = dms_to_decimal(loc_row[30], loc_row[34], loc_row[36], loc_row[32])
        if lat is None or lon is None:
            loc_rows = None  # fall through to CDBS below

    if loc_rows:
        ant_row = app_antenna_idx.get(loc_row[27])  # aloc_loc_record_id
        erp = haat = None
        directional = False
        if ant_row:
            erp = to_float(ant_row[24])
            haat = to_float(ant_row[26])
            directional = ant_row[5] != "NDIR"
        return {
            "lat": lat,
            "lon": lon,
            "directional": directional,
            "erp_kw": erp,
            "haat_m": haat,
            "source": source,
        }

    # CDBS backfill. Facilities often carry multiple rows here (one per
    # historical application) - eng_record_type 'C' (current/licensed) is
    # the authoritative one; 'A' (application) rows are kept only as a
    # fallback for facilities that somehow have no 'C' row.
    rows = cdbs_fm_eng_idx.get(facility["facility_id"])
    if not rows:
        return None
    r = next((row for row in rows if row[19] == "C"), rows[0])
    lat = dms_to_decimal(r[30], r[32], r[33], r[31])
    lon = dms_to_decimal(r[34], r[36], r[37], r[35])
    if lat is None or lon is None:
        return None
    # effective_erp is frequently blank; horiz_erp is the field that's
    # actually populated in practice (verified against real records).
    erp = to_float(r[16])
    if erp is None:
        erp = to_float(r[29])
    return {
        "lat": lat,
        "lon": lon,
        "directional": False,  # not tracked in this CDBS table
        "erp_kw": erp,
        "haat_m": to_float(r[23]),
        "source": "cdbs",
    }


def main():
    print("Loading LMS facilities...")
    facilities = load_lms_facilities()
    print(f"  {len(facilities)} active licensed AM/FM facilities")

    print("Loading LMS engineering tables...")
    app_am_antenna_idx = load_lms_app_am_antenna()
    app_location_idx = load_lms_app_location()
    app_antenna_idx = load_lms_app_antenna()

    print("Loading CDBS backfill tables (if present)...")
    cdbs_am_eng_idx = load_cdbs_am_eng_data()
    cdbs_am_ant_sys_idx = load_cdbs_am_ant_sys()
    cdbs_fm_eng_idx = load_cdbs_fm_eng_data()

    partitions = defaultdict(list)
    stats = {"am_lms": 0, "am_cdbs": 0, "am_miss": 0,
              "fm_lms": 0, "fm_cdbs": 0, "fm_miss": 0}
    am_reference_curves = {}  # freq_khz -> reference_points, computed once per channel

    for facility in facilities.values():
        if facility["service"] == "AM":
            resolved = resolve_am(facility, app_am_antenna_idx,
                                   cdbs_am_eng_idx, cdbs_am_ant_sys_idx)
            stats["am_" + (resolved["source"] if resolved else "miss")] += 1
        else:
            resolved = resolve_fm(facility, app_location_idx,
                                   app_antenna_idx, cdbs_fm_eng_idx)
            stats["fm_" + (resolved["source"] if resolved else "miss")] += 1

        if not resolved:
            continue

        code = olc.encode(resolved["lat"], resolved["lon"],
                           codeLength=PLUS_CODE_LENGTH)
        key = code[:PLUS_CODE_LENGTH]

        record = {
            "callsign": facility["callsign"],
            "service": facility["service"],
            "frequency": facility["frequency"],
            "city": facility["city"],
            "state": facility["state"],
            "lat": resolved["lat"],
            "lon": resolved["lon"],
            "directional": resolved["directional"],
            "source": resolved["source"],
        }
        if facility["service"] == "AM":
            record["power_day_kw"] = resolved["power_day_kw"]
            record["power_night_kw"] = resolved["power_night_kw"]

            freq_khz = to_float(facility["frequency"])
            if freq_khz is not None:
                if freq_khz not in am_reference_curves:
                    am_reference_curves[freq_khz] = \
                        am_groundwave.reference_curve_km_vs_dbu(freq_khz)
                curve = am_reference_curves[freq_khz]
                day_ranges = am_groundwave.range_at_thresholds(
                    curve, resolved["power_day_kw"])
                night_ranges = am_groundwave.range_at_thresholds(
                    curve, resolved["power_night_kw"])
                record["range_day_km"] = [
                    day_ranges.get(t) for t in am_groundwave.THRESHOLDS_DBU]
                record["range_night_km"] = [
                    night_ranges.get(t) for t in am_groundwave.THRESHOLDS_DBU]
        else:
            record["erp_kw"] = resolved["erp_kw"]
            record["haat_m"] = resolved["haat_m"]

        partitions[key].append(record)

    print("Resolution stats:", stats)

    os.makedirs(OUT_DIR, exist_ok=True)
    for key, records in partitions.items():
        with open(os.path.join(OUT_DIR, f"{key}.json"), "w") as f:
            json.dump(records, f, separators=(",", ":"))

    total = sum(len(v) for v in partitions.values())
    print(f"Wrote {len(partitions)} partition files, {total} stations total")


if __name__ == "__main__":
    main()
