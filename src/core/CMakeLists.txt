# Modifications Copyright (C) 2026 SiliconBrane Inc.
# Modified 2026 as part of the SiliconBrane fork of TraceMaker:
# the version string carries the commit it was built from, computed at build time via cmake/GitVersion.cmake.
# The modifications are licensed under GPL-3.0-or-later, the same
# terms as the original work.

find_package(Threads REQUIRED)
add_library(tm_core STATIC version.cpp live.cpp)
add_library(tm::core ALIAS tm_core)
target_include_directories(tm_core PUBLIC ${PROJECT_SOURCE_DIR}/src)
# Issues 40/56: the version string carries the commit identity (0.12.1+<short sha>, with
# -dirty on an unclean tree) so a binary - and every route JSON it writes - names the
# exact code that ran. The stamp is recomputed at BUILD time into a generated header
# (cmake/GitVersion.cmake): a configure-time capture went stale on any commit that
# touched no CMakeLists.txt. Tarball builds (no .git) and builds without git keep the
# plain release version. The header is rewritten only when the stamp changes.
set(TM_VERSION_HEADER ${PROJECT_BINARY_DIR}/generated/tm_version.hpp)
execute_process(COMMAND ${CMAKE_COMMAND} -DTM_SOURCE_DIR=${PROJECT_SOURCE_DIR}
                        -DTM_FALLBACK_VERSION=${PROJECT_VERSION} -DTM_OUTPUT=${TM_VERSION_HEADER}
                        -P ${PROJECT_SOURCE_DIR}/cmake/GitVersion.cmake)
add_custom_target(tm_version_header ALL
  COMMAND ${CMAKE_COMMAND} -DTM_SOURCE_DIR=${PROJECT_SOURCE_DIR}
          -DTM_FALLBACK_VERSION=${PROJECT_VERSION} -DTM_OUTPUT=${TM_VERSION_HEADER}
          -P ${PROJECT_SOURCE_DIR}/cmake/GitVersion.cmake
  BYPRODUCTS ${TM_VERSION_HEADER}
  COMMENT "Version stamp"
  VERBATIM)
add_dependencies(tm_core tm_version_header)
target_include_directories(tm_core PUBLIC ${PROJECT_BINARY_DIR}/generated)
tm_set_warnings(tm_core)
target_link_libraries(tm_core PRIVATE Threads::Threads)
