#!/usr/bin/env bash
# =============================================================================
# DeclarAI Test Runner
# =============================================================================
# Runs all test categories (unit, functional, regression, integration, UAT)
# and produces a grouped report. Returns non-zero exit code on any failure.
#
# Execution modes (auto-detected, overridable with --mode):
#   docker  - exec pytest inside the running backend container (default when
#             the container is up and we are on the host)
#   native  - run pytest directly in the current environment (CI, or a local
#             virtualenv with the backend requirements installed)
#
# Usage:
#   ./run_tests.sh                 # Run all tests (auto-detect mode)
#   ./run_tests.sh unit            # Run only unit tests
#   ./run_tests.sh functional      # Run only functional tests
#   ./run_tests.sh --quick         # Run unit + regression only (fast check)
#   ./run_tests.sh --mode native   # Force native pytest (no Docker)
#   ./run_tests.sh --mode docker   # Force Docker exec
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT_DIR="$SCRIPT_DIR/test-reports"
BACKEND_DIR="$SCRIPT_DIR/backend"
CONTAINER_NAME="${BACKEND_CONTAINER:-auto-ml-backend-1}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Counters
TOTAL_PASSED=0
TOTAL_FAILED=0
TOTAL_ERRORS=0
TOTAL_SKIPPED=0
CATEGORIES_RUN=0
FAILED_CATEGORIES=()

mkdir -p "$REPORT_DIR"

# ---------------------------------------------------------------------------
# Parse arguments: separate --mode from category args
# ---------------------------------------------------------------------------
MODE="auto"
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --mode)
            MODE="$2"; shift 2 ;;
        --mode=*)
            MODE="${1#*=}"; shift ;;
        *)
            ARGS+=("$1"); shift ;;
    esac
done
set -- "${ARGS[@]}"

# ---------------------------------------------------------------------------
# Resolve execution mode
# ---------------------------------------------------------------------------
container_running() {
    command -v docker >/dev/null 2>&1 && \
        docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"
}

if [ "$MODE" = "auto" ]; then
    if container_running; then
        MODE="docker"
    else
        MODE="native"
    fi
fi

if [ "$MODE" = "docker" ] && ! container_running; then
    echo -e "${RED}${BOLD}ERROR: Docker container '${CONTAINER_NAME}' is not running.${NC}"
    echo -e "${YELLOW}Start it with: docker-compose up -d${NC}"
    echo -e "${YELLOW}Or run without Docker: ./run_tests.sh --mode native${NC}"
    exit 1
fi

if [ "$MODE" = "native" ]; then
    PYTHON_BIN="${PYTHON:-python3}"
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        PYTHON_BIN="python"
    fi
    if ! "$PYTHON_BIN" -c "import pytest" >/dev/null 2>&1; then
        echo -e "${RED}${BOLD}ERROR: pytest is not importable with '${PYTHON_BIN}'.${NC}"
        echo -e "${YELLOW}Install backend requirements: pip install -r backend/requirements.txt${NC}"
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Helper: run pytest for a marker, in the resolved mode.
# Uses --junitxml for robust, locale-independent result parsing.
# ---------------------------------------------------------------------------
run_category() {
    local marker="$1"
    local label="$2"
    local icon="$3"

    CATEGORIES_RUN=$((CATEGORIES_RUN + 1))

    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${icon}  ${label} Tests${NC}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    local report_file="$REPORT_DIR/${marker}_results.txt"
    local junit_file="$REPORT_DIR/${marker}_junit.xml"
    local container_junit="/app/test-reports/${marker}_junit.xml"

    set +e
    if [ "$MODE" = "docker" ]; then
        docker exec "$CONTAINER_NAME" mkdir -p /app/test-reports >/dev/null 2>&1
        docker exec "$CONTAINER_NAME" python -m pytest -m "$marker" -v --tb=short \
            --no-header --rootdir=/app/backend -c /app/backend/pytest.ini \
            --junitxml="$container_junit" 2>&1 | tee "$report_file"
        local exit_code=${PIPESTATUS[0]}
        # Copy the JUnit report out of the container for parsing.
        docker cp "${CONTAINER_NAME}:${container_junit}" "$junit_file" >/dev/null 2>&1
    else
        ( cd "$BACKEND_DIR" && "${PYTHON_BIN}" -m pytest -m "$marker" -v --tb=short \
            --no-header --junitxml="$junit_file" ) 2>&1 | tee "$report_file"
        local exit_code=${PIPESTATUS[0]}
    fi
    set -e

    # Parse counts from the JUnit XML (authoritative, locale-independent).
    local counts passed failed errors skipped
    counts=$(parse_junit "$junit_file")
    passed=$(echo "$counts" | cut -d' ' -f1)
    failed=$(echo "$counts" | cut -d' ' -f2)
    errors=$(echo "$counts" | cut -d' ' -f3)
    skipped=$(echo "$counts" | cut -d' ' -f4)

    TOTAL_PASSED=$((TOTAL_PASSED + passed))
    TOTAL_FAILED=$((TOTAL_FAILED + failed))
    TOTAL_ERRORS=$((TOTAL_ERRORS + errors))
    TOTAL_SKIPPED=$((TOTAL_SKIPPED + skipped))

    if [ "$exit_code" -ne 0 ]; then
        echo -e "${RED}${BOLD}✗ ${label}: FAILED${NC} (${passed} passed, ${failed} failed, ${errors} errors, ${skipped} skipped)"
        FAILED_CATEGORIES+=("$label")
    else
        echo -e "${GREEN}${BOLD}✓ ${label}: PASSED${NC} (${passed} passed, ${skipped} skipped)"
    fi

    return $exit_code
}

