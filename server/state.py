"""
IKIRERE ORBITAL LABS AFRICA — PHASE 1
Shared Orbital State Cache

=======================================================================
PURPOSE
=======================================================================
Single shared list that decouples the propagation engine from the API.

Write path:  propagate.py  → replaces satellite_cache contents atomically
Read path:   api.py        → returns satellite_cache on GET /satellites

=======================================================================
WRITE ATOMICITY
=======================================================================
The write uses slice assignment:

    satellite_cache[:] = new_list

This mutates the existing list object in place rather than replacing
the reference. CPython executes list slice assignment as a single
C-level operation under the GIL, making it atomic for our single-
process use case. There is no window where the cache is empty.

The previous pattern (clear() + extend()) had a window between the
two calls where any API request would return an empty list. That
pattern was replaced on 2026-05-22. See phase1_engineering_notes.md,
BUG-012 / Q3 resolution.

=======================================================================
FUTURE MIGRATION
=======================================================================
When the platform scales to multiple workers, replace with a Redis
cache. Only this file and the two import sites change.
"""

satellite_cache    = []
last_propagated_at = None   # ISO 8601 UTC string, set by propagate.py on each run
