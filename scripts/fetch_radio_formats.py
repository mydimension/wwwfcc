"""Fetch station format/genre tags (e.g. "classic rock", "talk radio")
from Wikidata, keyed by FCC Facility ID.

The FCC's own LMS/CDBS data has no format field at all - format is a
business decision, not something the FCC regulates or tracks. Wikidata
carries it as property P415 ("radio format") on ~18% of US radio
station items (2,748 of ~15,900 as of this writing) - the rest just
have no format recorded, same shape as the CDBS engineering-data gap
parse_stations.py already backfills/tolerates.

Joined on P1400 ("FCC Facility ID"), not callsign (P2317): facility_id
is on 98% of the format-tagged items vs. only 61% for callsign, and it's
the same stable identifier parse_stations.py already uses to join
CDBS<->LMS (see that file's docstring). A callsign join would silently
drop over a third of the otherwise-available matches.

Wikidata content is CC0 (public domain) - no attribution requirement,
no API key, no rate-limit concerns for a query this size (single
request, a few thousand rows).

This mirrors fetch_cdbs_data.py/fetch_lms_data.py: pure network fetch,
writes one local JSON file, no parsing of FCC tables. parse_stations.py
loads that file and merges it in by facility_id.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://query.wikidata.org/sparql"

QUERY = """
SELECT ?facilityId (GROUP_CONCAT(DISTINCT ?fmtLabel; separator="|") AS ?formats) WHERE {
  ?station wdt:P31 wd:Q14350 ; wdt:P17 wd:Q30 ; wdt:P1400 ?facilityId ; wdt:P415 ?fmt .
  ?fmt rdfs:label ?fmtLabel . FILTER(LANG(?fmtLabel)="en")
} GROUP BY ?facilityId
"""

OUT_DIR = os.environ.get("WIKIDATA_RAW_DIR", "raw_wikidata")
OUT_PATH = os.path.join(OUT_DIR, "radio_formats.json")


def fetch_formats():
    url = f"{ENDPOINT}?{urllib.parse.urlencode({'query': QUERY})}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            # Wikidata asks bulk/bot clients to self-identify.
            "User-Agent": "wwwfcc-radio-coverage-map/1.0 (github.com project; personal non-commercial use)",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)

    formats = {}
    for row in data["results"]["bindings"]:
        facility_id = row["facilityId"]["value"]
        formats[facility_id] = row["formats"]["value"].split("|")
    return formats


def main():
    try:
        formats = fetch_formats()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        # Enrichment is optional - a Wikidata hiccup shouldn't break the
        # weekly FCC data build. parse_stations.py treats a missing file
        # the same as "no format data available".
        print(f"radio format fetch failed, continuing without it: {e}")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(formats, f, separators=(",", ":"))
    print(f"fetched formats for {len(formats)} facility IDs")


if __name__ == "__main__":
    main()
