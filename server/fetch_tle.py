"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
TLE Acquisition, Validation, and Catalog Parsing Pipeline

=======================================================================
PURPOSE
=======================================================================
This file owns two responsibilities:

1. Fetch and validate the TLE catalog from CelesTrak (unchanged).
2. Parse the validated catalog into Satrec objects and store them in
   state.satrec_catalog for on-demand propagation by api.py.

Parsing (Satrec.twoline2rv) is the CPU-expensive part of the orbital
pipeline — it converts TLE string representations into numeric orbital
element structures. Doing this once per 2-hour refresh rather than on
every request is the correct separation of work.

=======================================================================
VALIDATION CONTRACT (unchanged)
=======================================================================
A TLE catalog is accepted only if ALL hold:
  1. No CelesTrak cooldown message in the response
  2. At least MIN_SATELLITES_REQUIRED * 3 non-empty lines
  3. Total non-empty line count divisible by 3
  4. Every name line does NOT start with "1 " or "2 "
  5. Every TLE line 1 starts with "1 "
  6. Every TLE line 2 starts with "2 "

=======================================================================
ATOMICITY
=======================================================================
File write is staged via .tmp + os.replace() (atomic on POSIX).
satrec_catalog is replaced via slice assignment (atomic under GIL).
"""

import os
import httpx
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from sgp4.api import Satrec
import state
from propagate import reset_sgp4_error_log

load_dotenv()

TLE_FILE_PATH             = "../data/active.tle"
TLE_STAGING_PATH          = "../data/active.tle.tmp"
MIN_SATELLITES_REQUIRED   = 100
CELESTRAK_COOLDOWN_MARKER = "GP data has not been updated"


def _epoch_to_iso(tle_epoch_year, tle_epoch_days):
    """
    Convert TLE epoch (two-digit year + day-of-year fraction) to ISO 8601 UTC.

    TLE epoch year convention:
      57-99 -> 1957-1999
      00-56 -> 2000-2056
    """
    full_year = int(tle_epoch_year) + (2000 if tle_epoch_year < 57 else 1900)
    epoch_dt  = (
        datetime(full_year, 1, 1, tzinfo=timezone.utc)
        + timedelta(days=tle_epoch_days - 1)
    )
    return epoch_dt.isoformat()


def _validate_tle_structure(raw_tle_text):
    """
    Validate the structural integrity of a raw TLE catalog string.
    Returns True only if every triplet has the correct prefix pattern.
    """
    lines = [l for l in raw_tle_text.strip().splitlines() if l.strip()]

    if len(lines) < MIN_SATELLITES_REQUIRED * 3:
        return False
    if len(lines) % 3 != 0:
        return False

    for i in range(0, len(lines), 3):
        if lines[i].startswith("1 ") or lines[i].startswith("2 "):
            return False
        if not lines[i + 1].startswith("1 "):
            return False
        if not lines[i + 2].startswith("2 "):
            return False

    return True


def _parse_catalog_into_satrecs(raw_tle_text):
    """
    Parse a validated TLE catalog into Satrec objects.

    This is called once per successful TLE refresh. The parsed objects
    are stored in state.satrec_catalog and reused on every subsequent
    GET /satellites request until the next refresh.

    Each entry in the returned list contains:
      name      — satellite name string
      norad_id  — 5-digit NORAD catalog number string
      epoch     — ISO 8601 UTC of TLE measurement epoch
      satrec    — parsed Satrec object (ready for sgp4 evaluation)
      bstar     — atmospheric drag coefficient
      tle_line1 — raw TLE line 1 (preserved for Phase 2 TCA refinement)
      tle_line2 — raw TLE line 2 (preserved for Phase 2 TCA refinement)
    """
    lines   = [l for l in raw_tle_text.strip().splitlines() if l.strip()]
    catalog = []
    skipped = 0

    for i in range(0, len(lines) - 2, 3):
        name      = lines[i].strip()
        tle_line1 = lines[i + 1].strip()
        tle_line2 = lines[i + 2].strip()
        norad_id  = tle_line1[2:7].strip()

        try:
            satrec = Satrec.twoline2rv(tle_line1, tle_line2)
            catalog.append({
                "name":      name,
                "norad_id":  norad_id,
                "epoch":     _epoch_to_iso(satrec.epochyr, satrec.epochdays),
                "satrec":    satrec,
                "bstar":     satrec.bstar,
                "tle_line1": tle_line1,
                "tle_line2": tle_line2,
            })
        except Exception as parse_error:
            print(f"TLE parse failed for NORAD {norad_id}: {parse_error} — skipped")
            skipped += 1

    if skipped:
        print(f"TLE parsing: {skipped} entries skipped due to parse errors")

    return catalog


def fetch_tle():
    """
    Fetch the active satellite TLE catalog from CelesTrak.

    On success:
      - Writes catalog atomically to disk (active.tle)
      - Parses catalog into Satrec objects (state.satrec_catalog)
      - Resets the SGP4 error suppression log (new catalog = fresh start)
    """
    celestrak_url = os.getenv("CELESTRAK_URL")

    try:
        response = httpx.get(
            celestrak_url,
            headers={"User-Agent": "iola-orbit/1.0"},
            follow_redirects=True,
            timeout=30
        )
        response.raise_for_status()
    except Exception as network_error:
        print(f"TLE fetch failed: {network_error}")
        return

    raw_tle_text = response.text

    if CELESTRAK_COOLDOWN_MARKER in raw_tle_text:
        print("TLE refresh skipped: CelesTrak cooldown active.")
        return

    if not _validate_tle_structure(raw_tle_text):
        print("TLE refresh skipped: catalog failed structural validation.")
        return

    # Atomic file write
    with open(TLE_STAGING_PATH, "w") as staging_file:
        staging_file.write(raw_tle_text)
    os.replace(TLE_STAGING_PATH, TLE_FILE_PATH)

    # Parse into Satrec objects and replace catalog atomically
    new_catalog            = _parse_catalog_into_satrecs(raw_tle_text)
    state.satrec_catalog[:] = new_catalog

    satellite_count = len(new_catalog)
    print(f"TLE catalog refreshed and parsed: {satellite_count} satellites")
    reset_sgp4_error_log()


def load_tle_from_disk():
    """
    Parse the on-disk active.tle into state.satrec_catalog.
    Called once at startup to initialise the catalog from the committed
    seed file, before the first network fetch has run.
    """
    try:
        with open(TLE_FILE_PATH, "r") as f:
            raw_tle_text = f.read()
    except FileNotFoundError:
        print("WARNING: active.tle not found on disk — catalog empty until first fetch")
        return

    new_catalog             = _parse_catalog_into_satrecs(raw_tle_text)
    state.satrec_catalog[:] = new_catalog
    print(f"Catalog loaded from disk: {len(new_catalog)} satellites parsed")
