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

inline void set_cap(int n) { cap_slot().store(std::max(0, n)); }
inline int cap() { return cap_slot().load(); }
inline int primary_active() { return primary_slot().load(); }

// How many secondary worker threads a stage may add right now: unbounded when no cap is set,
// otherwise what the cap leaves after the live primary workers (never negative).
inline int secondary_allowance() {
  const int c = cap();
  if (c <= 0) return INT_MAX;
  return std::max(0, c - primary_active());
}

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
