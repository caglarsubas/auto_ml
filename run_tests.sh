#!/usr/bin/env bash
# =============================================================================
# DeclarAI Test Runner
# =============================================================================
# Runs all test categories (unit, functional, regression, integration, UAT)
# inside the Docker backend container and produces a grouped report.
# Returns non-zero exit code on any failure.
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh unit         # Run only unit tests
#   ./run_tests.sh functional   # Run only functional tests
#   ./run_tests.sh --quick      # Run unit + regression only (fast check)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORT_DIR="$SCRIPT_DIR/test-reports"
CONTAINER_NAME="auto-ml-backend-1"

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
# Check Docker container is running
# ---------------------------------------------------------------------------
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}${BOLD}ERROR: Docker container '${CONTAINER_NAME}' is not running.${NC}"
    echo -e "${YELLOW}Start it with: docker-compose up -d${NC}"
    exit 1
fi

# ---------------------------------------------------------------------------
# Helper: run a single test category inside Docker
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

    # Run pytest inside Docker container
    set +e
    docker exec "$CONTAINER_NAME" python -m pytest -m "$marker" -v --tb=short --no-header --rootdir=/app/backend -c /app/backend/pytest.ini 2>&1 | tee "$report_file"
    local exit_code=${PIPESTATUS[0]}
    set -e

    # Parse results from the last summary line of pytest output
    local summary_line
    summary_line=$(grep -E '(passed|failed|error|skipped|no tests ran)' "$report_file" | tail -1)

    local passed=0 failed=0 errors=0 skipped=0

    # macOS-compatible parsing using sed
    if echo "$summary_line" | grep -q "passed"; then
        passed=$(echo "$summary_line" | sed -E 's/.*[^0-9]([0-9]+) passed.*/\1/')
    fi
    if echo "$summary_line" | grep -q "failed"; then
        failed=$(echo "$summary_line" | sed -E 's/.*[^0-9]([0-9]+) failed.*/\1/')
    fi
    if echo "$summary_line" | grep -q "error"; then
        errors=$(echo "$summary_line" | sed -E 's/.*[^0-9]([0-9]+) error.*/\1/')
    fi
    if echo "$summary_line" | grep -q "skipped"; then
        skipped=$(echo "$summary_line" | sed -E 's/.*[^0-9]([0-9]+) skipped.*/\1/')
    fi

    # Validate parsed values are numeric
    [[ "$passed" =~ ^[0-9]+$ ]] || passed=0
    [[ "$failed" =~ ^[0-9]+$ ]] || failed=0
    [[ "$errors" =~ ^[0-9]+$ ]] || errors=0
    [[ "$skipped" =~ ^[0-9]+$ ]] || skipped=0

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
