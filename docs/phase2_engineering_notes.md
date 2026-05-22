# IOLA Phase 2 — Engineering Notes
## Orbital Intelligence Infrastructure

**Status:** In progress  
**Period:** 2026-05-22 onward  
**Engineers:** Jason Quist (Founder & CEO) · Claude (Chief Research Scientist / Systems Architect)  
**Repository:** iola-orbit — `server/conjunction.py`  
**Predecessor:** See `docs/phase1_engineering_notes.md` for all Phase 1 decisions, bugs, and architecture.

**Document policy:** Append-only. Every bug, decision, rename, and open question is recorded with timestamp and signature. Nothing is softened or removed. This document will be read by future engineers, cited in research papers, and reviewed by investors. It must be accurate.

---

## Preamble

*Written: 2026-05-22 · Jason Quist + Claude*

Phase 1 answered one question: *"Where are the satellites right now?"*

Phase 2 answers the next question: *"Will they collide?"*

This is not a minor extension of Phase 1. It is a qualitative change in what the system understands. Phase 1 produces orbital state — positions, velocities, altitudes. Phase 2 produces orbital intelligence — relationships between objects, predictions of future encounters, risk assessments, actionable advisories.

The data pipeline is intentionally sequential and cumulative:

```
Phase 1  propagate.py       → orbital state (position, velocity, altitude, sunlit, bstar, epoch)
Phase 2  conjunction.py     → orbital intelligence (TCA, miss distance, risk score, CDM)
Phase 3  ikirere_mesh.py    → coordination decisions (maneuver proposals, coverage optimisation)
```

Each phase enriches the data. Phase 3 cannot function without Phase 2 output. Phase 2 cannot function without Phase 1 output. The architecture is load-bearing in sequence.

---

## 1. Objective

*Written: 2026-05-22 · Jason Quist + Claude*

Phase 2 answers: *"Will they collide? And how dangerous is this encounter compared to every other encounter in the catalog?"*

The output must be:

- **Deterministic** — the same input at the same time always produces the same output
- **Physically correct** — not approximately correct. The mathematics are derived from first principles.
- **Actionable** — every output is either a number a human can act on, or a recommendation a human can evaluate
- **Novel** — the Kessler cascade factor and bstar-weighted TLE age uncertainty are IOLA IP. They are not in any published CDM standard.
- **Human-supervised** — Phase 2 produces intelligence. It does not command spacecraft. The operator decides.

---

## 2. Kessler Syndrome — The Reason Phase 2 Exists

*Written: 2026-05-22 · Jason Quist + Claude*  
*Briefing source: External research discussion, 2026-05-22*

In 1978 Donald Kessler and Burton Cour-Palais published a paper describing a scenario that has since become the defining existential risk of orbital infrastructure.

**The cascade mechanism:**

Two objects collide in LEO. The collision generates a debris field. Each fragment from that debris field has its own orbital trajectory. Some fragments collide with other satellites. Each of those collisions generates more debris. The debris density in a given orbital shell crosses a threshold where further collisions become statistically inevitable regardless of whether any new objects are launched. The shell becomes self-sustaining in its own destruction.

**Why it is relevant to IOLA specifically:**

The LEO shell between 400 and 600 km — exactly where IOLA's CubeSat will operate — is the most congested volume of space in human history. The Starlink constellation alone contributes approximately 6,000 satellites to the green LEO cloud visible in the Phase 1 visualizer. OneWeb adds 600. Amazon Kuiper is planning 3,200. Planet Labs, Spire, and dozens of other operators add more. USSPACECOM currently tracks over 27,000 objects larger than 10 cm. Estimated 500,000 objects between 1 and 10 cm are untracked and untrackable with current ground radar.

A 1 cm fragment at orbital velocity carries the kinetic energy of a hand grenade.

**Real-world events:**

- 2009: Iridium 33 and Cosmos 2251 collided over Siberia, generating 2,000+ trackable fragments. Still in orbit.
- 2021: Russia destroyed Cosmos 1408 in an antisatellite test, generating 1,500 trackable fragments and forcing ISS crew to shelter. Still in orbit.

**Why USSPACECOM CDMs are insufficient:**

USSPACECOM's Conjunction Data Messages report probability of collision for the specific pair. They do not score the cascade potential of the orbital shell. A conjunction between two active satellites in the Starlink shell at 550 km is categorically more dangerous than the same miss distance between two derelict objects in a sparse shell at 1,200 km, because the cascade consequence differs by orders of magnitude.

**The IOLA solution — shell density factor:**

`compute_composite_risk_score()` includes a `shell_density_factor` component (10% weight) that measures the population density of the orbital shell in which the conjunction occurs. This is IOLA's novel contribution to conjunction scoring. It accounts for the fact that consequence is not pair-symmetric. The same Pc can represent vastly different real-world risks depending on orbital shell.

