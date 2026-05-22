"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
TLE Acquisition and Validation Pipeline

=======================================================================
PURPOSE
=======================================================================
This file owns the boundary between IOLA's orbital state engine and
the external world. It fetches Two-Line Element sets from CelesTrak,
validates their structure rigorously, and writes them atomically to
disk. Nothing else touches this ingestion boundary.

A TLE (Two-Line Element set) is the standard format for encoding a
satellite's orbital elements — the six parameters that fully describe
its orbit at a given epoch. Published by USSPACECOM and distributed
by CelesTrak. Format defined by NORAD, designed for punch cards, and
strict about every character position.

=======================================================================
VALIDATION CONTRACT
=======================================================================
A TLE catalog is accepted only if ALL of the following hold:
  1. No CelesTrak cooldown message in the response
  2. At least MIN_SATELLITES * 3 non-empty lines
  3. Total non-empty line count divisible by 3
  4. Every name line does NOT start with "1 " or "2 "
  5. Every TLE line 1 starts with "1 "
  6. Every TLE line 2 starts with "2 "

=======================================================================
ATOMICITY
=======================================================================
Writes are staged to a .tmp file and committed with os.replace().
os.replace() is atomic on POSIX systems — the operational catalog is
never in a partially-written state. If the process dies mid-write, the
existing active.tle is untouched.

=======================================================================
COOLDOWN HANDLING
=======================================================================
CelesTrak rate-limits repeated requests by returning a plain-text
message instead of TLE data. This is detected by string match and
treated as a silent skip — the existing catalog remains valid.
"""

import os
import httpx
from dotenv import load_dotenv
from propagate import reset_sgp4_error_log

load_dotenv()

# -----------------------------------------------------------------------
# File paths for the operational catalog and the staging file.
# The staging file is written first; os.replace() promotes it atomically.
# -----------------------------------------------------------------------
TLE_FILE_PATH      = "../data/active.tle"
TLE_STAGING_PATH   = "../data/active.tle.tmp"

# -----------------------------------------------------------------------
# Validation thresholds
# -----------------------------------------------------------------------
MIN_SATELLITES_REQUIRED = 100   # Reject any catalog with fewer than this

# -----------------------------------------------------------------------
# CelesTrak returns this string instead of TLE data when rate-limited.
# -----------------------------------------------------------------------
CELESTRAK_COOLDOWN_MARKER = "GP data has not been updated"


def _validate_tle_structure(raw_tle_text):
    """
    Validate the structure of a raw TLE catalog string.

    Checks line count, divisibility, and that each triplet has the
    correct prefix pattern (name, "1 ...", "2 ...").

    Parameters
    ----------
    raw_tle_text : str — raw text response from CelesTrak

    Returns
    -------
    bool — True if the catalog passes all structural checks
    """
    non_empty_lines = [
        line for line in raw_tle_text.strip().splitlines() if line.strip()
    ]

    if len(non_empty_lines) < MIN_SATELLITES_REQUIRED * 3:
        return False
    if len(non_empty_lines) % 3 != 0:
        return False

    for triplet_start in range(0, len(non_empty_lines), 3):
        name_line = non_empty_lines[triplet_start]
        tle_line1 = non_empty_lines[triplet_start + 1]
        tle_line2 = non_empty_lines[triplet_start + 2]

        # Name line must never look like a TLE numeric line
        if name_line.startswith("1 ") or name_line.startswith("2 "):
            return False
        if not tle_line1.startswith("1 "):
            return False
        if not tle_line2.startswith("2 "):
            return False

    return True


def fetch_tle():
    """
    Fetch the active satellite TLE catalog from CelesTrak and write it
    to disk if it passes structural validation.

    Reads CELESTRAK_URL from environment. Writes atomically via staging
    file. Skips silently on cooldown or validation failure.
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

    # Atomic write: stage → validate → replace
    with open(TLE_STAGING_PATH, "w") as staging_file:
        staging_file.write(raw_tle_text)
    os.replace(TLE_STAGING_PATH, TLE_FILE_PATH)

    satellite_count = (
        len([l for l in raw_tle_text.strip().splitlines() if l.strip()]) // 3
    )
    print(f"TLE catalog refreshed: {satellite_count} satellites")
    reset_sgp4_error_log()
