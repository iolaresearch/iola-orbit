"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Service Startup and Thread Orchestration

=======================================================================
PURPOSE
=======================================================================
Defines startup order and background thread lifecycle for the Phase 1
orbital simulation service.

=======================================================================
STARTUP ORDER (critical — do not change)
=======================================================================
  1. fetch_tle()           — populate active.tle before any propagation
  2. propagate_satellites() — populate satellite cache before API starts
  3. Start propagation thread — updates cache every 15 seconds
  4. Start TLE refresh thread — refreshes catalog every 2 hours
  5. Start uvicorn          — API is now safe to serve requests

The API must never be exposed before step 2 completes. A request
arriving before propagation would return an empty satellite list.

=======================================================================
THREAD DESIGN
=======================================================================
Both threads sleep FIRST, then execute. The initial state comes from
the synchronous calls in steps 1 and 2 above. This avoids a double
propagation on startup and ensures the sleep interval is measured from
after each operation completes, not from when the thread was created.

The TLE refresh thread calls propagate_satellites() immediately after
a successful fetch so the cache reflects the new catalog within seconds
rather than waiting for the next propagation tick.

Both threads are daemon threads — they are killed automatically when
the main process exits. No cleanup is required.
"""

import os
import time
import threading
import uvicorn
from api import app
from fetch_tle import fetch_tle
from propagate import propagate_satellites

PROPAGATION_INTERVAL_SECONDS = 15
TLE_REFRESH_INTERVAL_SECONDS  = 7200   # 2 hours


def _propagation_loop():
    """Background thread: propagate all satellites every 15 seconds."""
    while True:
        time.sleep(PROPAGATION_INTERVAL_SECONDS)
        propagate_satellites()


def _tle_refresh_loop():
    """
    Background thread: refresh TLE catalog every 2 hours.
    Immediately re-propagates after a successful refresh so the cache
    reflects the new orbital elements without waiting for the next tick.
    """
    while True:
        time.sleep(TLE_REFRESH_INTERVAL_SECONDS)
        fetch_tle()
        propagate_satellites()


# -----------------------------------------------------------------------
# Synchronous initialisation — must complete before threads start
# -----------------------------------------------------------------------
fetch_tle()
propagate_satellites()

# -----------------------------------------------------------------------
# Background threads
# -----------------------------------------------------------------------
threading.Thread(target=_propagation_loop, daemon=True).start()
threading.Thread(target=_tle_refresh_loop,  daemon=True).start()

# -----------------------------------------------------------------------
# API server — started last, after cache is populated
# -----------------------------------------------------------------------
uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
