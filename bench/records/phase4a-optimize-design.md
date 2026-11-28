# Phase 4A — `--optimize` pass: design (2026-11-28, issue #67)

## Problem, from the gating measurement

Median per-board via ratio on the Phase 3 gate corpus is **1.667x** the human
reference (aggregate 12070 vs 7245 vias; 69 of 83 boards above 1.0x). The excess
concentrates in short layer-change jogs: the worst boards carry hundreds of
`short_segments`, the signature of a net that drops to another layer for a few
millimetres and comes straight back. A post-route pass cannot fix the router's
via economics wholesale (that is later 4A work on via cost in search), but it can
remove the jogs that are already routed, measurably and provably safely.

## Shape of the pass

`tmk::passes::optimize_copper(board, rules, tracks, vias, opt)` — same signature
family as `octilinear_tracks` / `widen_tracks`: it rewrites the run's new copper
(the `res.tracks` / `res.vias` of a route job) against the input board, and the
call site judges it like every after-route pass (doc 05 §39): the result is kept
only if no net has more unconnected items with it than without it. Opt-in via
`--optimize-copper` (RouteJob.optimize_copper, default off — default runs are byte-identical).
Input (already-placed) copper is never modified in this slice; on the gate bench
all copper is new, so the slice is fully exercised there.


Note on naming: the router already owns `--optimize`/`--no-optimize` for its in-search
clean-up (`optimize_vias`/`lns_vias` in router.cpp, on by default) — so the 1.667x
baseline already includes that clean-up's effect, and this pass removes the geometric
jogs it leaves behind. Hence the distinct flag name.

## Stage A — collinear merge (copper-identical)

Two tracks of one net, same layer and width, meeting at a vertex V where the
copper graph has degree exactly 2, collinear and continuing straight
(cross == 0, dot > 0), both unlocked, neither a tuning pattern, no via, arc or
pad at V and no third track touching or crossing V — are replaced by the single
track a→b. The union of the two capsules **is** the merged capsule (same line,
same width, shared endpoint), so the copper shape is bit-identical: no legality
check is needed and DRC cannot change. This is the degenerate case of jog
straightening and it also cleans up after stage B.

## Stage B — via-jog collapse (the via reducer)

Pattern, all in the run's new copper, one net N, layers L != M:

```
T1 (layer L) ── P ●via V1   T2 (layer M, length <= max_jog, default 5 mm)   Q ●via V2 ── T3 (layer L)
```

Replace V1 + T2 + V2 with one track P→Q on layer L at T1/T3's width (T1.width
must equal T3.width). Removes 2 vias per hit. Guards, all mandatory:

- V1/V2 are through vias spanning L and M, unlocked, not `free` (stitching);
  T1/T2/T3 unlocked, not tuning patterns.
- Degree discipline at P and Q over the **whole board**: the pattern's tracks
  are the only track endpoints there, no track interior passes through, no arc
  touches, and **no pad shape of any net contains P or Q** (a via in or on a pad
  is a connection point, never a jog).
- Net N has no zone on the board (a via may be a plane tie; zones are excluded
  wholesale in this slice) and is not a coupled-pair member
  (`Obstacles::coupling_net` — pair geometry is not ours to move).
- Exact legality: `Obstacles::segment_state(P, Q, L, width, N) == 0` against the
  full board state (the router's own exact check, the one octilinear trusts).

Why the check is sound on a per-net working copy: obstacles are rebuilt per net
from the current board, so another net never sees a stale state. Within one net,
items this pass removed are the net's own copper (own copper never blocks an
own-net probe) and items it added are likewise its own — staleness can only make
the pass *miss* a collapse, never accept an illegal one. Removing copper cannot
create a clearance violation anywhere; the only new copper is the replacement
segment, which is exactly checked, and connectivity is preserved by
construction (P and Q stay joined) and independently re-judged at the call site.

## Determinism and limits

Candidates are visited in (net, position, index) order; all geometry is integer
nm; the only budget is a count of exact checks (`work_limit`, as in octilinear).
No wall clock anywhere: the seed_determinism gate is unaffected.

## Later slices (not this one)

Whole-board mode (input copper too, via the finish path); multi-segment jogs
(dogleg middles); unequal-width jogs with a neck rule; stub/antenna removal;
and the search-side work the measurement points at — via cost and layer
preference during routing, which is where the remaining ~0.6x of the median
must come from.
