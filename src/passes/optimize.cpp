// Copyright (C) 2026 SiliconBrane Inc.
//
// This file is part of TraceMaker (SiliconBrane fork).
//
// TraceMaker is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// TraceMaker is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with TraceMaker. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: GPL-3.0-or-later
#include "passes/optimize.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <tuple>
#include <utility>

#include "drc/copper.hpp"
#include "geom/shape.hpp"
#include "route/obstacles.hpp"

namespace tmk::passes {
namespace {

using model::Point;
using geom::i128;

using Pt = std::pair<Coord, Coord>;
Pt key(Point p) { return {p.x, p.y}; }

i128 cross(Point a, Point b, Point c) {  // (b-a) x (c-a)
  return static_cast<i128>(b.x - a.x) * (c.y - a.y) - static_cast<i128>(b.y - a.y) * (c.x - a.x);
}
i128 dot(Point a, Point b, Point c) {  // (b-a) . (c-a)
  return static_cast<i128>(b.x - a.x) * (c.x - a.x) + static_cast<i128>(b.y - a.y) * (c.y - a.y);
}
double len(Point a, Point b) { return std::hypot(static_cast<double>(b.x - a.x), static_cast<double>(b.y - a.y)); }

// A snapshot index over a working board's copper: who ends where, what passes through a point, what sits on
// a point. Rebuilt whenever the working board changes; the pass never trusts a stale one for a decision
// that could remove copper (stage A's merges are decided from a fresh index each sweep, stage B rebuilds
// per candidate).
struct Index {
  std::map<Pt, std::vector<std::pair<int, int>>> ends;  // point -> (track index, 0 = a end, 1 = b end)
  std::map<Pt, std::vector<int>> vias_at;               // point -> via indices
  std::set<Pt> arc_pts;                                 // arc endpoints and midpoints
  std::map<std::pair<long long, long long>, std::vector<int>> cells;  // 4 mm cells -> tracks whose box meets the cell

  explicit Index(const model::Board& w) {
    for (int i = 0; i < static_cast<int>(w.tracks.size()); ++i) {
      const auto& t = w.tracks[static_cast<std::size_t>(i)];
      ends[key(t.a)].push_back({i, 0});
      ends[key(t.b)].push_back({i, 1});
      const long long x0 = std::min(t.a.x, t.b.x) / 4'000'000, x1 = std::max(t.a.x, t.b.x) / 4'000'000;
      const long long y0 = std::min(t.a.y, t.b.y) / 4'000'000, y1 = std::max(t.a.y, t.b.y) / 4'000'000;
      for (long long cx = x0; cx <= x1; ++cx)
        for (long long cy = y0; cy <= y1; ++cy) cells[{cx, cy}].push_back(i);
    }
    for (int i = 0; i < static_cast<int>(w.vias.size()); ++i) vias_at[key(w.vias[static_cast<std::size_t>(i)].pos)].push_back(i);
    for (const auto& a : w.arcs) {
      arc_pts.insert(key(a.a));
      arc_pts.insert(key(a.mid));
      arc_pts.insert(key(a.b));
    }
  }

