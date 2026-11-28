# Phase 4C design — first slice: pair-transition return stitching (issue #69)

Inventory: docs/phase-4c-inventory.md. This note records the pick, the sourced basis, and the
exact semantics of the slice. Written 2026-11-28.

## The pick

Item (a), narrowed to the gap the inventory proves: differential-pair layer transitions are
stitched per half, not per transition. Items (b) and (c) are not first slices: (b) has no model
at all in the engine (a sourced coupled-line model and budget semantics are a design study of
their own), and (c) means replacing the router's trombone tuning stage, a routing-core change
whose blast radius is the whole length-tuning path. Item (a) has the full machinery in place —
stitch pass, reference-return audit, crules critical pairs, a sourced distance — and one
well-bounded defect inside it.

## Sourced basis (read, not remembered)

TI SPRAAR7J, *High-Speed Interface Layout Guidelines* (2023), §2 "General High-Speed Signal
Routing", Figure 2-11 (read from the TI PDF on 2026-11-28): "The entirety of any high-speed
signal trace should maintain the same GND reference from origination to termination. If unable
to maintain the same GND reference, via-stitch both GND planes together to ensure continuous
grounding and uniform impedance. Place these stitching vias **symmetrically within 200 mils
(center-to-center, closer is better) of the signal transition vias**." The figure shows ONE GND
stitching via serving a transition, dimensioned 200 mil (max) to the signal vias. The
catalogue's `stitch_via_within_mm` = 5.08 mm is this 200 mil.

The current pass deviates from that guidance for pairs: it places the stitch relative to one
half's via (whichever sorts first), at the first legal compass point; the other half is served
only if that via happens to lie within the distance, and at a tight distance each half draws
its own stitch for the same transition.

## Semantics of the slice

Opt-in: `StitchOptions::pair_transitions` + `StitchOptions::pairs`, wired to the route option
`--stitch-pair-transitions` (default off; off is the old code path untouched, so default
behaviour is byte-identical). When on, for every pair whose both halves ask for return
stitching to the same plane (any source: --stitch-return, a crules reference_plane rule, or the
--si-rules audit loop):

- The halves vias are grouped into transitions: a via of one half and the nearest unused via
- A transition already served (a plane via or plated pad within the distance of both vias)
  needs nothing.
- Otherwise one plane via is searched on rings of 16 directions around the transition
  MIDPOINT, nearest ring first, exactly as the per-via search searches around a signal via.
  Ring bounds guarantee any candidate is clear of the copper of both vias and within the
  distance (the smaller distance of the two halves) of both; the placement itself reuses the
  exact check of the pass (try_place: obstacle state, fill test, two-layer join proof after
  refill).
- If no joint site exists, nothing is placed for the transition here and the existing per-via
  search runs for both halves unchanged (fallback, never a regression).
- Accounting: StitchResult::pair_stitches counts the joint placements; the per-half
  StitchReturn rows credit both halves through the existing ties bookkeeping, and the route
  summary gains stitch.pair_stitch_vias.

Determinism: pairs are sorted and deduplicated, vias are processed in the same (x, y) order
the per-via search uses, ring geometry is integer — the result is a pure function of the board.

## Tests

tests/test_passes.cpp [passes][stitch], on the synthetic two-plane board:

1. A pair transition (tracks in on F.Cu, out on B.Cu, open copper east) gets exactly one
   return via, on the pair axis at the midpoint height, equidistant from both vias; the rows
   of both halves report stitched; the board with the via refills with 0 DRC errors; a repeat
   run is identical.
2. The same board with the option off reproduces the old placement exactly (anchored on the
   via of the first half), pinning the default path.
3. At distance 1 mm no joint site exists: the joint search places nothing and the per-via
   fallback serves the first half alone — the second half stays unstitched, as today.

## Not in this slice

- In-search co-synthesis (reserving the stitch site when the search commits a critical via) —
  the long-term form of (a); it changes the search core and needs its own design.
- The reference-return audit is unchanged: it still reports per net. Its per-net missing
  count and the per-half rows of the pass can therefore both describe one transition twice;
  pair_stitch_vias in the summary is the transition-level number.
- Items (b) and (c) — see the inventory for their starting points.
