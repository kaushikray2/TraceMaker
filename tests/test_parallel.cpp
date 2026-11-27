// SPDX-License-Identifier: GPL-3.0-or-later
// parallel.hpp (Stage 2B #19 follow-up): a secondary claim is a reservation, not a
// read -- concurrent secondary stages share the cap headroom exactly, a claim is
// released when its scope ends, and with no cap set a claim is unbounded (-1).
#include <catch2/catch_test_macros.hpp>

#include <climits>

#include "core/parallel.hpp"

using tmk::parallel::PrimaryScope;
using tmk::parallel::SecondaryScope;

TEST_CASE("parallel: secondary claims share the cap headroom exactly", "[parallel]") {
  tmk::parallel::set_cap(8);
  PrimaryScope primaries(6);  // 6 primary workers live: 2 slots of headroom
  {
    SecondaryScope a(4);
    CHECK(a.count() == 2);  // asked for 4, only 2 are free
    SecondaryScope b(4);
    CHECK(b.count() == 0);  // headroom exhausted: the second caller gets none
  }  // both claims released here
  SecondaryScope c(4);
  CHECK(c.count() == 2);  // the headroom is back
  tmk::parallel::set_cap(0);
}

TEST_CASE("parallel: no cap means unbounded secondary claims", "[parallel]") {
  tmk::parallel::set_cap(0);
  SecondaryScope a(3);
  CHECK(a.count() == -1);
}

TEST_CASE("parallel: allowance read matches the unclaimed headroom", "[parallel]") {
  tmk::parallel::set_cap(4);
  PrimaryScope primaries(1);
  CHECK(tmk::parallel::secondary_allowance() == 3);
  tmk::parallel::set_cap(0);
  CHECK(tmk::parallel::secondary_allowance() == INT_MAX);
}
