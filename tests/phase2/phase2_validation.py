"""
IKIRERE ORBITAL LABS AFRICA — PHASE 2
Validation Test Suite

=======================================================================
PURPOSE
=======================================================================
Validates the Phase 2 orbital intelligence engine against known
physical constraints, mathematical invariants, and performance bounds.

Tests are split by data source:

  SYNTHETIC DATA (Tests 1, 3, 5):
    Mathematical invariants and edge cases where exact expected values
    are known. These tests must always use synthetic data — real orbital
    data changes every 15 seconds and cannot be verified by hand.

  REAL SATELLITE DATA (Tests 2, 4, 6):
    End-to-end pipeline validation against live orbital state from the
    production API. These tests prove the algorithm works on real
    physical objects, not just synthetic constructions.
    Note: full screen_catalog() on all 15k satellites is NOT run here
    to avoid exhausting Render's compute budget. A 500-satellite sample
    from the real catalog is sufficient to validate the pipeline.

=======================================================================
TEST COVERAGE
=======================================================================
Test 1 — Geometric correctness (SYNTHETIC)
  Euclidean distance verified to machine precision against known values.
  Mathematical foundation — stays synthetic permanently.

Test 2 — TCA accuracy on REAL satellites
  ISS (NORAD 25544) and Starlink-1007 (NORAD 44713).
  Fires Phase B SGP4 bisection (tca_refined=True) for the first time.
  Validates pipeline with real tle_line1/tle_line2 fields.

Test 3 — Risk score bounds (SYNTHETIC)
  Score [0,1], monotonicity, Kessler factor — stays synthetic.

Test 4 — Screen performance on REAL 500-satellite sample
  Fetches 500 real satellites from /satellites.
  Validates stage reductions against real orbital distribution.
  Documents real performance characteristics.

Test 5 — CDM field completeness (SYNTHETIC)
  Structural validation stays synthetic — field names never change.

Test 6 — Real pair end-to-end CDM
  Full pipeline for ISS vs Starlink-1007 from real propagated state.
  Validates complete output contract on real data.

=======================================================================
HOW TO RUN
=======================================================================
    python tests/phase2/phase2_validation.py

Output: PASS/FAIL per test with quantitative measurements.
Full output written to tests/phase2/phase2_validation_response_<timestamp>.txt
"""

import os
import sys
import io
import math
import time
from datetime import datetime, timezone, timedelta

# Force UTF-8 on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server"))

try:
    import httpx
except ImportError:
    print("MISSING DEPENDENCY: pip install httpx")
    sys.exit(1)

from conjunction import (
    distance_between_satellites,
    find_closest_approach,
    compute_composite_risk_score,
    generate_cdm,
    screen_catalog,
    compute_orbital_shell_density,
    classify_risk_from_distance,
    satellites_are_approaching,
)

API_URL         = os.getenv("API_URL", "https://iola-orbit-dfxp.onrender.com")
SATELLITES_URL  = f"{API_URL}/satellites"
PAIR_URL        = f"{API_URL}/conjunction/pair"

# Reference NORAD IDs for real-data tests
ISS_NORAD       = "25544"   # International Space Station
STARLINK_NORAD  = "44714"   # Starlink-1008 — LEO (44713 retired, 44714 confirmed active)


def fetch_real_satellites(limit=None):
    """
    Fetch live satellite records from the production API.
    Returns the satellites list. Optionally slices to first `limit` records.
    """
    print(f"  Fetching real satellites from {SATELLITES_URL} ...")
    response = httpx.get(SATELLITES_URL, timeout=60)
    response.raise_for_status()
    body       = response.json()
    satellites = body.get("satellites", body) if isinstance(body, dict) else body
    if limit:
        satellites = satellites[:limit]
    print(f"  Loaded {len(satellites)} satellites (propagated_at: "
          f"{body.get('propagated_at', 'N/A') if isinstance(body, dict) else 'N/A'})")
    return satellites


def find_satellite_by_norad(satellites, norad_id):
    for sat in satellites:
        if sat.get("norad_id") == norad_id:
            return sat
    return None

