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
#pragma once
// Flat open-addressing containers (Stage 2B: flat hash maps): a uint64 -> uint16 map and
// an int64-pair set, both linear-probing with backward-shift-free growth rehashing.
//
// Linear probing over a power-of-two slot array with a splitmix64 finalizer for the probe
// start, backward-shift deletion (no tombstones), growth at 70 % load. Built for the route
// history map: ~1e8 finds per large job against std::unordered_map cost several seconds of
// pointer chasing; a find here is one or two cache lines. Key 0 is a valid key (occupancy
// is a separate flag, not a sentinel). Iteration is over raw slots for the one caller that
// transforms values in place (the history decay sweep); slot order is unspecified and no
// caller may depend on it.
#include <cstddef>
#include <cstdint>
#include <vector>

namespace tmk::core {

class FlatU64U16 {
 public:
  bool empty() const { return n_ == 0; }
  std::size_t size() const { return n_; }

  const std::uint16_t* find(std::uint64_t key) const {
    if (slots_.empty()) return nullptr;
    std::size_t i = probe(key);
    return slots_[i].used ? &slots_[i].value : nullptr;
  }
  std::uint16_t& operator[](std::uint64_t key) {
    if (slots_.empty() || (n_ + 1) * 10 > slots_.size() * 7) grow();
    std::size_t i = probe(key);
    if (!slots_[i].used) {
      slots_[i].used = true;
      slots_[i].key = key;
      slots_[i].value = 0;
      ++n_;
    }
    return slots_[i].value;
  }

  // Slot access for read-only sweeps (the heatmap build). Do NOT erase in place during a
  // hand-rolled sweep: backward shift moves an entry from a higher slot into the erased
  // one, and across the ring wrap (last slot -> slot 0) that entry has already been
  // visited, so it would be processed twice. Use decay_half() for in-place decay.
  std::size_t slot_count() const { return slots_.size(); }
  bool slot_used(std::size_t i) const { return slots_[i].used; }
  std::uint16_t& value_at(std::size_t i) { return slots_[i].value; }
  std::uint64_t key_at(std::size_t i) const { return slots_[i].key; }
  void erase_at(std::size_t i) {
    const std::size_t mask = slots_.size() - 1;
    std::size_t hole = i;
    slots_[hole].used = false;
    --n_;
    std::size_t j = hole;
    for (;;) {
      j = (j + 1) & mask;
      if (!slots_[j].used) return;
      const std::size_t home = mix(slots_[j].key) & mask;
      // Move slot j into the hole when its home is not in the cyclic interval (hole, j].
      const bool home_after_hole = hole < j ? (home > hole && home <= j) : (home > hole || home <= j);
      if (!home_after_hole) {
        slots_[hole] = slots_[j];
        slots_[j].used = false;
        hole = j;
      }
    }
  }
  void clear() {
    for (auto& s : slots_) s.used = false;
    n_ = 0;
  }

  // Halve every value in place, erasing entries whose value reaches 0 -- the history
  // decay. Exact-once: the sweep starts just after an empty slot (one always exists at
  // the <= 70 % load the growth rule keeps) and walks the ring from there. Backward-shift
  // deletion never moves an entry across an empty slot, so every entry an erase shifts
  // into the sweep's path comes from its own cluster, ahead of the sweep -- never from
  // behind it, which is exactly what goes wrong across the wrap in a sweep from slot 0.
  void decay_half() {
    if (slots_.empty()) return;
    const std::size_t n = slots_.size();
    std::size_t s0 = 0;
    while (s0 < n && slots_[s0].used) ++s0;  // the empty slot anchoring the sweep
    if (s0 == n) return;                     // a full table cannot occur under the growth rule
    for (std::size_t k = 1; k < n; ++k) {
      std::size_t idx = s0 + k;
      if (idx >= n) idx -= n;
      if (!slots_[idx].used) continue;
      const std::uint16_t hv = static_cast<std::uint16_t>(slots_[idx].value / 2);
      if (hv == 0) {
        erase_at(idx);
        --k;  // re-examine idx: the entry shifted into it is unvisited
      } else {
        slots_[idx].value = hv;
      }
    }
  }