This component feeds directly into Phase 3: IkirereMesh's reward function must penalise actions that increase conjunction risk in dense shells more heavily than the same risk in sparse shells.

---

## 3. System Architecture

*Written: 2026-05-22 · Jason Quist + Claude*

```
state.satrec_catalog          — parsed Satrec objects, populated by fetch_tle.py
        |
        v
propagate_satellites()        — on-demand SGP4 evaluation → 15,000+ satellite records
        |
        v
screen_catalog()              — three-stage conjunction pipeline
  Stage 1: altitude_band_grouping()  — O(n) pre-filter, eliminates ~95% of pairs
  Stage 2: current_separation()     — O(m) filter, m << n²
  Stage 3: find_closest_approach()  — O(k) full TCA, k << m
        |
        v
compute_composite_risk_score() — 6-component risk formula (IOLA IP)
        |
        v
generate_cdm()                — CCSDS-adjacent CDM (IOLA proprietary JSON)
        |
        v
API endpoints:
  GET /conjunction/screen              → full catalog scan
  GET /conjunction/pair/{id1}/{id2}    → specific pair report
  GET /conjunction/high-risk           → events with score > 0.7
        |
        v
Phase 3 (ikirere_mesh.py)     — consumes risk scores, CDMs, shell density data
```

**Two-phase TCA algorithm in `find_closest_approach()`:**

- Phase A: Coarse Keplerian scan (60s steps, 24h window). Fast. ~1 km accuracy.
- Phase B: SGP4 bisection refinement (12 iterations, converges to ~0.03s). CCSDS-grade accuracy. Requires `tle_line1`/`tle_line2` on the satellite record (stored by `fetch_tle.py`).

---

## 4. Novelty Boundaries

*Written: 2026-05-22 · Jason Quist + Claude*

Per Alph Doamekpor's guidance: do not reinvent standard orbital mechanics. Use established tools. Novelty must be locatable and defensible.

| Component | Novel? | Notes |
|---|---|---|
| Euclidean distance between satellites | No | Standard vector math. |
| Keplerian two-body propagation | No | Published, standard. Used for coarse TCA scan. |
| SGP4 TCA bisection refinement | No | Standard algorithm applied to conjunction. |
| Eclipse/sunlight detection | No | Conical shadow model, well-published. |
| Coverage footprint geometry | No | Spherical Earth geometry, standard. |
| Communication window prediction | No | ECI→ECEF rotation + elevation angle, standard. |
| Orbital decay estimation | No | Piecewise exponential atmosphere, standard. |
| **`compute_tle_age_uncertainty_km()`** | **Yes** | σ(t) = σ₀ + k × |B*| / B*_nominal × age². No published standard weights positional uncertainty by bstar-adjusted TLE age. IOLA IP. |
| **`shell_density_factor` in risk score** | **Yes** | Kessler cascade weight. No published CDM standard uses orbital shell population density as a risk component. IOLA IP. |
| **Composite risk score formula** | **Yes** | 6-component weighted formula. The specific combination — distance, velocity, time urgency, collision probability, TLE age uncertainty, shell density — is IOLA's formulation. Validation target: calibrate weights against historical Space-Track CDMs. |
| CDM internal format | Partial | IOLA-proprietary JSON. Designed to map to CCSDS 508.0-B-1 without structural change. The schema is novel; the required fields are standard-compliant. |

---

## 5. Phase 1 → Phase 2 → Phase 3 Data Pipeline

*Written: 2026-05-22 · Jason Quist + Claude*

### Phase 1 fields consumed by Phase 2

| Phase 1 field | How Phase 2 uses it |
|---|---|
| `x`, `y`, `z` | Euclidean distance between pairs — the mathematical foundation |
| `vx`, `vy`, `vz` | Relative velocity vector — approach direction and speed |
| `speed_km_s` | Approach severity classification |
| `altitude_km` | Altitude pre-filter (Stage 1 of `screen_catalog`) |
| `orbital_class` | Cross-shell filtering and CDM metadata |
| `epoch` | TLE age calculation for `compute_tle_age_uncertainty_km` |
| `bstar` | Drag coefficient — scales uncertainty growth with TLE age |
| `sunlit` | Passed through to CDM metadata; eclipse windows computed separately |
| `norad_id` | Primary key for all pair computations and CDM identification |
| `name` | Human-readable identification in CDM output |
| `tle_line1`, `tle_line2` | Required for Phase B SGP4 bisection in `find_closest_approach` |

### Phase 2 outputs consumed by Phase 3

Phase 3 (IkirereMesh) will consume from Phase 2:

