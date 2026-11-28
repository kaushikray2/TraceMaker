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
// FlatU64U16 (Stage 2B flat hash maps): differential test against std::unordered_map over
// randomized insert / find / increment / decay traffic, including key 0 (a real
// lattice corner) and enough entries to force several growths. Decay is the map's own
// decay_half(), as the history caller uses it.
#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <random>
#include <unordered_map>

#include "core/flat_map.hpp"
#include <unordered_set>
#include <utility>

struct PairHashRef {
  std::size_t operator()(const std::pair<std::int64_t, std::int64_t>& p) const noexcept {
    return std::hash<std::int64_t>{}(p.first * 1000003) ^ std::hash<std::int64_t>{}(p.second);
  }
};
using tmk::core::FlatPairSet;
using tmk::core::FlatU64U16;

namespace {
void decay(FlatU64U16& m) { m.decay_half(); }
void require_same(const FlatU64U16& m, const std::unordered_map<std::uint64_t, std::uint16_t>& ref) {
  REQUIRE(m.size() == ref.size());
  for (const auto& [k, v] : ref) {
    const std::uint16_t* got = m.find(k);
    REQUIRE(got != nullptr);
    REQUIRE(*got == v);
  }
}
}  // namespace

TEST_CASE("flat map: randomized differential traffic", "[flat_map]") {
  FlatU64U16 m;
  std::unordered_map<std::uint64_t, std::uint16_t> ref;
  std::mt19937_64 rng(20261124);
  REQUIRE(m.empty());
  REQUIRE(m.find(0) == nullptr);
  for (int step = 0; step < 300000; ++step) {
    // Structured keys like cell_key(layer, gx, gy), plus key 0 and small keys.
    std::uint64_t key;
    switch (rng() % 4) {
      case 0: key = 0; break;
      case 1: key = rng() % 977; break;
      default: key = (rng() % 8) << 48 | (rng() % 4000) << 24 | (rng() % 4000); break;
    }
    if (step % 50000 == 49999) {
      decay(m);
      for (auto it = ref.begin(); it != ref.end();) {
        it->second = static_cast<std::uint16_t>(it->second / 2);
        it = it->second == 0 ? ref.erase(it) : std::next(it);
      }
      require_same(m, ref);
      continue;
    }
    std::uint16_t& a = m[key];
    std::uint16_t& b = ref[key];
    if (a < 60000) a = static_cast<std::uint16_t>(a + 1);
    if (b < 60000) b = static_cast<std::uint16_t>(b + 1);
    if (step % 997 == 0) {
      const std::uint16_t* got = m.find(key);
      REQUIRE(got != nullptr);
      REQUIRE(*got == ref[key]);
      REQUIRE(m.find(key + (std::uint64_t{1} << 40)) == nullptr);
    }
  }
  require_same(m, ref);
  m.clear();
  REQUIRE(m.empty());
  REQUIRE(m.size() == 0);
  REQUIRE(m.find(0) == nullptr);
}

TEST_CASE("flat map: decay is exact-once across the slot ring wrap", "[flat_map]") {
  // Regression: keys 3052 (value 1) and 3703 (value 2) share home slot 1023 of the
  // initial 1024-slot table, so 3703 spills to slot 0. A sweep from slot 0 that erases
  // 3052 at slot 1023 pulls the already-decayed 3703 into slot 1023 and decays it a
  // second time (2 -> 1 -> 0, silently erased). decay_half() anchors the sweep just
  // after an empty slot, so this cannot happen.
  FlatU64U16 m;
  m[3052] = 1;
  m[3703] = 2;
  REQUIRE(m.slot_count() == 1024);
  m.decay_half();
  CHECK(m.find(3052) == nullptr);  // 1 -> 0: erased
  const std::uint16_t* b = m.find(3703);
  REQUIRE(b != nullptr);           // 2 -> 1: kept, halved exactly once
  CHECK(*b == 1);
  CHECK(m.size() == 1);
}

TEST_CASE("flat map: repeated decays match the reference on many seeds", "[flat_map]") {
  // Small values (1..4) so decays erase constantly and clusters churn across the wrap;
  // the single-seed traffic test above never produced a wrap-straddling cluster with a
  // zero-halving entry at the last slot, which is the shape that broke the old sweep.
  for (const std::uint64_t seed : {1ULL, 7ULL, 42ULL, 12345ULL, 999983ULL}) {
    FlatU64U16 m;
    std::unordered_map<std::uint64_t, std::uint16_t> ref;
    std::mt19937_64 rng(seed);
    for (int i = 0; i < 3000; ++i) {
      const std::uint64_t key = (rng() % 8) << 48 | (rng() % 4000) << 24 | (rng() % 4000);
      const std::uint16_t v = static_cast<std::uint16_t>(1 + rng() % 4);
      m[key] = v;
      ref[key] = v;
    }
    for (int round = 0; round < 4; ++round) {
      m.decay_half();
      for (auto it = ref.begin(); it != ref.end();) {
        it->second = static_cast<std::uint16_t>(it->second / 2);
        it = it->second == 0 ? ref.erase(it) : std::next(it);
      }
      require_same(m, ref);
    }
  }
}

TEST_CASE("flat pair set: randomized differential membership", "[flat_map]") {
  FlatPairSet s;
  std::unordered_set<std::pair<std::int64_t, std::int64_t>, PairHashRef> ref;
  std::mt19937_64 rng(20261125);
  REQUIRE(s.empty());
  REQUIRE(!s.contains(0, 0));
  for (int step = 0; step < 200000; ++step) {
    const std::int64_t a = static_cast<std::int64_t>(rng() % 64) * 10'000'000 + static_cast<std::int64_t>(rng() % 300);
    const std::int64_t b = static_cast<std::int64_t>((rng() % 8) << 48 | (rng() % 4000) << 24 | (rng() % 4000));
    s.insert(a, b);
    ref.insert({a, b});
    REQUIRE(s.contains(a, b));
    REQUIRE(s.size() == ref.size());
    if (step % 991 == 0) {
      const std::int64_t x = static_cast<std::int64_t>(rng() % 64) * 10'000'000 + 9999;
      REQUIRE(s.contains(x, b) == (ref.count({x, b}) != 0));
    }
  }
  for (const auto& pr : ref) REQUIRE(s.contains(pr.first, pr.second));
}
