# Phase 4B inventory: multi-pin topology and pin/gate swapping (issue 68)

Measured and read on zorinbox-1, branch tm-phase4b-topology at 3add24c, 2026-11-28.

## 1. How multi-pin nets are decomposed today

- The decomposition lives in `Router::Impl::plan()` in `src/route/router.cpp` (the "Connections" section,
  ~line 864). It builds, per net, the clusters of pads already joined by existing copper (union-find over
  copper items), then runs Prim over the clusters: each new cluster joins by its cheapest pad pair
  (centre distance, or copper gap with `--plan-gap`; a pad may instead target a zone fill of its net).
  The result is the connection list (`std::vector<Connection>`, router.hpp:375): pad-to-pad or pad-to-zone
  two-terminal connections. A multi-pin net becomes a tree of two-terminal connections; there is no
  Steiner-point machinery in the detailed router (Steiner/corridor demand exists only in the global
  router, `src/route/global_router.hpp`).
- **The decomposition is static per route job.** `plan(uf)` is called exactly once (router.cpp:7525),
  before the first pass. The negotiation loop (passes at router.cpp:8010, restarts at ~7685) routes,
  rips and re-routes those fixed connections; victims are re-queued, never re-paired. The only mid-route
  topology changes are local repairs: `plane_fallback` (a pad-to-plane connection becomes pad-to-pad,
  D155) and pair re-coupling. Restarts re-order the same connections hardest-first; they do not re-plan.
- What DOES evolve live is the PathFinder history: `history` (FlatU64U16, per lattice cell, router.cpp:450)
  is bumped on every rip (`bump_history`, router.cpp:3022) and halved on deep restarts. Searches price it
  via `hist_cost()` (router.cpp:1205). So congestion knowledge accumulates in the cost field, but the
  spanning tree it acts on never changes: a bus net whose MST sends four pins down one corridor keeps
  that pairing for the whole job, and negotiation can only pay history to route around it.
- Cluster identity for a live re-plan already exists: `joined_roots()` (router.cpp:3752) unions the
  fixed-copper groups (`init_root[pad_item[pad]]`) through the currently routed connections of a net.
  A re-decomposition at a pass boundary can contract those clusters and re-run Prim over the still-open
  connections with history-priced edges, without touching routed copper.

## 2. Static-decomposition exposure: multi-pin census of the gate tiers

Pads per net counted from the fixture boards in ~/tm-gate3/fix (nets with >= 3 pads):

| Tier | Boards | Heaviest boards (multi-pin pads / largest net) |
|---|---|---|
| B (40) | bumps 548/102, kitspace_test-jig 417/104, Hardware_Playground_E3 400/111, poncho_fpga 322/109, EtherCAT_shield 292/92 |
| C (30) | kitspace_d20 621/34, mechkeys_MF68 619/41, zx-sizif-512-ext 617/104, 40-channel-hv-switching 598/109, Ergodone 550/45 |
| D (22) | Aleste-520EX 1894/271, LeeChee 1488/293, MonApollo 1287/268, mini_mass 1225/425 |

Every tier board carries dozens of multi-pin nets; the MST pairing decision is made hundreds of times
per board and never revisited. The A/B set for the re-decomposition slice is drawn from the bus/clock
heavy mid-size boards: poncho_fpga (FPGA bus), EtherCAT_shield_v1, kitspace_d20_tri_r0.3,
mechkeys_MF68+10, digital_clock_led_clock_3_and_4_digit (clock distribution), zx-sizif-512-ext.

## 3. bench/pin_swap.py: state and verdict

- Exists, 337 lines, complete and documented (doc 18 C2, doc 05 section 56, M20). Subcommands:
  `scan` (find swappable groups + oracle saving), `make` (write boards with the oracle assignment,
  permuting the pads own `(net ...)` nodes so the rest round-trips byte for byte), `compare`
  (routed/vias/length/clean for base vs swapped runs, KiCad-judged). Groups are found by construction,
  not design intent: connector signal pins (J/P/CN/CON/X refs) and resistor arrays (RN/RP, 4/8/16 pads).
  The oracle is a free-assignment upper bound (scipy Hungarian on distance to the nets nearest outside
  pad); it measures what swap freedom would be worth, not what is legal.
- **Already measured** (bench/records/m20-c2, 2026-10-27): on the 20 failing tier B-D boards with a
  group, oracle swaps changed open connections 982 -> 978 in total (5 boards better, 5 worse), vias
  3548 -> 3434, length 102180 -> 101261 mm; median per board: opens +0.0, vias -3, length -10.1 mm;
  clean 0 -> 0. On the 10 quick boards the same picture. That is the CEILING (free assignment, legality
  ignored): completion gain is noise.
- Verdict for 4B(b): an in-engine legal pin/gate swap pass cannot beat its own oracle bound, so it is
  **not viable as the next slice** on completion grounds. It could still pay as a via/length polish on
  connector-heavy boards (Teensy layout: vias 460 -> 421), but that belongs behind the 4A optimize pass
  in value. Recommendation: keep pin_swap.py as the measurement oracle; do not build the engine pass
  unless a board family shows a group-level ratsnest saving an order larger than the m20-c2 medians.

## 4. Slice 1 design (this lane)

`--redecompose N` (RouterOptions::redecomp_every, default 0 = off): at negotiation pass boundaries
where pass > 0 and pass % N == 0, for each net whose open connections are plain pad-to-pad (no zone
targets, no coupled-pair halves, no bus/bundle lanes), contract the clusters joined by routed copper
(joined_roots machinery), rebuild the spanning tree over the open connections clusters with edge
weight = pad-pair distance + history congestion sampled along the segment (hist_cost, all layers),
Prim with the same deterministic tie behaviour as plan(), and rewrite the open connections pad
endpoints in place (connection count per net is invariant: contracting a tree along routed edges
leaves exactly the open edges as the spanning forest). Counters in RouteResult (redecomp_rounds,
redecomp_changed) and a stage event per round. Deterministic: weights are pure functions of the
history map contents (lookups, never iteration order), Prim scans in fixed index order.