 private:
  struct Slot {
    std::uint64_t key = 0;
    std::uint16_t value = 0;
    bool used = false;
  };
  static std::uint64_t mix(std::uint64_t k) {
    k ^= k >> 30;
    k *= 0xbf58476d1ce4e5b9ULL;
    k ^= k >> 27;
    k *= 0x94d049bb133111ebULL;
    k ^= k >> 31;
    return k;
  }
  std::size_t probe(std::uint64_t key) const {
    const std::size_t mask = slots_.size() - 1;
    std::size_t i = mix(key) & mask;
    while (slots_[i].used && slots_[i].key != key) i = (i + 1) & mask;
    return i;
  }
  void grow() {
    std::vector<Slot> old = std::move(slots_);
    slots_.assign(old.empty() ? 1024 : old.size() * 2, Slot{});
    const std::size_t mask = slots_.size() - 1;
    for (const auto& s : old) {
      if (!s.used) continue;
      std::size_t i = mix(s.key) & mask;
      while (slots_[i].used) i = (i + 1) & mask;
      slots_[i] = s;
    }
  }
  std::vector<Slot> slots_;
  std::size_t n_ = 0;
};

// Flat open-addressing set of int64 pairs (the learned_block shape): same probing core as
// FlatU64U16, membership and insert only (that caller never erases or iterates). The probe
// start mixes both halves, matching the splitmix pair hash the unordered_set used.
class FlatPairSet {
 public:
  bool empty() const { return n_ == 0; }
  std::size_t size() const { return n_; }
  bool contains(std::int64_t a, std::int64_t b) const {
    if (slots_.empty()) return false;
    const std::size_t mask = slots_.size() - 1;
    std::size_t i = mix(static_cast<std::uint64_t>(a) ^ mix(static_cast<std::uint64_t>(b))) & mask;
    while (slots_[i].used && (slots_[i].a != a || slots_[i].b != b)) i = (i + 1) & mask;
    return slots_[i].used;
  }
  void insert(std::int64_t a, std::int64_t b) {
    if (slots_.empty() || (n_ + 1) * 10 > slots_.size() * 7) grow();
    const std::size_t mask = slots_.size() - 1;
    std::size_t i = mix(static_cast<std::uint64_t>(a) ^ mix(static_cast<std::uint64_t>(b))) & mask;
    while (slots_[i].used && (slots_[i].a != a || slots_[i].b != b)) i = (i + 1) & mask;
    if (!slots_[i].used) {
      slots_[i].used = true;
      slots_[i].a = a;
      slots_[i].b = b;
      ++n_;
    }
  }

 private:
  struct Slot {
    std::int64_t a = 0;
    std::int64_t b = 0;
    bool used = false;
  };
  static std::uint64_t mix(std::uint64_t k) {
    k ^= k >> 30;
    k *= 0xbf58476d1ce4e5b9ULL;
    k ^= k >> 27;
    k *= 0x94d049bb133111ebULL;
    k ^= k >> 31;
    return k;
  }
  void grow() {
    std::vector<Slot> old = std::move(slots_);
    slots_.assign(old.empty() ? 1024 : old.size() * 2, Slot{});
    const std::size_t mask = slots_.size() - 1;
    for (const auto& s : old) {
      if (!s.used) continue;
      std::size_t i = mix(static_cast<std::uint64_t>(s.a) ^ mix(static_cast<std::uint64_t>(s.b))) & mask;
      while (slots_[i].used) i = (i + 1) & mask;
      slots_[i] = s;
    }
  }
  std::vector<Slot> slots_;
  std::size_t n_ = 0;
};

}  // namespace tmk::core
