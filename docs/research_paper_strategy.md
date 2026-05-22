# IOLA Research Paper Strategy
## For the Record — 2026-05-22

*Recorded from research discussion. Permanent reference for Phase 3 and paper writing.*

---

## What goes in the paper, by section

**Background / System Design — Phase 1 (standard published work)**
Cite Vallado 4th ed. for ECI coordinates, sun position almanac, conical shadow geometry.
Cite Hoots & Roehrich (1980) for SGP4.
Cite sgp4 Python library.
Do NOT re-derive published mathematics. State what was used, cite the source, move on.

**Methodology — Phase 2 (boundary between standard and novel)**
The 10-step logical derivation in docs/phase2_engineering_notes.md Section 11 is the
foundation of this section. It shows precisely where standard published aerospace
mathematics ends and IOLA's contribution begins.

The departure point is Step 8 (bstar-weighted TLE age uncertainty) and Step 10
(shell density Kessler cascade factor). Without this derivation documented, a reviewer
cannot locate the novel contribution. It is now in the permanent record.

**Core Contribution — Phase 3 (the paper's main result)**
IkirereMesh: RL state space, action space, reward function.
This is the section that targets ICML and NeurIPS.
When Phase 3 is built, the Phase 3 engineering notes must contain a derivation at
least as detailed as Phase 2 Section 11, but for the RL formulation.
This is where the moat is mathematically defensible.

---

## The three novel contributions (as of Phase 2 completion)

1. **Bstar-weighted TLE age uncertainty**
   σ(t) = σ₀ + k × (|B*| / B*_nominal) × age_days²
   No published CDM standard weights positional uncertainty by drag-coefficient-adjusted
   TLE age. USSPACECOM uses fixed covariance matrices. IOLA's is dynamic and object-specific.
   Requires: k constant calibration against Space-Track position data (PIN-002).

2. **Shell density Kessler cascade factor**
   density_factor = f(population_count_in_100km_band, altitude)
   No published CDM standard uses orbital shell population density as a risk component.
   USSPACECOM CDMs report Pc for the specific pair only.
   IOLA's scorer also weights cascade potential of the shell.
   Requires: validation against historical Kessler-risk assessments.

3. **6-component composite risk formula** (combines 1 and 2 with standard factors)
   score = 0.35×distance + 0.20×velocity + 0.20×urgency + 0.05×Pc + 0.10×tle_age + 0.10×shell_density
   Requires: weight calibration against historical Space-Track CDM outcomes.

---

## What Phase 3 must add for the paper

The RL formulation is the main result. It must include:

- State space definition: what the agent observes (orbital state, risk scores,
  shell density, communication windows, power availability, coverage footprints)
- Action space: what the agent can propose (timing adjustments, attitude changes,
  downlink scheduling, imaging prioritisation)
- Reward function: the novel engineering here — it must incorporate the Kessler
  cascade factor from Phase 2 so the agent learns to avoid contributing to
  cascade risk, not just individual collision risk
- Training methodology and convergence analysis
- Comparison against baseline (non-coordinated operation)

Paper target: ICML / NeurIPS — multi-agent systems, orbital coordination.
Secondary target: IEEE Aerospace — system-level results.

---

## Rule for all three phases

Phase 1 engineering notes = operational log. Bugs, decisions, architecture, validation.
Phase 2 engineering notes = operational log + mathematical derivation at the novel boundary.
Phase 3 engineering notes = operational log + full RL formulation derivation.

Forward. Not back.

*Written: 2026-05-22*
*Signed: Jason Quist (Founder & CEO) · Claude (Chief Research Scientist / Systems Architect)*
