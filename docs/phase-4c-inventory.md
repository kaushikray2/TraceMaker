# Phase 4C inventory — engine signal-integrity physics (issue #69)

Taken at 3add24c (base of tm-phase4c-si), 2026-11-28. Every claim below names the file it was read from.

## 1. Engineered high-speed fixtures that exist today

- `tests/test_tuning_profiles.cpp` — Phase 3 item 1 (#37): crules impedance LineSolutions become
  per-layer track widths; synthetic boards written as temp .kicad_pcb files.
- `tests/test_diff_pair.cpp` — pair geometry and per-layer pair rules (#38 negotiated pairs, #61
  per-layer gap floors); `src/route/diff_pair.cpp` holds `pair_rule()` (per-layer width/gap from
  the crules impedance maps).
- `src/crules/test_crules.cpp` — catalogue / detect / evaluate tests; reads the PCBench fixture
  board `bench/data/freerouting/scripts/benchmark/fixtures/PCBench/1Bitsy_1bitsy/unrouted.kicad_pcb`.
- `tests/test_return_path.cpp` — the reference-return audit (below) on synthetic boards.
- `tests/test_passes.cpp` [passes][stitch] — the stitch pass on synthetic boards (grid stitching,
  blocked sites, one return-path case: a single-ended signal via gets one plane via within the
  distance, DRC-checked after refill).
- `tests/integration/crules_two_stage.py`, `tests/integration/rule_parity/` — crules integration.
- `bench/make_delay_boards.py`, `bench/make_bus_boards.py` — generated boards;
  `bench/drc_judge.py` — the KiCad DRC judge used for added-error counts; PCBench tier lists in
  `~/tm-gate3/tier{B,C,D}.txt`.
- High-speed marking: `crules::critical_nets()` (src/crules/critical.hpp, used at
  src/app/route_job.cpp:1056) derives critical nets from component roles AND differential pairs;
  with `--si-rules` they are routed first, with a via-cost multiplier (x3) and split costs.

## 2. Item (a) — ground-stitching vias at layer transitions: MOSTLY BUILT, post-hoc

- `src/passes/stitch.cpp` (326 lines) implements plane grid stitching and return-path stitching:
  for each (signal, plane, distance) request it ring-searches 16 directions at growing radius
  around each signal via and places the first legal plane via (exact via check, fill test, and a
  second-refill proof that the via joins its net's fill on two layers).
- Wiring (src/app/route_job.cpp): `--stitch-vias planes|return|all`, `--stitch-return` options,
  crules `reference_plane` rules, and — under `--si-rules` (with `--no-si-stitch` to opt out) —
  the reference-return audit (`src/analysis/return_path.cpp`, read-only geometric audit: copper
  under the trace, detours, layer changes and whether each closes through a stitch within a
  radius, default 5.0 mm) drives stitch requests for critical nets whose layer change has the
  same reference net on both sides and no stitch. Distance is
  min(audit radius, catalogue `stitch_via_within_mm` = 5.08 mm, TI SPRAAR7J's 200 mil).
- The pass runs as an after-route transaction: kept only if no net gains unconnected items.
- GAPS against the 4C wording ("co-synthesised"):
  1. Placement is post-hoc and per-via greedy: the search chose the signal via position with no
     knowledge of the stitch; the stitch takes whatever room is left (blocked sites and dropped
     vias are counted, not prevented).
  2. Differential-pair transitions are treated as two independent single-ended vias. The first
     half (sorted by position) gets a stitch at the first legal compass point at minimum radius;
     the second half counts as served if that via happens to lie within the (large) distance.
     Nothing centres the shared return via on the transition, and with a tight distance the two
     halves can each draw their own stitch, crowding one transition with two plane vias.
  3. There is no in-search co-synthesis: no reservation of a stitch site when a critical via is
     committed. (Recorded as the long-term gap; not this slice.)

## 3. Item (b) — crosstalk: NO MODEL EXISTS

- `src/drc/coupling.cpp` + `tests/test_coupling.cpp` implement KiCad 10.0.6's diff-pair coupling
  GEOMETRY (parallel-run gap between the P and N halves of one pair), used by the DRC parity
  check and by `route/obstacles.cpp` (`coupling_state`) during search. It is pair-internal
  geometry, not victim/aggressor crosstalk between different nets.
- No crosstalk estimate, coupled-length accounting, noise budget, or crosstalk term in any path
  cost exists anywhere in src/ (searched: xtalk, cross-talk, aggressor, victim, noise budget).
- The crules catalogue (src/crules/catalogue.json, `general_high_speed`, sourced to TI
  SPRAAR7J) carries spacing values — `pair_to_other_signal_mm` 0.76, `pair_to_clock_mm` 1.27,
  `plane_edge_min_mm` 2.29, `max_via_stub_mm` 0.38 — that NO engine code consumes (grep across
  src/route, src/drc, src/passes, src/crules finds no reader). Only `stitch_via_within_mm` is
  consumed. A crosstalk slice therefore starts from a design study (sourced coupled-line model
  + budget semantics), not from existing machinery.

## 4. Item (c) — meanders: POST-HOC TROMBONES EXIST

- Length tuning lives in the router (src/route/router.cpp, ~lines 6486 and 6757): trombone
  meanders are added on the longest straight segments of a routed net, each candidate checked
  exactly, the net never made worse. `src/drc/length.cpp` measures; tuning profiles (3C) set
  per-layer widths. There is no corridor reservation during the search and no octilinear/arc
  meander geometry — replacing the trombone stage is a routing-core change with wide blast
  radius.

## 5. Consequence for the first slice

Item (a) is the only one with complete machinery to build on (stitch pass, return audit, crules
critical pairs, a sourced distance constant). The first slice closes gap 2: pair-transition
return stitching — one stitch via per differential-pair layer transition, searched around the
transition midpoint so it serves both halves symmetrically — behind an opt-in flag, default off
(byte-identical behaviour). Design: docs/phase-4c-design.md.
