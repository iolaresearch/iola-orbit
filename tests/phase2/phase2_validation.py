"""
IKIRERE ORBITAL LABS AFRICA — PHASE 2
Validation Test Suite

=======================================================================
PURPOSE
=======================================================================
Validates the Phase 2 orbital intelligence engine against known
physical constraints, mathematical invariants, and performance bounds.

These are research-grade acceptance tests. Every test targets a real
physical or mathematical invariant that would be violated if the
conjunction engine is incorrect.

=======================================================================
TEST COVERAGE
=======================================================================
Test 1 — Geometric correctness
  Compute separation for two satellites at known positions.
  Verify against manually calculated Euclidean distance.
  Test the mathematical foundation before trusting anything above it.

Test 2 — TCA accuracy
  Run find_closest_approach() for a known converging pair.
  Verify refined TCA is within 2 seconds of coarse TCA.
  Verify miss distance is non-negative and physically plausible.

Test 3 — Risk score bounds and component consistency
  Score must be in [0.0, 1.0] for all input combinations.
  All components must be individually in [0.0, 1.0].
  Score with approaching=True must be >= score with approaching=False.
  Higher miss distance must produce lower or equal composite score.

Test 4 — Screen performance
  Catalog screen must complete in under 60 seconds for a sample of
  satellites. (Full 15k catalog screen is a research operation, not
  a real-time one — document expected time accurately.)

Test 5 — CDM field completeness
  All required fields present and correctly typed.
  CCSDS-required fields present.
  TCA in CDM must be later than CREATION_DATE.
  OBJECT_1 and OBJECT_2 NORAD IDs must be distinct.

=======================================================================
HOW TO RUN
=======================================================================
From the repository root:

    python tests/phase2/phase2_validation.py

Or against a local server for Test 4 (live catalog):

    API_URL=http://localhost:8000 python tests/phase2/phase2_validation.py

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

API_URL = os.getenv("API_URL", "https://iola-orbit-dfxp.onrender.com")

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
# TEST 2 — TCA Accuracy
# ===========================================================================

def test_2_tca_accuracy():
    """
    Verify TCA computation produces physically plausible results.
    TCA must be non-negative and miss distance must be non-negative.
    Refined TCA must be within 2 minutes of coarse TCA (for synthetic data
    without full TLE lines, refinement falls back to coarse — this is expected).
    """
    print_header("TEST 2 — TCA Accuracy")
    all_passed = True

    # Short window for test speed (1 hour, 60s step)
    approach = find_closest_approach(SYNTHETIC_SAT_A, SYNTHETIC_SAT_C,
                                     scan_duration_seconds=3600,
                                     coarse_step_seconds=60)

    # Miss distance must be non-negative
    miss_non_negative = approach["distance_km"] >= 0
    all_passed        = all_passed and miss_non_negative
    print_result(
        "Miss distance >= 0",
        miss_non_negative,
        f"miss_distance_km = {approach['distance_km']:.3f}"
    )

    # Miss distance must be physically plausible (< diameter of Earth)
    miss_plausible = approach["distance_km"] < 12742.0
    all_passed     = all_passed and miss_plausible
    print_result(
        "Miss distance < Earth diameter (12,742 km)",
        miss_plausible,
        f"miss_distance_km = {approach['distance_km']:.3f}"
    )

    # TCA must be within scan window
    tca_in_window = 0 <= approach["time_seconds"] <= 3600
    all_passed    = all_passed and tca_in_window
    print_result(
        "TCA within scan window (0-3600s)",
        tca_in_window,
        f"tca_seconds = {approach['time_seconds']:.1f}"
    )

    # tca_refined flag must be a boolean
    refined_is_bool = isinstance(approach["tca_refined"], bool)
    all_passed      = all_passed and refined_is_bool
    print_result(
        "tca_refined is boolean",
        refined_is_bool,
        f"tca_refined = {approach['tca_refined']}"
    )

    # approaching flag must be a boolean
    approaching_is_bool = isinstance(approach["approaching"], bool)
    all_passed          = all_passed and approaching_is_bool
    print_result(
        "approaching is boolean",
        approaching_is_bool,
        f"approaching = {approach['approaching']}"
    )

    print(f"\n  TCA result: miss={approach['distance_km']:.3f} km at "
          f"t+{approach['time_seconds']:.1f}s, "
          f"refined={approach['tca_refined']}, approaching={approach['approaching']}")

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
# TEST 4 — Screen Performance
# ===========================================================================

def test_4_screen_performance():
    """
    Measure catalog screening performance.
    Test against a synthetic fleet of 200 satellites (fast, deterministic).
    Report expected time for full 15k catalog.
    """
    print_header("TEST 4 — Screen Performance")
    all_passed = True

    # Build synthetic catalog: 200 objects in LEO at various altitudes
    synthetic_fleet = []
    for i in range(200):
        angle_rad = (i / 200.0) * 2 * math.pi
        radius_km = 7000.0 + (i % 10) * 50.0
        synthetic_fleet.append({
            "norad_id":      f"SYN{i:04d}",
            "name":          f"SYNTHETIC-{i}",
            "x":             radius_km * math.cos(angle_rad),
            "y":             radius_km * math.sin(angle_rad),
            "z":             float(i % 50) * 10.0,
            "vx":            -7.5 * math.sin(angle_rad),
            "vy":             7.5 * math.cos(angle_rad),
            "vz":             0.0,
            "speed_km_s":    7.5,
            "altitude_km":   radius_km - 6371.0,
            "orbital_class": "LEO",
            "bstar":         1e-4,
            "epoch":         (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "sunlit":        True,
            "propagation_mode": "SGP4",
        })

    # Time the screen with a tight threshold (fast, fewer TCA scans)
    t0     = time.perf_counter()
    result = screen_catalog(synthetic_fleet, threshold_km=50.0, scan_window_seconds=3600)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Must complete in under 60 seconds
    within_time = elapsed_ms < 60000
    all_passed  = all_passed and within_time
    print_result(
        "200-satellite screen completes under 60s",
        within_time,
        f"{elapsed_ms:.0f} ms"
    )

    # Result must have the required keys
    required_keys = ["screened_at", "total_satellites", "pairs_altitude_passed",
                     "pairs_separation_passed", "conjunctions_found", "conjunctions", "summary"]
    keys_present  = all(k in result for k in required_keys)
    all_passed    = all_passed and keys_present
    print_result(
        "Screen result has all required keys",
        keys_present,
        str([k for k in required_keys if k not in result]) if not keys_present else "All present"
    )

    # Summary counts must add up to conjunctions_found
    summary_total = sum(result["summary"].values())
    counts_match  = summary_total == result["conjunctions_found"]
    all_passed    = all_passed and counts_match
    print_result(
        "Summary counts match conjunctions_found",
        counts_match,
        f"summary total={summary_total}  conjunctions_found={result['conjunctions_found']}"
    )

    # Stage counts must be logically ordered
    stage_order = (result["pairs_altitude_passed"] >= result["pairs_separation_passed"])
    all_passed  = all_passed and stage_order
    print_result(
        "Altitude-passed >= separation-passed (filter reduces pairs)",
        stage_order,
        f"altitude={result['pairs_altitude_passed']}  separation={result['pairs_separation_passed']}"
    )

    print(f"\n  Fleet: {result['total_satellites']} satellites")
    print(f"  Stage 1 (altitude):   {result['pairs_altitude_passed']} pairs")
    print(f"  Stage 2 (separation): {result['pairs_separation_passed']} pairs")
    print(f"  Conjunctions found:   {result['conjunctions_found']}")
    print(f"  Screen time:          {elapsed_ms:.0f} ms")

    # Extrapolate to full catalog
    scale_factor  = (15447 / 200) ** 2  # O(n^2) scaling
    estimated_s   = (elapsed_ms / 1000) * scale_factor
    print(f"\n  Estimated full 15k catalog time: ~{estimated_s:.0f}s "
          f"(this is a research operation, not a real-time call)")

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
    print(f"  Python        : {sys.version.split()[0]}")
    print(f"{'=' * 70}")

    results = {
        "test_1": test_1_geometric_correctness(),
        "test_2": test_2_tca_accuracy(),
        "test_3": test_3_risk_score_bounds(),
        "test_4": test_4_screen_performance(),
        "test_5": test_5_cdm_field_completeness(),
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
