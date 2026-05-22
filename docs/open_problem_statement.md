# Open Problem: Real-Time Many-to-Many Conjunction Screening at Orbital Scale

**Ikirere Orbital Labs Africa (IOLA)**  
**Date:** 2026-05-22  
**Status:** Open. No published solution exists at the performance threshold defined below.  
**Contact:** jason@ikirere.com  
**Repository:** iolaresearch/iola-orbit

---

## The Problem in One Sentence

Given a catalog of 15,000+ actively tracked orbital objects, compute all pairwise
conjunction risks — including cascade-weighted orbital shell density — in under 100
milliseconds.

---

## Background

### The Kessler Cascade

In 1978 Donald Kessler and Burton Cour-Palais published a scenario now recognised as
the defining existential risk of orbital infrastructure: a collision between two objects
in Low Earth Orbit generates a debris field. Each fragment has its own orbital
trajectory. Some fragments strike other satellites. More debris. More collisions. The
debris density in a given orbital shell crosses a threshold where collisions become
statistically inevitable regardless of whether any new objects are launched. The shell
becomes self-sustaining in its own destruction.

This is not theoretical. The 2009 Iridium-Cosmos collision and the 2021 Cosmos-1408
ASAT test each generated thousands of fragments still in orbit today. The LEO shell
between 400 and 600 km — home to the Starlink megaconstellation, OneWeb, Amazon Kuiper,
and thousands of other operators — is approaching critical density.

USSPACECOM currently tracks 27,000+ objects. Estimated 500,000 objects between 1 and
10 cm are untracked. A 1 cm fragment at orbital velocity carries the kinetic energy of
a hand grenade.

### The screening bottleneck

Every 15,000-satellite catalog contains:

```
15,000 × 14,999 / 2 = 112,492,500 pairs
```

At 1 millisecond per pair (faster than any current Python implementation): 112,492
seconds = 31 hours. Not viable.

Current state of the art:
- **Space-Track (USSPACECOM):** 8-hour screening cadence
- **LeoLabs:** custom screenings in under 30 seconds (proprietary, undisclosed architecture)
- **jaxsgp4 (Cambridge, March 2026):** 9,341 satellites × 1,000 time steps in 4ms on A100 GPU — but this solves **propagation only**, not the full conjunction screening pipeline

The full conjunction screening pipeline — propagation, pairwise geometry, TCA
computation, risk scoring, CDM generation — has not been solved at millisecond scale
with a publicly available, verifiable implementation.

---

## Formal Problem Statement

### Input

A catalog `C` of `n` orbital objects, where each object is defined by:
- A Two-Line Element set (TLE): name, line 1, line 2
- Derived state vector at epoch `t₀`: position `r = (x, y, z)` in km ECI,
  velocity `v = (vx, vy, vz)` in km/s ECI
- Atmospheric drag coefficient B* (from TLE)
- TLE epoch timestamp

### Required output

For every pair `(i, j)` where `i < j` and `|altitude_i - altitude_j| < 200 km`:

1. **Time of Closest Approach (TCA)** — UTC timestamp accurate to ±2 seconds
2. **Miss distance at TCA** — in km, accurate to ±1 km for LEO objects
3. **Composite risk score** — a scalar in [0, 1] incorporating:
   - Geometric miss distance
   - Relative velocity at TCA
   - Time urgency (seconds until TCA)
   - Collision probability (Gaussian approximation with uncertainty envelope)
   - TLE age uncertainty: `σ(t) = σ₀ + k × (|B*| / B*_nominal) × age_days²`
   - **Orbital shell density factor** (the novel component): a cascade-weighted score
     proportional to the population density of the orbital shell in which the conjunction
     occurs, reflecting Kessler cascade potential
4. **Conjunction Data Message (CDM)** — structured advisory, CCSDS 508.0-B-1 mappable

Returned as a ranked list sorted by composite risk score, highest first.

### Performance requirement

| Metric | Requirement |
|---|---|
| Total screening time | < 100 milliseconds for n = 15,000 |
| TCA accuracy | ±2 seconds |
| Miss distance accuracy | ±1 km for LEO (altitude < 2,000 km) |
| Output completeness | All pairs with altitude separation < 200 km |
| Hardware | Achievable on a single NVIDIA A100 or equivalent |

---

## Why This Is Hard

Three distinct computational problems must be solved simultaneously:

**1. Propagation at scale**
Each satellite must be propagated to multiple future time points using SGP4/SDP4.
This is solved by jaxsgp4 (Cambridge, 2026) for propagation-only. 4ms for 9,341
satellites × 1,000 steps on an A100. The path exists.

**2. Pairwise geometry at scale**
112 million pairs. Even with the 200 km altitude pre-filter (eliminating ~95% of pairs),
the surviving ~5.6 million pairs require distance computation and TCA search. Each TCA
search sweeps a 72-hour window at 60-second resolution = 4,320 time steps per pair.
A naive implementation: 5.6M × 4,320 SGP4 evaluations = 24 billion evaluations.
This requires fully parallel GPU execution with memory-efficient batch decomposition.

