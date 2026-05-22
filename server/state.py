"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Shared Orbital State

=======================================================================
PURPOSE
=======================================================================
Holds the parsed Satrec objects and satellite metadata parsed from
the TLE catalog. Shared between fetch_tle.py (writes) and api.py
(reads).

Architecture (on-demand propagation):
  - fetch_tle.py parses the TLE catalog into Satrec objects on each
    successful refresh and stores them here.
  - api.py reads satrec_catalog and propagates every satellite to
    datetime.now() on each GET /satellites request.
  - No background propagation thread. No cache staleness. No 15-second
    delay. Positions are always exact for the moment of the request.

=======================================================================
WHY THIS REPLACED THE CACHE APPROACH
=======================================================================
The previous architecture maintained a satellite_cache list that was
refreshed every 15 seconds by a background thread. This introduced:
  - Cache staleness (up to 15s + network latency = stale positions)
  - BUG-012: clear() + extend() empty-cache window
  - Test 1 timing artifact (comparing positions from different epochs)
  - propagated_at complexity to work around the staleness

Profiling showed 15,000 SGP4 evaluations take 9ms on the Render
free tier. On-demand propagation per request costs 9ms of latency.
This is a better trade than 15 seconds of position staleness.

The TLE parsing (Satrec.twoline2rv) is the expensive part — it parses
orbital element strings into numeric structures. This happens once per
TLE refresh (every 2 hours), not once per request. Each request then
runs only the 9ms evaluation loop.

=======================================================================
THREAD SAFETY
=======================================================================
satrec_catalog is replaced atomically via slice assignment on refresh.
api.py reads it under a consistent snapshot since the list replacement
is a single C-level operation under the CPython GIL.
"""

# List of dicts: {name, norad_id, tle_line1, tle_line2, satrec, bstar, epoch}
# Populated by fetch_tle.py after each successful TLE refresh.
# Read by api.py on every GET /satellites request.
satrec_catalog = []