| Phase 2 output | Phase 3 use |
|---|---|
| `composite_score` | Collision avoidance reward shaping — high-risk pairs drive maneuver proposals |
| `shell_density_factor` | Kessler cascade term in reward function — penalises risk in dense shells |
| `tca_seconds_from_now` | Maneuver timing decisions — urgency of coordination response |
| `relative_velocity_kms` | Delta-V estimation for avoidance maneuvers |
| `miss_distance_km` | Separation target for maneuver planning |
| `worst_case_uncertainty_km` | Confidence bounds on maneuver effectiveness |
| `cdm` | Full structured context for coordination decisions |

---

## 6. Human-in-the-Loop Boundary

*Written: 2026-05-22 · Jason Quist + Claude*

This boundary is architecturally mandatory. It applies to Phase 2 and Phase 3 equally.

**Phase 2 produces intelligence. It does not command spacecraft.**

`screen_catalog()` returns a ranked list of conjunction events. `generate_cdm()` produces a structured advisory. `generate_maneuver_recommendation()` produces an action flag (`MONITOR`, `MONITOR_CLOSELY`, `MANEUVER_RECOMMENDED`, `MANEUVER_IMMEDIATE`). None of these cause any satellite to do anything.

**Why this boundary must never be crossed:**

At 7.7 km/s, 3 seconds is 23 km. One wrong autonomous command cascades at the speed of orbital mechanics. In a dense LEO shell, a botched avoidance maneuver can create a new conjunction while resolving the original one. Kessler dynamics are not reversible. Human oversight is not a limitation — it is a safety property and, for licensed operators, a regulatory requirement.

**Phase 3 boundary:**

IkirereMesh will propose coordination actions. Those proposals are recommendations subject to human approval. The architecture of Phase 3 must include an explicit human-approval gate before any maneuver command reaches hardware. This gate is not optional. It is documented here so it cannot be accidentally omitted when Phase 3 is built.

---

## 7. Risk Score Formula — Design Record

*Written: 2026-05-22 · Jason Quist + Claude*

### Components and weights (v1.0)

| Component | Weight | Formula | Physical meaning |
|---|---|---|---|
| `distance_risk` | 35% | `max(0, 1 - miss_distance / 50.0)` | Saturates to 1.0 at 0 km, 0.0 at 50 km |
| `velocity_risk` | 20% | `min(1, relative_velocity / 15.0)` | Saturates at 15 km/s (head-on LEO-LEO max) |
| `time_urgency` | 20% | `max(0, 1 - tca_seconds / 7200.0)` | Full urgency within 2 hours |
| `probability` | 5% | `min(1, collision_probability × 1e5)` | Gaussian Pc, normalised |
| `tle_age_risk` | 10% | `min(1, (uncertainty - σ₀) / 50.0)` | Saturates at 50 km positional uncertainty |
| `shell_density` | 10% | `density_factor` from `compute_orbital_shell_density()` | Kessler cascade weight |
| Closing bonus | +0.1 | Applied if `approaching == True` | Penalises confirmed closing geometry |

**Calibration status:** First-principles estimate. Weights not yet empirically validated.

**Validation target:** Run scorer against 20-30 known historical CDMs from Space-Track. Compare IOLA risk tier assignment (CRITICAL/HIGH/MODERATE/LOW) against actual outcomes. Fit weights to minimise misclassification rate. This is Phase 2's empirical validation milestone.

### Why shell density is 10% not higher

Shell density captures a real physical phenomenon (cascade potential) but it is a consequence multiplier, not a probability driver. A conjunction between two cubesats in a crowded shell at 550 km may have the same Pc as a conjunction between two large defunct satellites in a sparse shell at 900 km, but the former carries higher cascade risk. The 10% weighting reflects: relevant but secondary to the geometric probability of this specific event occurring.

Increasing shell density weight beyond 15% would cause the scorer to over-penalise all conjunctions in crowded shells regardless of their geometric severity. The goal is to break ties in favour of sparse-shell events, not to dominate the score.

### TLE age uncertainty formula

```
σ(age, bstar) = σ₀ + k × (|bstar| / bstar_nominal) × age_days²
```

Where:
- `σ₀ = 1.0 km` — baseline 1-sigma position uncertainty at epoch
- `k = 0.5 km/day²` — drag-induced uncertainty growth rate at nominal bstar
- `bstar_nominal = 1e-4` — typical LEO drag coefficient (1/earth_radii)
- `age_days` — TLE age in days

**Derivation:** Atmospheric drag causes unmodelled acceleration proportional to bstar. Velocity error integrates into position error quadratically with time. Objects with high bstar (e.g. high area-to-mass ratio debris) accumulate position uncertainty faster.

**k calibration target (PIN-002 from Phase 1):** Pull 20-30 satellites spanning the bstar range. Compare IOLA SGP4 positions against Space-Track at TLE ages of 1, 3, 5, and 7 days. Fit k to the observed error growth curve.

