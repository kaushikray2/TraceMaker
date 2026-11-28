# Phase 4A slice 2 inventory: where via cost lives in the router (issue #67)

Read on zorinbox-1, branch tm-phase4a-via-econ at 5fef963, 2026-11-28.
Line numbers are src/route/router.cpp unless another file is named.
Slice 1 (bench/records/phase4a-ab-2026-11-28.md) proved a post-route pass
cannot move the via ratio (1 kept collapse of 67 candidate jogs); the owner
re-scoped 4A to search-side via economics. This inventory maps every place
the router prices a via or a layer today, to find where a search-side
dial can bite.

## 1. The detailed A* search (the only place vias are priced per decision)

- One flat price per through via, independent of how many layers it spans:
  the via step to any other layer at the same lattice cell costs
  `via_cost + vextra + textra(landing cell)` (line 2645), where
  `via_cost = via_cost_mm * via_cost_mult * via_mult_of(net)` in mm,
  converted to the search integer units at line 2298-2299.
  `RouterOptions::via_cost_mm = 3.0` (router.hpp): one via costs as much as
  3 mm of track. A two-layer dip (down and back) therefore costs 6 mm and
  beats any same-layer detour longer than 6 mm.
- Blind/micro fallback vias, tried only where the through via is blocked
  and the board allows them, cost 1.5x via_cost (line 2631).
- `via_cost_at` extras (line 1397): a via inside another net dense-package
  fan-out region pays `pin_via_pen_mm` (RouterOptions, default 0 = off).
- The heuristic follows the same price: the octile bound adds one via_cost
  when the state layer differs from the target layer (lines 2337-2348), and
  the cost-to-go field is built with the same via_cost (build_field call,
  line 2314). Both stay admissible whatever the price is.
- Search endpoints price layer changes the same way: via drops
  (--via-drops) cost stub length + the via price (line 1625); via-in-pad
  endpoints cost 4x the via price (line 1712, a last resort).
- `via_cost_mult` (Impl member, line 3293) is the search-scoped
  multiplier: 1.0 while routing, set to 10.0 inside the clean-up
  re-routes (lines 6288, 6363), divided by 4 for the via-retry of a
  capped search (lines 3224-3231; RouterOptions::via_retry, default off).
  It is hardcoded: no option reaches it.
- Per-net multiplier `via_mult_of(net)`: RouterOptions::critical_via_mult
  (default 1.0) applied to critical nets only; route_job raises it to 3.0
  for component-rule critical nets under --si-rules unless given
  (src/app/route_job.cpp:1029).
- Planar steps cost on_layer(pitch or pitch*sqrt2, layer) + cell extras +
  bend (step/2 per 45 deg, 2*step per 90 deg) + direction/diagonal
  penalties (lines 2573-2595). on_layer applies layer_cost_pm (per-layer
  per-mille track cost, default all 1000 = neutral; --layer-cost in
  route_job). Being on a layer can be priced; changing layer is priced
  only by the via step above.

## 2. Negotiation (PathFinder): crossings get dearer, vias do not

- Negotiated searches are the same search with soft=true. Crossing
  another net copper costs soft_unit = soft_cost_mm (default 1.0 mm) *
  (1 + soft_growth * min(pass, 20)); soft_growth defaults to 0, so the
  crossing price is flat unless --soft-growth is given (lines 7668, 8176).
- History: hist_cost(cell) = history * pitch * history_weight
  (history_weight = 2.0 pitches per recorded conflict, line 1205-1208),
  charged as a cell extra and at 4x on soft cells (line 1393).
- The via price is the same in the strict pass and in every negotiated
  pass: as passes accumulate history and crossing costs, vias become
  relatively cheaper, never dearer.

## 3. Layer preference (prices position, never transitions)

- layer_dir_pen (default -1 = automatic: 0.3 on breakout boards only,
  else 0): pitches per orthogonal step against a layer preferred
  direction. layer_assign (default off, two-layer boards only):
  layer_assign_pen = 0.4 pitches per step on the non-preferred layer.
  layer_diag_pen (default empty = off). None of these charges a layer
  change; a route may change layer at every step and pay only via_cost
  per change.

## 4. Plan / MST stage: layer-blind

- plan() (line 934) runs Prim over pad clusters with edge weight =
  centre distance, or copper gap with plan_gap (default on); the only
  adder is radial_penalty_mm (10 mm) for same-package pin pairs when
  radial_supply is on (default off). No via or layer term: the pairing
  is chosen as if layers were free. 4B redecomp (line 3776+) adds a
  history-congestion sample capped at 10% of the geometric base; still
  no via term.

## 5. The router own clean-up (--optimize, default on): mismatched prices

- RouterOptions::optimize = true (--no-optimize skips). At the end of a
  run, on a best state with budget left: recouple split pairs,
  optimize_vias (up to 4 rounds), lns_vias(400), then smoothing and
  length tuning (lines 8523-8553). tidy_sweep (opt.tidy, default 0 =
  off) is the same idea inside the pass loop (line 8362).
- optimize_vias and lns_vias re-route with via_cost_mult = 10 (a via
  costs 30 mm in their searches) but JUDGE the result with a hardcoded
  len + 2 mm per via (the 2e6 constant in their cost_of lambdas, lines
  6246, 6307, 6373): a re-route that removes 2 vias at +5 mm length is
  rejected (5 > 2*2) even though the search that produced it priced
  those vias at 30 mm each. tidy_sweep searches at the routing
  multiplier and judges at the same 2 mm per via.
- Slice 1 --optimize-copper is a separate after-route pass in
  route_job; it is not this clean-up.

## 6. Portfolio: via cost is diversified, then outvoted by completion

- The designed eight variants scale via_cost_mm by 0.4 / 1.0 / 2.5
  (lines 8802-8804); the breakout list draws 0.5 / 1.0 / 1.5 (line
  8785); seeded extras cycle 0.4 / 1.0 / 2.5 (line 8814). The winner
  order is routed, then bus_left, then vias, then length (better_r,
  line 8913): a dear-vias variant wins only when it routes at least as
  much as every other variant.
- With --variants 1 (the seeded measurement protocol) there is no
  portfolio: variant 0 runs the base options unchanged.

## 7. CLI surface

- --via-cost-mm (src/app/main.cpp:1179, VISIBLE group, in
  docs/reference/cli.md) sets RouterOptions::via_cost_mm for every
  consumer at once: the search via step, via drops, via-in-pad (4x),
  coupled-pair searches (2 * via_cost_mm flat, line 4528, no mult),
  the field heuristic, and the portfolio variant ladder that scales
  it. There is no search-scoped dial: an experiment cannot raise the
  price the detailed search pays for a layer change without also
  repricing escapes, drops, pairs and the variant ladder.

## Conclusion: where the slice can bite

The bite point is via_cost_mult: a search-scoped multiplier that
already exists as an Impl member, already feeds the via step, the
field, the heuristic endpoint costs, via drops and via-in-pad, and is
hardcoded to 1.0 while routing. Exposing it as a RouterOptions field
(default 1.0) is the smallest search-side change: one new dial on the
price every layer-change decision in the detailed search pays, with
escapes/drops/pairs keeping their tuned relationship to via_cost_mm
(they multiply through the same member today), the clean-up keeping
its own absolute 10.0 search price, and the plan stage untouched.