**3. Novel risk scoring at scale**
The composite risk score includes the orbital shell density factor — a function of how
many objects share the altitude band of the conjunction. Computing this naively requires
querying the full catalog for each pair. At 5.6 million pairs this is a second O(n²)
problem. A histogram-based pre-computation reduces it to O(n) setup + O(1) lookup per
pair. But this must be co-located on the GPU with the propagation and geometry to avoid
transfer bottlenecks.

---

## What Exists

| Component | Status | Reference |
|---|---|---|
| GPU-accelerated SGP4 propagation | Solved | jaxsgp4, arxiv:2603.27830 (Cambridge, 2026) |
| CUDA parallel orbit propagation | Solved | Advances in Space Research, 2023 |
| Browser-based GPU SGP4 | Solved | sgp4.gl, Kayhan Space, 2025 |
| Full pairwise conjunction pipeline on GPU | **Unsolved** | — |
| Cascade-weighted risk scoring on GPU | **Unsolved** | — |
| Sub-100ms end-to-end screening for 15k+ objects | **Unsolved** | — |

---

## IOLA's Current Implementation

IOLA has implemented the full conjunction screening pipeline in Python, correctly and
with novel risk scoring. The algorithm is correct. The performance is ~7,290 seconds
for the full catalog on a CPU (Python loops, sequential SGP4 calls).

The three-stage pipeline (`screen_catalog()` in `server/conjunction.py`):

```
Stage 1: Altitude band grouping (O(n)) — eliminates ~95% of pairs
Stage 2: Current separation filter (O(m), m << n²) — eliminates most remaining pairs
Stage 3: TCA computation + risk scoring (O(k × t), k << m)
```

The novel IP:
- `compute_tle_age_uncertainty_km()` — bstar-weighted quadratic uncertainty growth
- `compute_orbital_shell_density()` — Kessler cascade factor from live catalog population
- `compute_composite_risk_score()` — 6-component weighted risk formula

This implementation is validated (5/5 tests passing), research-correct, and open.

The gap between current performance (~2 hours) and the target (<100ms) is a GPU
architecture problem, not an algorithm problem. The algorithm is correct. It needs
to run in parallel on GPU hardware.

---

## The Research Contribution

A solution to this problem would produce:

1. **A GPU-native conjunction screening pipeline** that processes the full LEO catalog
   in under 100 milliseconds — the first publicly verifiable implementation at this scale

2. **Real-time Kessler cascade risk scoring** — not just pairwise collision probability
   (the current USSPACECOM standard) but cascade-weighted orbital shell risk that reflects
   the true consequence of each conjunction, not just its probability

3. **A foundation for autonomous orbital coordination** — millisecond screening enables
   onboard real-time conjunction awareness for constellation satellites, which is the
   prerequisite for autonomous avoidance and the core of Phase 3 (IkirereMesh)

4. **A research paper** targeting ICML, NeurIPS, or IEEE Aerospace Conference

---

## Relevance to the Kessler Cascade Problem

The reason real-time screening matters is not operational convenience. It is existential.

Space-Track's 8-hour cadence means that a fast-moving conjunction event (a debris
fragment at high relative velocity approaching an operational satellite) may not be
detected until 4 hours after TCA. The human-in-the-loop pipeline (operator decision,
ground contact window, command uplink, burn execution) requires 24-48 hours minimum.

If screening runs in milliseconds and can be executed onboard, the detection-to-decision
cycle compresses from days to seconds. An autonomous coordination system with millisecond
awareness and pre-approved maneuver authority can respond before a human operator would
even be notified.

This is the only architecture that can keep the LEO orbital environment usable as
constellation density increases toward Kessler-critical thresholds.

---

## Invitation

IOLA is building this system. We are looking for:

- **Research collaborators** — GPU systems researchers, astrodynamicists, ML engineers
  interested in the intersection of orbital mechanics and real-time systems
- **Compute contributors** — access to A100 or H100 GPU time to validate the Phase 4
  architecture
- **Co-authors** — for the research paper targeting ICML/NeurIPS/IEEE Aerospace

If you have solved a component of this problem, are working on it, or want to, reach
out.

```
Jason Quist — Founder & CEO, Ikirere Orbital Labs Africa
jason@ikirere.com
ikirere.com
Deep Learning Indaba 2025 Winner
INSEAD AI Venture Lab Fellow
Google + NVIDIA Inception Program
```

---

## References

1. Kessler, D.J. and Cour-Palais, B.G. (1978). "Collision Frequency of Artificial
   Satellites: The Creation of a Debris Belt." Journal of Geophysical Research.

2. jaxsgp4 (2026). "GPU-Accelerated SGP4 Propagation." arxiv:2603.27830.
   Cambridge University. March 2026.

3. Hoots, F.R. and Roehrich, R.L. (1980). "Models for Propagation of NORAD Element
   Sets." Spacetrack Report No. 3.

4. CCSDS 508.0-B-1 (2013). "Conjunction Data Message." Consultative Committee for
   Space Data Systems.

5. Vallado, D.A. (2013). "Fundamentals of Astrodynamics and Applications." 4th edition.
   Microcosm Press.

---

*Document created: 2026-05-22*  
*Ikirere Orbital Labs Africa — Africa's Access to Space*  
*"Software first. Hardware second. Space third."*