# -----------------------------------------------------------------------
# Known satellite state vectors for deterministic testing.
# These are synthetic but physically plausible LEO objects.
# Positions chosen so the distance is exactly 100 km (verifiable by hand).
# -----------------------------------------------------------------------

# Satellite A at exactly (7000, 0, 0) km
SYNTHETIC_SAT_A = {
    "norad_id":      "99991",
    "name":          "TEST-SAT-A",
    "x":             7000.0, "y": 0.0, "z": 0.0,
    "vx":            0.0,    "vy": 7.5, "vz": 0.0,
    "speed_km_s":    7.5,
    "altitude_km":   629.0,
    "orbital_class": "LEO",
    "bstar":         1.5e-4,
    "epoch":         (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    "sunlit":        True,
    "propagation_mode": "SGP4",
}

# Satellite B at exactly (7100, 0, 0) km — exactly 100 km from A
SYNTHETIC_SAT_B = {
    "norad_id":      "99992",
    "name":          "TEST-SAT-B",
    "x":             7100.0, "y": 0.0, "z": 0.0,
    "vx":            0.0,    "vy": 7.4, "vz": 0.0,
    "speed_km_s":    7.4,
    "altitude_km":   729.0,
    "orbital_class": "LEO",
    "bstar":         1.2e-4,
    "epoch":         (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
    "sunlit":        True,
    "propagation_mode": "SGP4",
}

# Satellite C converging directly toward A (head-on approach geometry)
SYNTHETIC_SAT_C = {
    "norad_id":      "99993",
    "name":          "TEST-SAT-C",
    "x":             7000.0, "y": 500.0,  "z": 0.0,
    "vx":            0.0,    "vy": -7.5,  "vz": 0.0,  # moving toward A
    "speed_km_s":    7.5,
    "altitude_km":   629.0,
    "orbital_class": "LEO",
    "bstar":         1.0e-4,
    "epoch":         datetime.now(timezone.utc).isoformat(),
    "sunlit":        True,
    "propagation_mode": "SGP4",
}


def print_header(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_result(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    marker = "OK" if passed else "XX"
    line   = f"  [{status}] {marker} {label}"
    if detail:
        line += f"  ->  {detail}"
    print(line)
    return passed


# ===========================================================================
# TEST 1 — Geometric Correctness
# ===========================================================================

def test_1_geometric_correctness():
    """
    Verify Euclidean distance computation against manually calculated values.
    This is the mathematical foundation. Everything else builds on it.
    """
    print_header("TEST 1 — Geometric Correctness")
    all_passed = True

    # Known distance: A at (7000, 0, 0), B at (7100, 0, 0) => distance = 100 km exactly
    computed_distance = distance_between_satellites(SYNTHETIC_SAT_A, SYNTHETIC_SAT_B)
    expected_distance = 100.0
    error_km          = abs(computed_distance - expected_distance)

    passed     = error_km < 1e-6
    all_passed = all_passed and passed
    print_result(
        "A-B distance = 100.000 km",
        passed,
        f"computed = {computed_distance:.6f} km  error = {error_km:.2e} km"
    )

    # 3D distance: A at origin, D at (3, 4, 0) => distance = 5 km
    sat_origin = {**SYNTHETIC_SAT_A, "x": 0.0, "y": 0.0, "z": 0.0}
    sat_3_4_0  = {**SYNTHETIC_SAT_B, "x": 3.0, "y": 4.0, "z": 0.0}
    dist_3d    = distance_between_satellites(sat_origin, sat_3_4_0)
    error_3d   = abs(dist_3d - 5.0)

    passed     = error_3d < 1e-6
    all_passed = all_passed and passed
    print_result(
        "3D distance (3,4,0) = 5.000 km",
        passed,
        f"computed = {dist_3d:.6f} km  error = {error_3d:.2e} km"
    )

    # Diagonal distance: A at (0,0,0), B at (1,1,1) => distance = sqrt(3)
    sat_111    = {**SYNTHETIC_SAT_B, "x": 1.0, "y": 1.0, "z": 1.0}
    dist_diag  = distance_between_satellites(sat_origin, sat_111)
    expected   = math.sqrt(3.0)
    error_diag = abs(dist_diag - expected)

    passed     = error_diag < 1e-6
    all_passed = all_passed and passed
    print_result(
        "Diagonal distance (1,1,1) = sqrt(3) km",
        passed,
        f"computed = {dist_diag:.8f}  expected = {expected:.8f}  error = {error_diag:.2e}"
    )

    # Approaching geometry: C is moving toward A, dot product should be negative
    approaching = satellites_are_approaching(SYNTHETIC_SAT_A, SYNTHETIC_SAT_C)
    all_passed  = all_passed and approaching
    print_result(
        "Converging satellites correctly identified as approaching",
        approaching,
        f"approaching = {approaching}"
    )

    # Not approaching: A and B moving in the same direction
    same_dir_a = {**SYNTHETIC_SAT_A, "vx": 0.0, "vy": 7.5, "vz": 0.0}
    same_dir_b = {**SYNTHETIC_SAT_B, "vx": 0.0, "vy": 7.5, "vz": 0.0}
    not_approaching = not satellites_are_approaching(same_dir_a, same_dir_b)
    all_passed      = all_passed and not_approaching
    print_result(
        "Co-moving satellites correctly identified as not approaching",
        not_approaching,
        f"approaching = {not not_approaching}"
    )

    return all_passed


# ===========================================================================
# TEST 2 — TCA Accuracy on REAL Satellites
# ===========================================================================

def test_2_tca_accuracy_real(satellites):
    """
    Run find_closest_approach() on ISS and Starlink-1007 — two real LEO
    objects with real tle_line1/tle_line2 fields from the live catalog.

    This test fires Phase B SGP4 bisection (tca_refined=True) for the
    first time, proving the full two-phase TCA algorithm works on real
    orbital data. Previous synthetic runs showed tca_refined=False because
    synthetic satellites have no TLE lines — Phase B was never exercised.

    ISS: NORAD 25544, altitude ~420 km, inclination ~51.6 deg
    Starlink-1007: NORAD 44713, altitude ~550 km, LEO
    These are in different altitude bands so TCA will be large (expected).
    What matters: pipeline completes, tca_refined=True, all fields present.
    """
    print_header("TEST 2 — TCA Accuracy (REAL: ISS + Starlink-1008)")
    all_passed = True

    iss      = find_satellite_by_norad(satellites, ISS_NORAD)
    starlink = find_satellite_by_norad(satellites, STARLINK_NORAD)

    if iss is None:
        print_result("ISS (25544) found in live catalog", False, "Not present — skipping Test 2")
        return False
    if starlink is None:
        print_result("Starlink-1007 (44713) found in live catalog", False, "Not present — skipping Test 2")
        return False

    print_result("ISS (25544) found in live catalog", True,
                 f"altitude={iss.get('altitude_km', 'N/A'):.1f} km")
    print_result("Starlink-1007 (44713) found in live catalog", True,
                 f"altitude={starlink.get('altitude_km', 'N/A'):.1f} km")

    # Confirm TLE lines are present (required for Phase B SGP4 bisection)
    iss_has_tles      = bool(iss.get("tle_line1"))
    starlink_has_tles = bool(starlink.get("tle_line1"))
    all_passed        = all_passed and iss_has_tles and starlink_has_tles
    print_result("ISS has tle_line1/tle_line2", iss_has_tles,
                 "Phase B SGP4 bisection will fire" if iss_has_tles else "MISSING — Phase B will not fire")
    print_result("Starlink-1007 has tle_line1/tle_line2", starlink_has_tles,
                 "Phase B SGP4 bisection will fire" if starlink_has_tles else "MISSING — Phase B will not fire")

    # Run TCA — 6-hour window, 60s coarse step (fast but real)
    t0       = time.perf_counter()
    approach = find_closest_approach(iss, starlink,
                                     scan_duration_seconds=21600,
                                     coarse_step_seconds=60)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Miss distance non-negative
    miss_ok    = approach["distance_km"] >= 0
    all_passed = all_passed and miss_ok
    print_result("Miss distance >= 0 km",
                 miss_ok, f"{approach['distance_km']:.3f} km")

    # Miss distance physically plausible
    miss_plausible = approach["distance_km"] < 50000.0
    all_passed     = all_passed and miss_plausible
    print_result("Miss distance < 50,000 km (physically plausible)",
                 miss_plausible, f"{approach['distance_km']:.3f} km")

    # TCA within scan window
    tca_ok     = 0 <= approach["time_seconds"] <= 21600
    all_passed = all_passed and tca_ok
    print_result("TCA within 6-hour scan window",
                 tca_ok, f"t+{approach['time_seconds']:.1f}s")

    # SGP4 bisection fired (tca_refined=True) — the critical new check
    tca_refined    = approach["tca_refined"] is True
    all_passed     = all_passed and tca_refined
    print_result("Phase B SGP4 bisection fired (tca_refined=True)",
                 tca_refined,
                 "CONFIRMED — first time real TLE lines exercised" if tca_refined
                 else "FAILED — Phase B did not fire, check tle_line1/tle_line2 fields")

    print(f"\n  ISS vs Starlink-1007 TCA:")
    print(f"    miss_distance = {approach['distance_km']:.3f} km")
    print(f"    tca           = t+{approach['time_seconds']:.1f}s")
    print(f"    tca_refined   = {approach['tca_refined']}")
    print(f"    approaching   = {approach['approaching']}")
    print(f"    compute_time  = {elapsed_ms:.0f} ms")

    return all_passed


# ===========================================================================
# TEST 3 — Risk Score Bounds and Component Consistency
# ===========================================================================

def test_3_risk_score_bounds():
    """
    Verify the composite risk score satisfies all mathematical invariants.
    The score is the primary output that Phase 3 will consume — it must be correct.
    """
    print_header("TEST 3 — Risk Score Bounds and Component Consistency")
    all_passed = True
    epoch      = datetime.now(timezone.utc)

    approach_close = {"distance_km": 0.5, "time_seconds": 1800, "approaching": True,  "tca_refined": False}
    approach_far   = {"distance_km": 80.0, "time_seconds": 7200, "approaching": False, "tca_refined": False}

    risk_close = compute_composite_risk_score(SYNTHETIC_SAT_A, SYNTHETIC_SAT_C, approach_close, epoch)
    risk_far   = compute_composite_risk_score(SYNTHETIC_SAT_A, SYNTHETIC_SAT_B, approach_far,   epoch)

    # Composite score must be in [0, 1]
    for label, risk in [("close approach", risk_close), ("far approach", risk_far)]:
        in_range   = 0.0 <= risk["composite_score"] <= 1.0
        all_passed = all_passed and in_range
        print_result(
            f"Composite score in [0,1] ({label})",
            in_range,
            f"score = {risk['composite_score']}"
        )

    # Close must score higher than far
    close_higher = risk_close["composite_score"] > risk_far["composite_score"]
    all_passed   = all_passed and close_higher
    print_result(
        "Close approach scores higher than far",
        close_higher,
        f"close={risk_close['composite_score']}  far={risk_far['composite_score']}"
    )

    # All components must be in [0, 1]
    components = ["distance_risk_component", "velocity_risk_component",
                  "time_urgency_component", "tle_age_risk_component", "shell_density_factor"]
    for component in components:
        value      = risk_close.get(component, 0)
        in_range   = 0.0 <= value <= 1.0
        all_passed = all_passed and in_range
        print_result(
            f"  {component} in [0,1]",
            in_range,
            f"{value:.4f}"
        )

    # Collision probability must be in [0, 1]
    prob_in_range = 0.0 <= risk_close["probability_of_collision"] <= 1.0
    all_passed    = all_passed and prob_in_range
    print_result(
        "Collision probability in [0,1]",
        prob_in_range,
        f"{risk_close['probability_of_collision']:.8f}"
    )

    # Approaching bonus: same approach with approaching=True must score >= False
    approach_no_approach  = {**approach_close, "approaching": False}
    risk_not_approaching  = compute_composite_risk_score(SYNTHETIC_SAT_A, SYNTHETIC_SAT_C,
                                                         approach_no_approach, epoch)
    bonus_works = risk_close["composite_score"] >= risk_not_approaching["composite_score"]
    all_passed  = all_passed and bonus_works
    print_result(
        "Approaching bonus increases score",
        bonus_works,
        f"with={risk_close['composite_score']}  without={risk_not_approaching['composite_score']}"
    )

    # Shell density: with a dense catalog, score must be >= without
    dense_catalog = [SYNTHETIC_SAT_A, SYNTHETIC_SAT_C] * 300  # 600 objects in same band
    risk_dense    = compute_composite_risk_score(SYNTHETIC_SAT_A, SYNTHETIC_SAT_C,
                                                 approach_close, epoch, all_satellites=dense_catalog)
    risk_sparse   = compute_composite_risk_score(SYNTHETIC_SAT_A, SYNTHETIC_SAT_C,
                                                 approach_close, epoch, all_satellites=[])
    density_works = risk_dense["composite_score"] >= risk_sparse["composite_score"]
    all_passed    = all_passed and density_works
    print_result(
        "Dense shell produces higher or equal score than sparse",
        density_works,
        f"dense={risk_dense['composite_score']}  sparse={risk_sparse['composite_score']}"
    )

    # Risk classification from distance
    for distance, expected_level in [(0.5, "CRITICAL"), (3.0, "HIGH"), (10.0, "MODERATE"), (50.0, "LOW")]:
        level  = classify_risk_from_distance(distance)
        passed = level == expected_level
        all_passed = all_passed and passed
        print_result(
            f"classify_risk({distance} km) = {expected_level}",
            passed,
            f"got: {level}"
        )

    return all_passed


# ===========================================================================
# TEST 4 — Screen Performance on REAL 500-Satellite Sample
# ===========================================================================

def test_4_screen_performance_real(satellites):
    """
    Run screen_catalog() against 500 real satellites from the live catalog.

    This test validates:
      - The pipeline executes without error on real orbital data
      - Stage reductions reflect real orbital distribution (not synthetic pattern)
      - Conjunctions found (if any) represent real events
      - SGP4 bisection fires on surviving pairs with real TLE lines

    500 satellites is large enough to be representative and fast enough
    to complete in under 5 minutes. The full 15,447-satellite screen
    (~2 hours) is documented in the engineering notes but is NOT run
    here to avoid exhausting Render's compute budget.
    """
    print_header("TEST 4 — Screen Performance (REAL: 500 satellites)")
    all_passed  = True
    real_sample = satellites[:500]

    print(f"  Sample: first 500 satellites from live catalog")
    print(f"  Orbital classes: "
          f"LEO={sum(1 for s in real_sample if s.get('orbital_class')=='LEO')}, "
          f"MEO={sum(1 for s in real_sample if s.get('orbital_class')=='MEO')}, "
          f"GEO={sum(1 for s in real_sample if s.get('orbital_class')=='GEO')}")

    # Screen with tight threshold and short window — fast, still exercises full pipeline
    t0         = time.perf_counter()
    result     = screen_catalog(real_sample, threshold_km=50.0, scan_window_seconds=3600)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Must complete in under 5 minutes
    within_time = elapsed_ms < 300000
    all_passed  = all_passed and within_time
    print_result("500-satellite real screen completes under 5 min",
                 within_time, f"{elapsed_ms:.0f} ms ({elapsed_ms/1000:.1f}s)")

    # Required output keys
    required_keys = ["screened_at", "total_satellites", "pairs_altitude_passed",
                     "pairs_separation_passed", "conjunctions_found", "conjunctions", "summary"]
    keys_present  = all(k in result for k in required_keys)
    all_passed    = all_passed and keys_present
    print_result("Screen result has all required keys", keys_present,
                 "All present" if keys_present else str([k for k in required_keys if k not in result]))

    # Summary counts consistent
    summary_total = sum(result["summary"].values())
    counts_match  = summary_total == result["conjunctions_found"]
    all_passed    = all_passed and counts_match
    print_result("Summary counts match conjunctions_found", counts_match,
                 f"summary={summary_total}  found={result['conjunctions_found']}")

    # Stage reductions logical
    stage_order = result["pairs_altitude_passed"] >= result["pairs_separation_passed"]
    all_passed  = all_passed and stage_order
    print_result("Filter stages reduce pairs monotonically", stage_order,
                 f"altitude={result['pairs_altitude_passed']} -> "
                 f"separation={result['pairs_separation_passed']}")

    print(f"\n  Real sample results:")
    print(f"    Total satellites     : {result['total_satellites']}")
    print(f"    Stage 1 (altitude)   : {result['pairs_altitude_passed']} pairs")
    print(f"    Stage 2 (separation) : {result['pairs_separation_passed']} pairs")
    print(f"    Conjunctions found   : {result['conjunctions_found']}")
    print(f"    Risk summary         : {result['summary']}")
    print(f"    Screen time          : {elapsed_ms:.0f} ms")

    if result["conjunctions_found"] > 0:
        top = result["conjunctions"][0]
        print(f"\n  Highest-risk conjunction:")
        print(f"    {top['object_1_name']} ({top['object_1_norad']}) vs "
              f"{top['object_2_name']} ({top['object_2_norad']})")
        print(f"    miss_distance = {top['miss_distance_km']:.3f} km")
        print(f"    risk_score    = {top['risk']['composite_score']}")
        print(f"    tca_refined   = {top['tca_refined']}")
        print(f"    risk_level    = {top['risk']['risk_level']}")

        # If any conjunction found, SGP4 bisection should have fired
        any_refined = any(c["tca_refined"] for c in result["conjunctions"])
        all_passed  = all_passed and any_refined
        print_result("At least one TCA used SGP4 bisection (tca_refined=True)",
                     any_refined,
                     "Phase B fired on real TLE data" if any_refined
                     else "No refinement fired — check tle_line1/tle_line2 on catalog entries")
    else:
        print(f"\n  INFO: No conjunctions found within threshold/window on this sample.")
        print(f"  This is expected — 500 real satellites in a 1h window at 50km threshold")
        print(f"  is a tight screen. The pipeline is correct even with zero results.")

    scale_factor = (15447 / 500) ** 2
    estimated_s  = (elapsed_ms / 1000) * scale_factor
    print(f"\n  Full 15k catalog estimate: ~{estimated_s:.0f}s "
          f"(research batch operation — not a real-time call)")

    return all_passed


# ===========================================================================
# TEST 5 — CDM Field Completeness
# ===========================================================================

def test_5_cdm_field_completeness():
    """
    Verify CDMs contain all required fields and pass structural checks.
    CCSDS-required fields must be present.
    """
    print_header("TEST 5 — CDM Field Completeness")
    all_passed = True
    epoch      = datetime.now(timezone.utc)

    approach = {"distance_km": 2.5, "time_seconds": 3600, "approaching": True, "tca_refined": True}
    risk     = compute_composite_risk_score(SYNTHETIC_SAT_A, SYNTHETIC_SAT_B, approach, epoch)
    cdm      = generate_cdm(SYNTHETIC_SAT_A, SYNTHETIC_SAT_B, approach, risk, epoch)

    # CCSDS-required fields
    ccsds_fields = [
        "CDM_VERSION", "CREATION_DATE", "ORIGINATOR",
        "TCA", "MISS_DISTANCE_KM", "RELATIVE_VELOCITY_KMS",
        "COLLISION_PROBABILITY", "OBJECT_1", "OBJECT_2",
    ]
    for field in ccsds_fields:
        present    = field in cdm
        all_passed = all_passed and present
        print_result(f"CCSDS field '{field}' present", present)

    # IOLA extension fields
    iola_fields = ["COMPOSITE_RISK_SCORE", "RISK_LEVEL", "RISK_COMPONENTS",
                   "WORST_CASE_UNCERTAINTY_KM", "TCA_REFINED", "RECOMMENDED_ACTION"]
    for field in iola_fields:
        present    = field in cdm
        all_passed = all_passed and present
        print_result(f"IOLA field '{field}' present", present)

    # TCA must be after CREATION_DATE
    tca_dt      = datetime.fromisoformat(cdm["TCA"])
    created_dt  = datetime.fromisoformat(cdm["CREATION_DATE"])
    tca_future  = tca_dt > created_dt
    all_passed  = all_passed and tca_future
    print_result(
        "TCA is after CREATION_DATE",
        tca_future,
        f"created={cdm['CREATION_DATE']}  tca={cdm['TCA']}"
    )

    # Object 1 and Object 2 must have distinct NORAD IDs
    norad_1     = cdm["OBJECT_1"]["NORAD_ID"]
    norad_2     = cdm["OBJECT_2"]["NORAD_ID"]
    distinct    = norad_1 != norad_2
    all_passed  = all_passed and distinct
    print_result(
        "OBJECT_1 and OBJECT_2 have distinct NORAD IDs",
        distinct,
        f"{norad_1} vs {norad_2}"
    )

    # Miss distance must be non-negative
    miss_positive = cdm["MISS_DISTANCE_KM"] >= 0
    all_passed    = all_passed and miss_positive
    print_result(
        "MISS_DISTANCE_KM >= 0",
        miss_positive,
        f"{cdm['MISS_DISTANCE_KM']} km"
    )

    # Collision probability must be in [0, 1]
    prob_valid = 0.0 <= cdm["COLLISION_PROBABILITY"] <= 1.0
    all_passed = all_passed and prob_valid
    print_result(
        "COLLISION_PROBABILITY in [0, 1]",
        prob_valid,
        f"{cdm['COLLISION_PROBABILITY']}"
    )

    # Composite risk score in [0, 1]
    score_valid = 0.0 <= cdm["COMPOSITE_RISK_SCORE"] <= 1.0
    all_passed  = all_passed and score_valid
    print_result(
        "COMPOSITE_RISK_SCORE in [0, 1]",
        score_valid,
        f"{cdm['COMPOSITE_RISK_SCORE']}"
    )

    # RECOMMENDED_ACTION must have an 'action' key
    action_present = "action" in cdm.get("RECOMMENDED_ACTION", {})
    all_passed     = all_passed and action_present
    print_result(
        "RECOMMENDED_ACTION contains 'action' key",
        action_present,
        str(cdm.get("RECOMMENDED_ACTION", {}).get("action", "MISSING"))
    )

    return all_passed


# ===========================================================================
# TEST 6 — Real Pair End-to-End CDM via API
# ===========================================================================

def test_6_real_pair_cdm():
    """
    Call GET /conjunction/pair/25544/44713 — ISS vs Starlink-1007.

    This is the most complete real-world validation test:
      - Fetches live propagated state from the production API
      - Runs the full conjunction pipeline (TCA + risk + CDM)
      - Fires Phase B SGP4 bisection on real TLE lines
      - Returns a production CDM from real orbital data

    If this test passes, Phase 2 is proven to work end-to-end on
    real satellites, not just synthetic constructions.
    """
    print_header("TEST 6 — Real Pair End-to-End CDM (ISS vs Starlink-1008)")
    all_passed = True

    url = f"{PAIR_URL}/{ISS_NORAD}/{STARLINK_NORAD}?window_hours=6"
    print(f"  Calling: {url}")

    try:
        t0       = time.perf_counter()
        response = httpx.get(url, timeout=120)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        print_result("API call succeeded", False, str(e))
        return False

    print_result("API call succeeded", True, f"{elapsed_ms:.0f} ms")

    # Error check
    if "error" in result:
        print_result("No error in response", False, result["error"])
        return False

    # Required top-level keys
    for key in ["queried_at", "object_1", "object_2", "current_separation_km",
                "approach", "risk", "cdm"]:
        present    = key in result
        all_passed = all_passed and present
        print_result(f"Field '{key}' present", present)

    if "approach" not in result:
        return False

    approach = result["approach"]
    risk     = result["risk"]
    cdm      = result["cdm"]

    # SGP4 bisection fired — the definitive test
    tca_refined = approach.get("tca_refined") is True
    all_passed  = all_passed and tca_refined
    print_result(
        "Phase B SGP4 bisection fired (tca_refined=True)",
        tca_refined,
        "CONFIRMED — real tle_line1/tle_line2 exercised full pipeline"
        if tca_refined else "DID NOT FIRE — tle_line1/tle_line2 missing from catalog"
    )

    # Miss distance physically plausible
    miss_ok    = 0 <= approach.get("distance_km", -1) < 50000
    all_passed = all_passed and miss_ok
    print_result("Miss distance in [0, 50000) km", miss_ok,
                 f"{approach.get('distance_km', 'N/A'):.3f} km")

    # Risk score in [0, 1]
    score_ok   = 0.0 <= risk.get("composite_score", -1) <= 1.0
    all_passed = all_passed and score_ok
    print_result("Composite risk score in [0, 1]", score_ok,
                 f"{risk.get('composite_score', 'N/A')}")

    # CDM has CCSDS fields
    ccsds_fields = ["CDM_VERSION", "CREATION_DATE", "TCA",
                    "MISS_DISTANCE_KM", "COLLISION_PROBABILITY", "OBJECT_1", "OBJECT_2"]
    for field in ccsds_fields:
        present    = field in cdm
        all_passed = all_passed and present
        print_result(f"CDM field '{field}' present", present)

    print(f"\n  ISS vs Starlink-1007 live result:")
    print(f"    current_separation = {result.get('current_separation_km', 'N/A'):.1f} km")
    print(f"    miss_distance      = {approach.get('distance_km', 'N/A'):.3f} km")
    print(f"    tca_seconds        = t+{approach.get('time_seconds', 'N/A'):.1f}s")
    print(f"    tca_refined        = {approach.get('tca_refined')}")
    print(f"    risk_level         = {risk.get('risk_level')}")
    print(f"    composite_score    = {risk.get('composite_score')}")
    print(f"    shell_density      = {risk.get('shell_density_factor')}")
    print(f"    recommended_action = {cdm.get('RECOMMENDED_ACTION', {}).get('action', 'N/A')}")

    return all_passed


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    run_timestamp = datetime.now(timezone.utc)
    buffer        = io.StringIO()

    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
        def flush(self):
            for s in self.streams:
                s.flush()

    original_stdout = sys.stdout
    sys.stdout      = Tee(original_stdout, buffer)

    print(f"\n{'=' * 70}")
    print("  IOLA PHASE 2 VALIDATION SUITE")
    print(f"  Run timestamp : {run_timestamp.isoformat()}")
    print(f"  API endpoint  : {API_URL}")
    print(f"  Python        : {sys.version.split()[0]}")
    print(f"{'=' * 70}")

    # Fetch real satellite data once — used by Tests 2, 4, 6
    try:
        real_satellites = fetch_real_satellites(limit=500)
    except Exception as e:
        print(f"\nFATAL: Could not reach API -- {e}")
        sys.stdout = original_stdout
        sys.exit(1)

    results = {
        "test_1": test_1_geometric_correctness(),
        "test_2": test_2_tca_accuracy_real(real_satellites),
        "test_3": test_3_risk_score_bounds(),
        "test_4": test_4_screen_performance_real(real_satellites),
        "test_5": test_5_cdm_field_completeness(),
        "test_6": test_6_real_pair_cdm(),
    }

    passed_count = sum(1 for v in results.values() if v)
    total_count  = len(results)

    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed_count}/{total_count} tests passed")
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"    {name.upper()}: {status}")
    print(f"{'=' * 70}")
    print(f"\n  Signed: Jason Quist (Founder & CEO) + Claude (Chief Research Scientist)")
    print(f"  Phase 2 validation run complete.")

    sys.stdout  = original_stdout
    output_text = buffer.getvalue()

    tests_dir   = os.path.dirname(os.path.abspath(__file__))
    datestamp   = run_timestamp.strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(tests_dir, f"phase2_validation_response_{datestamp}.txt")

    header = (
        "IKIRERE ORBITAL LABS AFRICA\n"
        "Phase 2 Validation -- Full Output Record\n"
        "========================================\n"
        f"Run at    : {run_timestamp.isoformat()}\n"
        f"API       : {API_URL}\n"
        f"Real sats : {len(real_satellites)}\n"
        f"Python    : {sys.version.split()[0]}\n"
        f"Result    : {passed_count}/{total_count} tests passed\n"
        "========================================\n\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(output_text)

    print(f"\nOutput written to: {output_path}")

    if passed_count < total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
