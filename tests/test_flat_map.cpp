// SPDX-License-Identifier: GPL-3.0-or-later
// FlatU64U16 (Stage 2B flat hash maps): differential test against std::unordered_map over
// randomized insert / find / increment / decay-sweep traffic, including key 0 (a real
// lattice corner) and enough entries to force several growths. The decay sweep mirrors
// the history caller: halve every value in place, erase the zeros, re-examining a slot
// after an erase because backward shift moves an unvisited entry into it.
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
void decay(FlatU64U16& m) {
  for (std::size_t i = 0; i < m.slot_count();) {
    if (!m.slot_used(i)) {
      ++i;
      continue;
    }
    std::uint16_t& v = m.value_at(i);
    v = static_cast<std::uint16_t>(v / 2);
    if (v == 0) m.erase_at(i);
    else ++i;
  }
}
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
