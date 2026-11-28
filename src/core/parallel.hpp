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
// The process-wide worker budget behind --threads as a hard global cap (Stage 2B #19).
//
// The app sets the cap once per process (a route job sets it from its thread count); 0 means no
// cap was set and every stage keeps its historical behaviour. The portfolio's variant workers
// are the primary workers: route_portfolio registers how many are alive, and secondary stages
// (zone refill's per-layer tasks) may only add threads with what the cap leaves free, so the
// process never runs more concurrent workers than the cap. The main thread and the live-log
// writer are not workers; the documented OS-level thread peak is cap + 2.
#include <algorithm>
#include <atomic>
#include <climits>

namespace tmk::parallel {

inline std::atomic<int>& cap_slot() {
  static std::atomic<int> v{0};
  return v;
}
inline std::atomic<int>& primary_slot() {
  static std::atomic<int> v{0};
  return v;
}
inline std::atomic<int>& secondary_slot() {
  static std::atomic<int> v{0};
  return v;
}

inline void set_cap(int n) { cap_slot().store(std::max(0, n)); }

// RAII save/restore of the cap for one job's scope: the previous value (0 = no cap)
// is restored on exit, so a process that runs more than one job -- the test binary,
// batch mode, nested wrapper jobs -- never leaks one job's cap into the next.
struct CapScope {
  explicit CapScope(int n) : prev_(cap_slot().load()) { set_cap(n); }
  ~CapScope() { set_cap(prev_); }
  CapScope(const CapScope&) = delete;
  CapScope& operator=(const CapScope&) = delete;

 private:
  int prev_;
};
inline int cap() { return cap_slot().load(); }
inline int primary_active() { return primary_slot().load(); }

// How many secondary worker threads a stage may add right now: unbounded when no cap is set,
// otherwise what the cap leaves after the live primary workers (never negative).
inline int secondary_allowance() {
  const int c = cap();
  if (c <= 0) return INT_MAX;
  return std::max(0, c - primary_active());
}

// RAII claim of secondary worker slots under the cap. secondary_allowance() alone is a
// read, not a reservation: concurrent secondary stages (zone refill runs inside every
// portfolio variant's setup when the board has unfilled zones) would each spend the
// same headroom and oversubscribe the cap. A claim atomically takes as many of `want`
// as the cap leaves free after the live primary workers and other live claims, and
// releases them on scope exit. With no cap set, count() is -1: unbounded, the
// historical behaviour.
struct SecondaryScope {
  explicit SecondaryScope(int want) : n_(0) {
    if (cap() <= 0) {
      n_ = -1;
      return;
    }
    int cur = secondary_slot().load();
    for (;;) {
      const int avail = cap() - primary_active() - cur;
      const int claim = std::min(want, std::max(0, avail));
      if (claim <= 0) return;
      if (secondary_slot().compare_exchange_weak(cur, cur + claim)) {
        n_ = claim;
        return;
      }
    }
  }
  ~SecondaryScope() {
    if (n_ > 0) secondary_slot().fetch_sub(n_);
  }
  SecondaryScope(const SecondaryScope&) = delete;
  SecondaryScope& operator=(const SecondaryScope&) = delete;
  int count() const { return n_; }

 private:
  int n_;
};

// RAII registration of a primary pool's workers, for the scope of a parallel run.
struct PrimaryScope {
  explicit PrimaryScope(int n) : n_(n > 0 ? n : 0) {
    if (n_ > 0) primary_slot().fetch_add(n_);
  }
  ~PrimaryScope() {
    if (n_ > 0) primary_slot().fetch_sub(n_);
  }
  PrimaryScope(const PrimaryScope&) = delete;
  PrimaryScope& operator=(const PrimaryScope&) = delete;

 private:
  int n_;
};

}  // namespace tmk::parallel
