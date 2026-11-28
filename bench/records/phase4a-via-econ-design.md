# Phase 4A slice 2 design: a search-scoped via price (issue #67)

Inventory: bench/records/phase4a-via-econ-inventory.md. The detailed
search prices one through via at RouterOptions::via_cost_mm = 3.0 mm of
track, through the Impl member via_cost_mult, which is hardcoded to 1.0
while routing (10.0 inside clean-up re-routes, /4 for a capped search
via-retry). --via-cost-mm moves every consumer at once (search, via
drops, via-in-pad, coupled pairs, the portfolio ladder). There is no
dial on the search price alone.

## Change (smallest that bites)

- RouterOptions::via_search_mult (double, default 1.0): the routing
  value of via_cost_mult. Impl constructor initialises via_cost_mult
  from it; the two clean-up exits that today restore 1.0 restore
  via_search_mult instead. Clean-up searches keep their absolute 10.0.
  Negative values clamp to 0 at the same point (0 = free vias, a legal
  probe of the lower bound).
- CLI --via-search-mult in the hidden (empty) group, like
  --redecompose and --pin-via-pen: docs/reference/cli.md needs no
  regeneration.
- Nothing else changes: via_cost_mm, the plan stage, negotiation
  crossing/history prices, the clean-up judge (len + 2 mm/via) and the
  portfolio ladder all keep their current values and meanings.

## Why this is the right shape

- Every layer-change decision the detailed search makes multiplies
  through via_cost_mult already: the via step, the cost-to-go field,
  the heuristic layer term, via drops and via-in-pad endpoints. One
  field reprices all of them coherently; admissibility of the
  heuristic is preserved (the field and the octile bound are built
  from the same via_cost).
- Default 1.0 is byte-identical: the member already multiplies every
  via price, and 1.0 is the value it has today, so the arithmetic of
  a default run is unchanged term by term.
- Determinism: the multiplier is a pure double read from the options,
  applied in the same fixed order as today; no new iteration,
  randomness or wall-clock input.

## A/B setting (one, justified; no sweep)

--via-search-mult 3: a via costs 9 mm, a two-layer dip 18 mm. At the
default, a dip beats any same-layer detour longer than 6 mm; the
human references on the worst boards use 3-7x fewer vias, i.e. they
routinely accept detours far beyond 6 mm. 3x sits just above the
portfolio own dear-vias arm (2.5x = 7.5 mm), inside the range the
existing design already treats as sane, and triples the saving a dip
must make without pricing vias at the clean-up level (10x), where
congested boards would predictably trade vias for opens.

## Tests (tests/test_via_econ.cpp, tag [via_econ])

- Default inertness: via_search_mult defaults to 1.0; a run at the
  default and a run with it set to 1.0 explicitly give identical
  routed / tracks / vias / expansions on the test_txn-style SRJ
  breakout (the test_redecomp problem shape).
- Steering: a two-layer SRJ problem, one connection between two
  top-layer pads, a top-layer keep-out wall between them whose
  on-layer detour costs ~9 mm more than the straight line. At
  via_search_mult 1 the connection dips (vias >= 2); at
  via_search_mult 8 it stays on layer (vias == 0), routed either
  way, zero DRC errors. Clean-up is disabled in this test only, to
  isolate the search price (the clean-up has its own absolute price
  and judge, unchanged by this slice).
- Flag-on determinism: with via_search_mult 3 the result is identical
  at 1 and 4 threads (routed / tracks / vias / expansions).