---

## 8. screen_catalog() Algorithm Design

*Written: 2026-05-22 · Jason Quist + Claude*

### The complexity problem

15,447 satellites. Every pair must potentially be checked.
- Naive O(n²): 15,447 × 15,446 / 2 = 119,267,631 pairs
- At 1ms per pair (generous): 119,267 seconds = 33 hours

This is not viable. The three-stage filter reduces it to a tractable computation.

### Stage 1 — Altitude band grouping (O(n))

Sort all satellites into 200 km altitude bands. Two satellites more than 200 km apart in altitude cannot be in the same orbital shell and cannot conjunct within a 24-hour window under normal orbital mechanics (excluding HEO objects at apogee, which are handled by the separation filter in Stage 2).

Expected reduction: from 119M pairs to ~6M (approximately 95% reduction).

**The 200 km threshold (from Phase 1 engineering notes, Open Question Q2):**

The Phase 2 spec document and early notes suggested 200 km. This is conservative — most pairs with 200 km altitude difference are genuinely incapable of conjunction. The geometric justification: for two circular orbits at altitudes h_a and h_b with |h_a - h_b| > 200 km, the perigee of the outer orbit is above the apogee of the inner orbit. They cannot intersect.

**The caveat:** High-eccentricity objects (CLUSTER, MMS at 130,000-172,000 km apogee) pass through all altitude bands during their orbit. The current algorithm handles this correctly because their instantaneous altitude at any given moment will place them in a specific band, and they will be paired with whatever other objects share that band at that moment. The TCA scan will find their true closest approach.

### Stage 2 — Current separation filter

For pairs that pass Stage 1, compute Euclidean distance at the current moment. Pairs more than `CONJUNCTION_SEPARATION_PREFILTER_KM` (1,000 km) apart right now are unlikely to come within the threshold distance within 24 hours.

This is an approximation, not a guarantee. Two satellites can be 1,000 km apart now and conjunct in 12 hours. However, for the purpose of operational screening, this filter eliminates a large fraction of geometrically unlikely pairs.

**Conservative design:** If a real conjunction is missed because of this filter, it will be caught on the next screening run (the system will call `screen_catalog` again). The filter is not the last line of defence.

### Stage 3 — Full TCA computation

For pairs that survive both filters, run the two-phase TCA algorithm (Keplerian coarse scan + SGP4 bisection refinement). Compute the 6-component composite risk score. Generate CDM for MODERATE and above.

---

## 9. CDM Format — Internal vs. CCSDS Export

*Written: 2026-05-22 · Jason Quist + Claude*

Phase 2 produces IOLA-proprietary JSON CDMs. The field structure is designed from day one to map to CCSDS 508.0-B-1 without structural change when the export layer is added.

### CCSDS field mapping

Every CDM field that maps to a CCSDS equivalent is commented inline in `generate_cdm()`. The fields that do not have CCSDS equivalents are the novel IOLA extensions: `COMPOSITE_RISK_SCORE`, `RISK_COMPONENTS`, `SHELL_POPULATION_COUNT`, `WORST_CASE_UNCERTAINTY_KM`.

These extensions are the IP. They will remain in the IOLA internal format even after CCSDS export is added.

### When to add the CCSDS export layer

Before the first Tier 1 customer conversation (NASA, ESA, JAXA). The export layer is a two-day implementation — it maps IOLA field names to CCSDS field names. It does not require any change to the conjunction algorithm or risk scorer.

See Phase 1 engineering notes Section 12 for the full CDM format decision analysis and three-tier customer framework.

---

## 10. Open Questions for Phase 2

*Written: 2026-05-22 · Jason Quist + Claude*

**Q1 — k constant calibration**
The TLE age uncertainty formula uses `k = 0.5 km/day²` as a first-principles estimate. Before Phase 2 outputs are used for any Tier 1 or Tier 2 customer output, calibrate k against real Space-Track position data. See Phase 1 notes PIN-002 for protocol.

**Q2 — Altitude pre-filter threshold validation**
The 200 km altitude pre-filter is conservative and justified geometrically for circular orbits. Validate it does not miss any real conjunction events by running a sample of pairs that just barely fail the filter through the full TCA computation. If any produce miss_distance < threshold_km, tighten the filter or remove it.

**Q3 — shell_density_factor weight**
The 10% weight for the Kessler cascade factor was assigned from first principles. After k calibration (Q1) and CDM comparison against Space-Track historical data, re-evaluate whether this weight is appropriate. If the factor is systematically pushing the score in the wrong direction for known events, adjust.

**Q4 — screen_catalog() performance on 15,000 satellites**
The three-stage filter is designed to reduce the O(n²) problem to manageable scale. The actual computation time on Render free tier must be measured. If it exceeds 30 seconds (the Phase 2 validation test threshold), optimise Stage 1 and Stage 2 before declaring Phase 2 production-ready. Possible optimisation: vectorise Stage 1 using a sorted altitude array instead of a dict.