  // True when some track's interior runs through p (endpoints do not count). `skip` holds track indices to
  // ignore (the pattern's own tracks).
  bool interior_through(Point p, const std::set<int>& skip) const {
    const auto it = cells.find({p.x / 4'000'000, p.y / 4'000'000});
    if (it == cells.end()) return false;
    for (const int i : it->second) {
      if (skip.count(i)) continue;
      // The caller passes the working board's tracks through a thread-local pointer set by build_inplace;
      // see tracks_ below.
      const model::Track& t = (*tracks_)[static_cast<std::size_t>(i)];
      if (t.a == p || t.b == p) continue;
      if (cross(t.a, t.b, p) == 0 && dot(t.a, p, t.b) > 0 && dot(t.b, p, t.a) > 0) return true;
    }
    return false;
  }
  const std::vector<model::Track>* tracks_ = nullptr;
};

Index build_index(const model::Board& w) {
  Index ix(w);
  ix.tracks_ = &w.tracks;
  return ix;
}

// True when any pad's copper covers p (a via there is a connection point, never a jog). The centre-distance
// prefilter over-estimates every pad's reach, so it can only skip pads that cannot cover p.
bool pad_covers(const model::Board& w, Point p) {
  const geom::Shape pt = geom::Shape::point(p, 0);
  for (const auto& pad : w.pads) {
    const Coord reach = std::max(pad.size_x, pad.size_y) + 2'000'000;  // copper extent + drill offset + custom prims slack
    if (std::abs(pad.pos.x - p.x) > reach || std::abs(pad.pos.y - p.y) > reach) continue;
    for (const auto& s : drc::pad_shapes(pad))
      if (geom::gap(s, pt) <= 0) return true;
  }
  return false;
}

// Stage A: collinear merges. One sweep decides from a fresh index and applies merges that share no track;
// sweeps repeat until nothing merges (a straight run collapses over a few sweeps).
int merge_sweeps(model::Board& w, std::size_t base_t) {
  int total = 0;
  for (;;) {
    const Index ix = build_index(w);
    std::set<int> used;
    std::vector<std::pair<int, model::Track>> rewrites;  // track index -> merged track
    std::vector<int> drops;
    for (int i = static_cast<int>(base_t); i < static_cast<int>(w.tracks.size()); ++i) {
      if (used.count(i)) continue;
      const model::Track& t = w.tracks[static_cast<std::size_t>(i)];
      if (t.locked || t.tuning_pattern || t.a == t.b) continue;
      for (const int end : {0, 1}) {
        const Point v = end == 0 ? t.a : t.b;
        const auto eit = ix.ends.find(key(v));
        if (eit == ix.ends.end() || eit->second.size() != 2) continue;  // degree must be exactly two
        const auto other = eit->second[0].first == i ? eit->second[1] : eit->second[0];
        const int j = other.first;
        if (j == i || j < static_cast<int>(base_t) || used.count(j)) continue;
        const model::Track& u = w.tracks[static_cast<std::size_t>(j)];
        if (u.locked || u.tuning_pattern) continue;
        if (u.net != t.net || u.layer != t.layer || u.width != t.width) continue;
        const Point far_t = end == 0 ? t.b : t.a;
        const Point far_u = other.second == 0 ? u.b : u.a;
        if (cross(v, far_t, far_u) != 0 || dot(v, far_t, far_u) >= 0) continue;  // straight through: the far ends lie on opposite sides of v (dot < 0); a fold-back has them on the same side
        if (ix.vias_at.count(key(v)) || ix.arc_pts.count(key(v))) continue;
        if (ix.interior_through(v, {i, j})) continue;
        if (pad_covers(w, v)) continue;
        model::Track m = t;
        m.a = far_t;
        m.b = far_u;
        rewrites.push_back({i, m});
        drops.push_back(j);
        used.insert(i);
        used.insert(j);
        ++total;
        break;
      }
    }
    if (rewrites.empty()) return total;
    for (const auto& [i, m] : rewrites) w.tracks[static_cast<std::size_t>(i)] = m;
    std::sort(drops.begin(), drops.end(), std::greater<>());
    for (const int j : drops) w.tracks.erase(w.tracks.begin() + j);
  }
}

// Canonical (direction-free) key of a jog's two via positions, for the refused set.
std::tuple<Coord, Coord, Coord, Coord> jog_key(Point p, Point q) {
  return (p.x < q.x || (p.x == q.x && p.y < q.y)) ? std::tuple{p.x, p.y, q.x, q.y} : std::tuple{q.x, q.y, p.x, p.y};
}

struct Jog {
  int v1 = -1, v2 = -1, mid = -1;  // indices into w.vias / w.tracks
  Point p, q;
  int layer = -1;  // the layer the replacement runs on (the outer tracks' layer)
  Coord width = 0;
  model::NetId net = 0;
};

// Finds the first via jog of `net` in the working board, in via-index order, skipping refused (p, q) pairs.
// All guards of the design note except the exact check are applied here.
bool find_jog(const model::Board& w, const Index& ix, std::size_t base_t, std::size_t base_v, model::NetId net,
              const OptimizeOptions& opt, const std::set<std::tuple<Coord, Coord, Coord, Coord>>& refused, Jog& out) {
  auto ends_at = [&](Point pt) -> const std::vector<std::pair<int, int>>* {
    const auto it = ix.ends.find(key(pt));
    return it == ix.ends.end() ? nullptr : &it->second;
  };
  for (int vi = static_cast<int>(base_v); vi < static_cast<int>(w.vias.size()); ++vi) {
    const model::Via& v1 = w.vias[static_cast<std::size_t>(vi)];
    if (v1.net != net || v1.locked || v1.free || v1.type != model::ViaType::Through) continue;
    const Point p = v1.pos;
    const auto vat = ix.vias_at.find(key(p));
    if (vat == ix.vias_at.end() || vat->second.size() != 1) continue;  // a stacked via is not a jog end
    if (ix.arc_pts.count(key(p)) || pad_covers(w, p)) continue;
    const auto* ends = ends_at(p);
    if (!ends || ends->size() != 2) continue;  // exactly two track ends may touch the via
    // The two ends: one is the middle track (layer M), the other an outer track (layer L).
    for (const int flip : {0, 1}) {
      const auto& [mi, mend] = (*ends)[static_cast<std::size_t>(flip)];
      const auto& [oi, oend] = (*ends)[static_cast<std::size_t>(1 - flip)];
      (void)oend;
      const model::Track& mid = w.tracks[static_cast<std::size_t>(mi)];
      const model::Track& outer = w.tracks[static_cast<std::size_t>(oi)];
      if (mi < static_cast<int>(base_t) || mid.locked || mid.tuning_pattern || outer.locked || outer.tuning_pattern) continue;
      if (mid.net != net || outer.net != net || mid.layer == outer.layer) continue;
      const Point q = mend == 0 ? mid.b : mid.a;
      if (q == p || len(p, q) > static_cast<double>(opt.max_jog)) continue;
      if (refused.count(jog_key(p, q))) continue;
      const auto vat2 = ix.vias_at.find(key(q));
      if (vat2 == ix.vias_at.end() || vat2->second.size() != 1) continue;
      const int vj = vat2->second[0];
      if (vj < static_cast<int>(base_v) || vj == vi) continue;
      const model::Via& v2 = w.vias[static_cast<std::size_t>(vj)];
      if (v2.net != net || v2.locked || v2.free || v2.type != model::ViaType::Through) continue;
      const int layer = outer.layer;
      const int lo = std::min(layer, mid.layer), hi = std::max(layer, mid.layer);
      if (v1.layer_top > lo || v1.layer_bottom < hi || v2.layer_top > lo || v2.layer_bottom < hi) continue;
      if (ix.arc_pts.count(key(q)) || pad_covers(w, q)) continue;
      const auto* qends = ends_at(q);
      if (!qends || qends->size() != 2) continue;
      const auto& [qi, qend] = (*qends)[0].first == mi ? (*qends)[1] : (*qends)[0];
      if (qi == mi) continue;
      const model::Track& outer2 = w.tracks[static_cast<std::size_t>(qi)];
      (void)qend;
      if (outer2.locked || outer2.tuning_pattern || outer2.net != net || outer2.layer != layer) continue;
      if (outer2.width != outer.width) continue;
      if (ix.interior_through(p, {mi, oi}) || ix.interior_through(q, {mi, qi})) continue;
      out = Jog{vi, vj, mi, p, q, layer, outer.width, net};
      return true;
    }
  }
  return false;
}

}  // namespace

OptimizeResult optimize_copper(const model::Board& board, const model::DesignRules& rules, std::vector<model::Track>& tracks,
                               std::vector<model::Via>& vias, const OptimizeOptions& opt) {
  OptimizeResult res;
  model::Board w = board;
  const std::size_t base_t = w.tracks.size(), base_v = w.vias.size();
  w.tracks.insert(w.tracks.end(), tracks.begin(), tracks.end());
  w.vias.insert(w.vias.end(), vias.begin(), vias.end());

  res.merged = merge_sweeps(w, base_t);

  // Stage B, one net at a time. The obstacle model is rebuilt per net from the current board, so a net
  // never sees another net's stale state; within a net, what the pass removed or added is the net's own
  // copper, which never blocks its own probes — staleness can only lose a collapse, never invent one.
  std::set<model::NetId> nets;
  for (std::size_t i = base_v; i < w.vias.size(); ++i) nets.insert(w.vias[i].net);
  std::set<model::NetId> zoned;
  for (const auto& z : w.zones)
    if (z.net > 0) zoned.insert(z.net);
  for (const model::NetId net : nets) {
    if (res.out_of_work) break;
    if (net == 0 || zoned.count(net)) continue;  // a via of a zoned net may be a plane tie: not a jog
    route::Obstacles obs(w, rules);
    if (opt.soft_zones) obs.set_soft_zones(true);
    if (obs.coupling_net(net)) continue;  // pair geometry is not this pass's to move
    std::set<std::tuple<Coord, Coord, Coord, Coord>> refused;
    for (;;) {
      const Index ix = build_index(w);
      Jog jog;
      if (!find_jog(w, ix, base_t, base_v, net, opt, refused, jog)) break;
      ++res.jogs;
      if (res.checks + 1 > opt.work_limit) {
        res.out_of_work = true;
        break;
      }
      ++res.checks;
      if (obs.segment_state(jog.p, jog.q, jog.layer, jog.width, net, false) != 0) {
        ++res.no_room;
        refused.insert(jog_key(jog.p, jog.q));
        continue;
      }
      // Apply: the middle track and both vias go, one track on the outer layer joins p to q.
      model::Track t;
      t.a = jog.p;
      t.b = jog.q;
      t.width = jog.width;
      t.layer = jog.layer;
      t.net = net;
      w.tracks.push_back(t);
      std::vector<int> tv{jog.v1, jog.v2};
      std::sort(tv.begin(), tv.end(), std::greater<>());
      for (const int v : tv) w.vias.erase(w.vias.begin() + v);
      w.tracks.erase(w.tracks.begin() + jog.mid);
      ++res.collapsed;
    }
  }

  res.merged += merge_sweeps(w, base_t);  // a collapse leaves two collinear joins behind

  tracks.assign(w.tracks.begin() + static_cast<long>(base_t), w.tracks.end());
  vias.assign(w.vias.begin() + static_cast<long>(base_v), w.vias.end());
  return res;
}

}  // namespace tmk::passes
