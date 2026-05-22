"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Service Startup and Thread Orchestration

=======================================================================
STARTUP ORDER
=======================================================================
  1. load_tle_from_disk()  — parse seed active.tle into satrec_catalog
  2. fetch_tle()           — fetch fresh catalog from CelesTrak,
                             re-parse and replace satrec_catalog
  3. Start TLE refresh thread — re-fetches and re-parses every 2 hours
  4. Start uvicorn         — API is now safe to serve requests

There is no propagation thread. Propagation runs on-demand inside
GET /satellites (9ms per call). Zero staleness. No background state.

=======================================================================
TLE REFRESH THREAD
=======================================================================
Sleeps 7200s (2 hours) then fetches, validates, writes to disk,
parses into Satrec objects, and replaces state.satrec_catalog.
The sleep-first pattern means the interval is measured from after
each operation completes, not from thread creation time.
"""

import os
import time
import threading
import uvicorn
from api import app
from fetch_tle import fetch_tle, load_tle_from_disk

TLE_REFRESH_INTERVAL_SECONDS = 7200   # 2 hours


def _tle_refresh_loop():
    """Background thread: refresh and re-parse TLE catalog every 2 hours."""
    while True:
        time.sleep(TLE_REFRESH_INTERVAL_SECONDS)
        fetch_tle()


# -----------------------------------------------------------------------
# Synchronous initialisation
# -----------------------------------------------------------------------
load_tle_from_disk()   # parse seed file immediately — API can serve at once
fetch_tle()            # fetch fresh catalog from CelesTrak, replace if valid

# -----------------------------------------------------------------------
# Background thread
# -----------------------------------------------------------------------
threading.Thread(target=_tle_refresh_loop, daemon=True).start()

# -----------------------------------------------------------------------
# API server
# -----------------------------------------------------------------------
uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