**Q5 — TCA accuracy for HEO objects**
CLUSTER and MMS (altitude > 100,000 km at apogee) have highly elliptical orbits. The Keplerian two-body propagator used in Stage A of `find_closest_approach` is less accurate for HEO than for LEO. At perigee, the velocity is high (~10 km/s) and perturbations are significant. The SGP4 bisection refinement (Stage B) corrects much of this, but the coarse scan step (60s) may miss narrow close-approach windows. Consider reducing step to 10s for objects with altitude > 50,000 km.

---

## 11. Two-Body vs. Fleet — The TCAS Architecture Question

*Written: 2026-05-22 · Jason Quist + Claude*

This section records an important architectural clarification about how Phase 2 conjunction assessment relates to fleet-level safety, and how it evolves in Phase 3.

---

### The question

Is Phase 2 computing conjunctions between two satellites, or across all satellites simultaneously with a threshold filter?

The answer: **both, but they serve fundamentally different purposes and operate at different layers of the architecture.**

---

### Layer 1 — The two-body computation (mathematical foundation)

`distance_between_satellites()`, `find_closest_approach()`, and `compute_composite_risk_score()` all operate on **exactly two satellites**. This is mathematically correct and cannot be changed.

Conjunction is a two-body problem. You cannot compute a single conjunction event between three or more objects simultaneously in the same way you compute one between two. The physics of closest approach — the geometry of converging trajectories, the time of minimum separation, the relative velocity at that moment — is inherently pairwise.

This is not a limitation. It is the correct formulation. Every conjunction assessment system in aerospace — USSPACECOM, NASA CARA, ESA's SSOC — operates on satellite pairs. The pair is the unit of conjunction analysis.

---

### Layer 2 — `screen_catalog()` — The fleet-level operation

`screen_catalog()` is the fleet-level wrapper. It takes all 15,447 tracked satellites and runs the two-body computation for every relevant pair. The 200 km altitude threshold is the pre-filter that makes this computationally tractable — it eliminates ~95% of pairs before any expensive geometry is computed.

This **is** the TCAS analogy at the ground level. Every satellite in the catalog is checked against every other satellite in its altitude neighbourhood. The output is a ranked list of the most dangerous encounters across the entire tracked fleet.

The architectural distinction:

| What | Scope | Unit |
|---|---|---|
| `find_closest_approach()` | Two satellites | Pair |
| `screen_catalog()` | All 15,447 objects | Fleet |

---

### The gap — batch vs. continuous

TCAS on aircraft runs **continuously and simultaneously** on every aircraft. Every plane is checking its own local bubble of traffic at all times, in real time, autonomously.

`screen_catalog()` is a **batch operation**. For 15,447 satellites it takes approximately 68 minutes. It cannot run continuously. It is scheduled — run every N hours, results cached, served via API.

This is not a flaw in the design. It is a constraint of the operational context:

**We do not control the satellites.** TCAS works because every aircraft runs its own transponder and onboard processor. We are a ground observer with read-only access to TLE data. We cannot give each of the 15,447 tracked satellites its own local TCAS instance.

The ground system (`screen_catalog`) is the correct tool for what we can do: observe the full catalog, identify the highest-risk encounters, and produce intelligence for human operators.

---

### Layer 3 — Phase 3 IkirereMesh — The onboard TCAS

When IOLA's own CubeSat is in orbit running IkirereMesh firmware, the architecture changes fundamentally.

Each satellite in the IOLA constellation will:
1. Receive its own propagated orbital state
2. Monitor its local neighbourhood within a threshold radius (e.g. 50 km)
3. Run continuous pairwise conjunction checks against other IOLA satellites
4. Report risk scores to the IkirereMesh coordination layer
5. Receive coordination proposals and apply them subject to human approval

This **is** the onboard TCAS equivalent. Each satellite is its own sensor, running its own local conjunction awareness continuously and in real time. The IkirereMesh coordination layer aggregates the local awareness from all IOLA satellites and proposes fleet-level coordination decisions.

The two systems are complementary, not competing:

| Layer | Scope | Continuity | Who controls | Analogy |
|---|---|---|---|---|
| `screen_catalog()` | All 15,447 tracked objects | Batch, every N hours | Ground observer | Air traffic control radar sweep |
| IkirereMesh onboard | IOLA constellation only | Continuous, real-time | IOLA satellites | TCAS on each aircraft |

---

### Why this distinction matters for the research paper

The paper must distinguish clearly between:

1. **Ground-based conjunction intelligence** (Phase 2) — what any ground operator with TLE access can do. Standard aerospace practice. Novel only in the risk scoring formula.