# ---------------------------------------------------------------------------
# Parse a JUnit XML file -> "passed failed errors skipped".
# Uses Python (always available in both modes) for reliable XML parsing.
# ---------------------------------------------------------------------------
parse_junit() {
    local junit_file="$1"
    local py="${PYTHON_BIN:-python3}"
    command -v "$py" >/dev/null 2>&1 || py="python3"
    if [ ! -f "$junit_file" ]; then
        echo "0 0 0 0"
        return
    fi
    "$py" - "$junit_file" <<'PYEOF'
import sys, xml.etree.ElementTree as ET
try:
    root = ET.parse(sys.argv[1]).getroot()
except Exception:
    print("0 0 0 0"); sys.exit(0)
suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
tests = failures = errors = skipped = 0
for s in suites:
    tests += int(s.get("tests", 0))
    failures += int(s.get("failures", 0))
    errors += int(s.get("errors", 0))
    skipped += int(s.get("skipped", 0))
passed = tests - failures - errors - skipped
print(f"{max(passed,0)} {failures} {errors} {skipped}")
PYEOF
}

# ---------------------------------------------------------------------------
# Determine which categories to run
# ---------------------------------------------------------------------------
CATEGORIES=()
if [ $# -eq 0 ]; then
    CATEGORIES=("unit" "functional" "regression" "integration" "uat")
elif [ "$1" = "--quick" ]; then
    CATEGORIES=("unit" "regression")
else
    for arg in "$@"; do
        CATEGORIES+=("$arg")
    done
fi

LABELS=()
ICONS=()
for cat in "${CATEGORIES[@]}"; do
    case "$cat" in
        unit)        LABELS+=("Unit");        ICONS+=("🔬") ;;
        functional)  LABELS+=("Functional");  ICONS+=("⚙️") ;;
        regression)  LABELS+=("Regression");  ICONS+=("🛡️") ;;
        integration) LABELS+=("Integration"); ICONS+=("🔗") ;;
        uat)         LABELS+=("UAT");         ICONS+=("👤") ;;
        *)           echo "Unknown category: $cat"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║           DeclarAI Test Framework - Test Report             ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Mode:       ${BOLD}${MODE}${NC}"
echo -e "  Categories: ${BOLD}${CATEGORIES[*]}${NC}"
echo -e "  Backend:    ${BACKEND_DIR}"
echo -e "  Reports:    ${REPORT_DIR}"

OVERALL_EXIT=0
for i in "${!CATEGORIES[@]}"; do
    set +e
    run_category "${CATEGORIES[$i]}" "${LABELS[$i]}" "${ICONS[$i]}"
    if [ $? -ne 0 ]; then
        OVERALL_EXIT=1
    fi
    set -e
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${BLUE}║                      FINAL SUMMARY                          ║${NC}"
echo -e "${BOLD}${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Categories run:  ${BOLD}${CATEGORIES_RUN}${NC}"
echo -e "  Total passed:    ${GREEN}${BOLD}${TOTAL_PASSED}${NC}"
echo -e "  Total failed:    ${RED}${BOLD}${TOTAL_FAILED}${NC}"
echo -e "  Total errors:    ${RED}${BOLD}${TOTAL_ERRORS}${NC}"
echo -e "  Total skipped:   ${YELLOW}${BOLD}${TOTAL_SKIPPED}${NC}"
echo ""

if [ "$OVERALL_EXIT" -ne 0 ]; then
    echo -e "${RED}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}${BOLD}║  RESULT: FAILED                                             ║${NC}"
    echo -e "${RED}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${RED}  Failed categories: ${FAILED_CATEGORIES[*]}${NC}"
    echo -e "${RED}  Review the test output above and fix failing tests.${NC}"
    echo ""
    exit 1
else
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║  RESULT: ALL TESTS PASSED                                   ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    exit 0
fi
