find_package(Threads REQUIRED)
add_library(tm_core STATIC version.cpp live.cpp)
add_library(tm::core ALIAS tm_core)
target_include_directories(tm_core PUBLIC ${PROJECT_SOURCE_DIR}/src)
# Issue 40: bake the commit identity into the version string (0.12.1+<short sha>, with
# -dirty on an unclean tree) so a binary - and every route JSON it writes - names the
# exact code that ran. Captured at configure time. Tarball builds (no .git) and builds
# without git keep the plain release version.
set(TM_GIT_SUFFIX "")
find_package(Git QUIET)
if(GIT_FOUND AND EXISTS "${PROJECT_SOURCE_DIR}/.git")
  execute_process(COMMAND ${GIT_EXECUTABLE} rev-parse --short HEAD
                  WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
                  OUTPUT_VARIABLE TM_GIT_SHA OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
  execute_process(COMMAND ${GIT_EXECUTABLE} status --porcelain
                  WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
                  OUTPUT_VARIABLE TM_GIT_DIRTY OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
  if(TM_GIT_SHA)
    set(TM_GIT_SUFFIX "+${TM_GIT_SHA}")
    if(TM_GIT_DIRTY)
      set(TM_GIT_SUFFIX "+${TM_GIT_SHA}-dirty")
    endif()
  endif()
endif()
target_compile_definitions(tm_core PUBLIC TM_VERSION="${PROJECT_VERSION}${TM_GIT_SUFFIX}")
tm_set_warnings(tm_core)
target_link_libraries(tm_core PRIVATE Threads::Threads)