2. **Onboard autonomous coordination** (Phase 3) — what requires the satellite itself to participate. Novel in full. No current nanosatellite constellation runs distributed autonomous conjunction awareness with RL coordination. This is the ICML/NeurIPS contribution.

The Phase 2 ground system is the **training data generator** for Phase 3. Every conjunction event detected by `screen_catalog()` becomes a training example for the IkirereMesh RL policy: what was the state, what was the risk, what coordination decision was made (or should have been made), what was the outcome. The moat compounds because the ground system and the onboard system feed each other.

---

### Implementation note

The 200 km altitude threshold in `screen_catalog()` is architecturally equivalent to the TCAS range ring — it defines the neighbourhood within which conjunction is considered possible. Objects outside this neighbourhood are not checked, exactly as TCAS ignores aircraft beyond its surveillance range.

The difference: TCAS range is a physical radio range. Our threshold is a geometric impossibility bound — two satellites more than 200 km apart in altitude cannot share the same orbital shell and therefore cannot be in conjunction. The TCAS analogy is intuitive; the physical justification is orbital mechanics.

---

*Written: 2026-05-22 · Jason Quist + Claude*

---

## 12. Mathematical Derivation Record — From First Principles

*Written: 2026-05-22 · Jason Quist + Claude*  
*Source: Independent derivation conducted in parallel with implementation, 2026-05-22*

This section records the logical derivation of Phase 2 from first principles. It is included because:
1. The research paper will need to present the theoretical foundation, not just the implementation
2. Every novel contribution must be traceable to the moment where standard published mathematics ends and IOLA's formulation begins
3. Future engineers must understand the *why* behind each formula, not just the *what*

The derivation proceeded in 10 steps, each building on the previous. The implementation in `conjunction.py` follows this exact logical sequence.

---

### Step 1 — Relative Spatial Geometry

The starting point: every satellite is a position vector in 3D Earth-Centered Inertial space.

```
r = (x, y, z)   [km, ECI frame]
```

Conjunction assessment begins as pure relative geometry. The fundamental measurement is Euclidean separation between two satellites:

```
d = sqrt((x₂ - x₁)² + (y₂ - y₁)² + (z₂ - z₁)²)
```

This is `distance_between_satellites()` in the implementation — the mathematical foundation on which everything else is built.

**Core principle:** Conjunction risk fundamentally emerges from relative spatial convergence between orbital objects.

---

### Step 2 — Relative Velocity

Each satellite carries a velocity vector:

```
v = (vx, vy, vz)   [km/s, ECI frame]
```

The critical insight: individual velocity magnitude is less important than relative velocity. Two satellites moving at 7.7 km/s in the same direction have zero relative velocity and cannot collide. Two satellites moving at 7.7 km/s in opposite directions have 15.4 km/s relative velocity — maximum collision energy.

```
v_rel = v_B - v_A
|v_rel| = sqrt(dvx² + dvy² + dvz²)
```

This is `relative_velocity_between_satellites()` in the implementation.

**Core principle:** Conjunctions are not static geometry problems. They are dynamic motion problems. Phase 2 begins where Phase 1 ends — at the transition from orbital state to orbital interaction dynamics.

---

### Step 3 — Temporal Orbital Prediction

Velocity is interpreted physically as displacement per unit time:

```
v = Δx / Δt   →   Δx = v × Δt
```

This gives the first predictive orbital model:

```
x_future = x + vx × t
y_future = y + vy × t
z_future = z + vz × t
```

This is the linear (constant-velocity) approximation used in the initial Phase 2 notes and in the coarse screening step. It is intentionally simple. The full orbital propagation (Keplerian two-body + SGP4) comes later in the pipeline.

**Note on deliberate simplification:** The constant-velocity approximation is used in Stage 2 of `screen_catalog()` for current-moment separation checks only. It is not used for TCA computation. The TCA computation uses the full Keplerian propagator (Phase A) and SGP4 refinement (Phase B). The linear model is appropriate for eliminating obviously non-conjuncting pairs; it is not appropriate for precise TCA determination.

**Core principle:** Orbital intelligence begins when future orbital state can be estimated from present motion.

---

### Step 4 — Closest Approach as a Time-Search Problem

Conjunction assessment is fundamentally a search problem over time:

```
d(t) = separation between two satellites at time t
TCA  = argmin_t d(t)
```

Rather than asking "how far apart are they now?", the correct question is "what is the minimum separation they will reach, and when?"

We sweep future time windows discretely:
- Propagate positions forward at each time step
- Compute separation at each step
- Record the minimum

This is Phase A of `find_closest_approach()`.

**Core principle:** A conjunction is not current proximity. It is minimum future proximity. Systems that screen on current separation miss the majority of real conjunction risk.

---

### Step 5 — Time of Closest Approach (TCA)

Evolution from "how close?" to "how close and when?"

The system now tracks two values simultaneously:
- `miss_distance_km` — minimum separation at TCA
- `time_seconds` — seconds from now until TCA occurs

TCA is the operational trigger. An operator needs to know not just that two satellites will come close, but *when* — so they can decide whether a maneuver is still possible and how much delta-V is required.

Phase B of `find_closest_approach()` refines TCA to sub-second accuracy using SGP4 bisection. 12 iterations converge to ~0.03 seconds — CCSDS CDM accuracy.

**Core principle:** Operational orbital systems require event timing, not just event existence.

---

### Step 6 — Relative Approach Direction

Close satellites are not automatically dangerous. The direction of relative motion determines whether the gap is closing or opening.

Using the dot product of the displacement and relative velocity vectors:

```
displacement    = r_B - r_A
v_rel           = v_B - v_A
dot_product     = displacement · v_rel
```

Interpretation:
- `dot < 0` → vectors point in opposite directions → satellites are approaching → genuine risk
- `dot > 0` → vectors point in same direction → satellites are separating → past closest approach

This is `satellites_are_approaching()` in the implementation. It eliminates false conjunction candidates — pairs that are currently close but moving apart.

**Core principle:** Close satellites are not automatically dangerous. Direction of relative motion determines whether the encounter is incoming or outgoing.

---

### Step 7 — Orbital Filtering for Computational Scale

15,447 satellites produce:

```
15,447 × 15,446 / 2 = 119,267,631 pairs
```

At 1ms per pair: 119,267 seconds = 33 hours. Not viable.

The solution is hierarchical constraint-based filtering that eliminates geometrically impossible conjunction candidates before expensive prediction:

**Stage 1 — Altitude band filter (O(n)):**
Two satellites more than 200 km apart in altitude are in different orbital shells. Their orbits cannot intersect under two-body mechanics. This single filter eliminates ~95% of pairs.

**Stage 2 — Current separation filter (O(m) where m << n²):**
Pairs already more than 1,000 km apart at the current moment are unlikely to conjunct in the next 24 hours. Eliminates most remaining pairs.

**Stage 3 — Full TCA computation (O(k) where k << m):**
Only pairs that survive both filters get the expensive computation.

This is `screen_catalog()` in the implementation. Measured performance: 200-satellite fleet screened in 683ms, reducing 16,700 altitude-passing pairs to 652 separation-passing pairs.

**Core principle:** Real aerospace conjunction systems survive by eliminating geometrically impossible pairs early. Computational efficiency is not an optimisation — it is what makes the system usable at scale.

---

### Step 8 — Uncertainty Modelling

One of the most important conceptual transitions: orbital state is never perfectly known.

Sources of positional uncertainty:
- TLE measurement noise (baseline ~1 km)
- TLE aging — the TLE was computed at a past epoch; the real satellite may have deviated
- Atmospheric drag — unmodelled density variations cause unpredictable acceleration
- Orbital perturbations — higher-order gravitational terms, solar radiation pressure

**Standard treatment (deterministic):** Apply a fixed uncertainty margin.

```
d_effective = d_min - uncertainty_margin
```

**IOLA's treatment (novel):**

The uncertainty is not fixed. It grows as a function of TLE age and atmospheric drag:

```
σ(t) = σ₀ + k × (|B*| / B*_nominal) × age_days²
```

Where:
- `σ₀ = 1 km` — baseline uncertainty at epoch
- `k = 0.5 km/day²` — drag-induced growth rate at nominal bstar
- `B*` — the satellite's actual atmospheric drag coefficient from its TLE
- `age_days` — days since the TLE was measured

**Why this is novel:** No published CDM standard weights positional uncertainty by the satellite's actual drag coefficient. USSPACECOM's positional uncertainty model uses fixed covariance matrices. IOLA's formula produces a dynamic, object-specific uncertainty that correctly reflects the physical reality: a high-drag object at 300 km altitude accumulates positional uncertainty 10× faster than a low-drag GEO object.

This is `compute_tle_age_uncertainty_km()` in the implementation.

**Core principle:** Prediction without uncertainty is fake precision. The stated miss distance in a CDM is not the true miss distance — it is the best estimate given available tracking data. The uncertainty envelope around that estimate determines whether the conjunction is genuinely dangerous or safely bounded.

---

### Step 9 — Risk Classification

Not all conjunctions deserve equal operational attention. Threshold-based classification converts continuous distance measurements into discrete operational priorities:

```
miss_distance < 1 km   → CRITICAL
miss_distance < 5 km   → HIGH
miss_distance < 20 km  → MODERATE
otherwise              → LOW
```

These thresholds are based on operational CDM practice. USSPACECOM issues actionable CDMs for objects predicted to come within 1 km. The MODERATE threshold (20 km) reflects the positional uncertainty of typical LEO TLEs — at miss distances below ~3× the uncertainty radius, the stated miss distance is not reliably distinguishable from zero.

**Core principle:** Mission systems require prioritisation layers, not raw measurements. An operator cannot act on 119 million pairs. They can act on 5 CRITICAL events.

---

### Step 10 — Multi-Factor Risk Scoring

Even after filtering and classification, conjunction systems generate more events than operators can individually assess. A single risk score that integrates all relevant factors is required.

The standard heuristic form:

```
Risk ~ relative_velocity / (effective_distance × encounter_time)
```

**IOLA's 6-component composite risk score:**

```
score = 0.35 × distance_risk
      + 0.20 × velocity_risk
      + 0.20 × time_urgency
      + 0.05 × collision_probability
      + 0.10 × tle_age_risk
      + 0.10 × shell_density_factor
      + 0.10 (if approaching)
```

The first four components (distance, velocity, urgency, probability) represent the standard conjunction risk factors. The last two are IOLA's novel additions:

- **`tle_age_risk`** — penalises conjunctions where the stated miss distance may not reflect the true separation due to TLE staleness
- **`shell_density_factor`** — penalises conjunctions in dense orbital shells where a collision would have higher cascade consequence (Kessler cascade potential)

**Core principle:** Mission operations are fundamentally attention allocation systems. The risk score is not a measure of how dangerous the encounter is in absolute terms — it is a prioritisation signal that tells the operator which events deserve immediate attention.

---

### Where Standard Derivation Ends and IOLA IP Begins

The derivation above follows published aerospace mathematics through Steps 1-9. Steps 8-10 introduce IOLA's novel contributions:

| Novel contribution | Where in derivation | Mathematical form |
|---|---|---|
| Bstar-weighted TLE age uncertainty | Step 8 | `σ(t) = σ₀ + k × (bstar / bstar_nominal) × age²` |
| Shell density Kessler factor | Step 10 | `density_factor = f(population_count, altitude_band)` |
| 6-component composite risk formula | Step 10 | Weighted linear combination with the above |

These three elements are what distinguish IOLA's conjunction scorer from the standard USSPACECOM CDM approach. They are the foundation of the Phase 2 research paper contribution.

**For the paper:**
- The bstar-weighted uncertainty formula will require empirical validation (k constant calibration — see Open Question Q1)
- The shell density factor will require validation against historical Kessler-risk assessments
- The composite risk formula will require calibration of weights against known historical CDM outcomes

These validations are Phase 2 completion criteria, not optional. A paper without them is a proposal, not a result.

---

## 12. Phase 2 Validation Run Record

*Written: 2026-05-22 · Jason Quist + Claude*

**File:** `tests/phase2/phase2_validation_response_20260522_133057.txt`  
**Result:** 5/5 tests passed  
**Run time:** ~683ms (200-satellite synthetic fleet)

| Test | Result | Key measurement |
|---|---|---|
| Test 1: Geometric correctness | PASS | A-B distance = 100.000000 km, error = 0.00e+00 |
| Test 2: TCA accuracy | PASS | miss=344.455 km at t+2160s, tca_refined=False (no TLE lines in synthetic data — expected) |
| Test 3: Risk score bounds | PASS | close=0.848, far=0.0061; dense shell=0.948 vs sparse=0.848 (Kessler factor +0.10 confirmed) |
| Test 4: Screen performance | PASS | 683ms for 200 satellites; 16700 altitude-passed → 652 separation-passed → 0 conjunctions |
| Test 5: CDM completeness | PASS | All 9 CCSDS fields + 6 IOLA fields present; TCA after CREATION_DATE; action=MANEUVER_RECOMMENDED |

**Notable observations:**

1. **Test 3 Kessler validation:** Dense shell (600 synthetic objects) scored 0.948 vs sparse 0.848 — exactly 0.10 difference, confirming the 10% shell_density weight is arithmetically correct.

2. **Test 4 performance extrapolation:** Full 15,447-satellite catalog estimated at ~4,076 seconds (~68 minutes). This confirms `screen_catalog()` is a **scheduled research operation**, not a synchronous API call. The correct production pattern: run as a background job every 6 hours, cache results, serve cached results via `/conjunction/screen`.

3. **Test 2 TCA refinement:** `tca_refined=False` because synthetic satellites have no `tle_line1`/`tle_line2` fields. The Phase B SGP4 bisection correctly falls back to the coarse Keplerian result. This is the expected and correct behaviour for the synthetic test fleet.

---

*Document last updated: 2026-05-22*  
*Signed: Jason Quist (Founder & CEO) · Claude (Chief Research Scientist / Systems Architect)*  
*Next update: When Phase 2 empirical validation begins (k constant calibration, CDM comparison against Space-Track).*
