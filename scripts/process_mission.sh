#!/bin/bash

# Unified mission processing pipeline: import, calculate spending, and generate json
# Shell script version that calls existing Python scripts

set -e  # Exit on any error

# Default values
MISSION=""
MISSIONS_DIR_ARG=""
SKIP_IMPORT=false
SKIP_SPENDING=false
FORCE_OVERWRITE=false
VERBOSE=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Emojis
INFO_EMOJI="ℹ️ "
SUCCESS_EMOJI="✅"
ERROR_EMOJI="❌"
WARNING_EMOJI="⚠️ "
SKIP_EMOJI="⏭️ "

# Logging function
log() {
    local level=$1
    local message=$2

    case $level in
        INFO)
            if [ "$VERBOSE" = true ]; then
                echo -e "${INFO_EMOJI} $message"
            fi
            ;;
        SUCCESS)
            echo -e "${SUCCESS_EMOJI} $message"
            ;;
        ERROR)
            echo -e "${ERROR_EMOJI} $message" >&2
            ;;
        WARNING)
            echo -e "${WARNING_EMOJI} $message"
            ;;
    esac
}

# Function to show usage
usage() {
    cat << EOF
Usage: $0 (--mission MISSION_NAME | --missions-dir DIR) [OPTIONS]

Unified mission processing pipeline: import, calculate spending, and generate json

Required arguments:
  --mission MISSION_NAME    Name of the mission to process (matches 'Short Title' in source data)
  --missions-dir DIR        Directory of mission YAML files to update/process

Optional arguments:
  --skip-import            Skip import step and use existing YAML data
  --skip-spending          Skip obligations and outlays calculations
  --force-overwrite        Force overwrite existing YAML during import (loses manual edits)
  --verbose               Enable verbose output
  -h, --help              Show this help message and exit

Examples:
  $0 --mission "IMAP"
  $0 --mission "Chandra" --skip-import
  $0 --mission "Europa Clipper" --force-overwrite --verbose
  $0 --missions-dir data/missions
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mission)
            MISSION="$2"
            shift 2
            ;;
        --missions-dir|--import-dir)
            MISSIONS_DIR_ARG="$2"
            shift 2
            ;;
        --skip-import)
            SKIP_IMPORT=true
            shift
            ;;
        --skip-spending)
            SKIP_SPENDING=true
            shift
            ;;
        --force-overwrite)
            FORCE_OVERWRITE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -n "$MISSION" ] && [ -n "$MISSIONS_DIR_ARG" ]; then
    echo "Error: use either --mission or --missions-dir, not both" >&2
    usage >&2
    exit 1
fi

if [ -z "$MISSION" ] && [ -z "$MISSIONS_DIR_ARG" ]; then
    echo "Error: --mission or --missions-dir is required" >&2
    usage >&2
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
MISSIONS_DIR="$DATA_DIR/missions"
SPENDING_DIR="$DATA_DIR/spending"

# Results tracking
IMPORT_RESULT=""
OBLIGATIONS_RESULT=""
OUTLAYS_RESULT=""
JSON_RESULT=""

# Function to find mission YAML file
find_mission_yaml() {
    local mission_name="$1"
    local yaml_file=""

    # Try to find the YAML file by checking canonical_short_name in each file
    for yaml_path in "$MISSIONS_DIR"/*.yaml; do
        if [ -f "$yaml_path" ]; then
            # Use grep to check if this YAML contains the mission
            if grep -q "canonical_short_name: *['\"]${mission_name}['\"]" "$yaml_path" 2>/dev/null || \
               grep -q "canonical_short_name: *${mission_name}" "$yaml_path" 2>/dev/null; then
                yaml_file="$yaml_path"
                break
            fi
        fi
    done

    echo "$yaml_file"
}

echo ""
echo "============================================================"
if [ -n "$MISSIONS_DIR_ARG" ]; then
    echo "Processing Missions in: $MISSIONS_DIR_ARG"
else
    echo "Processing Mission: $MISSION"
fi
echo "============================================================"
echo ""

# Step 1: Import/Load mission
if [ "$SKIP_IMPORT" = false ]; then
    if [ -n "$MISSIONS_DIR_ARG" ]; then
        log "INFO" "Importing missions in directory: $MISSIONS_DIR_ARG"
    else
        log "INFO" "Importing mission: $MISSION"
    fi

    if [ "$FORCE_OVERWRITE" = true ]; then
        log "INFO" "Force overwrite mode - replacing entire YAML file..."
    fi

    if [ -n "$MISSIONS_DIR_ARG" ]; then
        IMPORT_CMD=(python "$SCRIPT_DIR/ingest_data.py" --import-dir "$MISSIONS_DIR_ARG")
    else
        IMPORT_CMD=(python "$SCRIPT_DIR/ingest_data.py" --import "$MISSION")
    fi
    if [ "$FORCE_OVERWRITE" = true ]; then
        IMPORT_CMD+=(--force-overwrite)
    fi

    if "${IMPORT_CMD[@]}"; then
        IMPORT_RESULT="created/updated"
        if [ -n "$MISSIONS_DIR_ARG" ]; then
            log "SUCCESS" "Successfully imported missions in directory"
        else
            log "SUCCESS" "Successfully imported mission: $MISSION"
        fi
    else
        if [ -n "$MISSIONS_DIR_ARG" ]; then
            log "ERROR" "Failed to import missions in directory"
        else
            log "ERROR" "Failed to import mission: $MISSION"
        fi
        IMPORT_RESULT="failed"

        # Try to find existing mission for subsequent steps
        if [ -z "$MISSIONS_DIR_ARG" ]; then
            log "WARNING" "Import failed, attempting to find existing mission..."
            MISSION_YAML=$(find_mission_yaml "$MISSION")
            if [ -n "$MISSION_YAML" ]; then
                log "SUCCESS" "Found existing mission at $MISSION_YAML"
            else
                log "ERROR" "Cannot proceed without mission data"
                exit 1
            fi
        fi
    fi
else
    if [ -n "$MISSIONS_DIR_ARG" ]; then
        log "INFO" "Skipping import, using existing mission YAML files..."
    else
        log "INFO" "Skipping import, loading existing mission..."
    fi
    IMPORT_RESULT="skipped"

    if [ -z "$MISSIONS_DIR_ARG" ]; then
        MISSION_YAML=$(find_mission_yaml "$MISSION")
        if [ -n "$MISSION_YAML" ]; then
            log "SUCCESS" "Found existing mission at $MISSION_YAML"
        else
            log "ERROR" "Mission '$MISSION' not found in $MISSIONS_DIR"
            exit 1
        fi
    fi
fi

if [ -n "$MISSIONS_DIR_ARG" ]; then
    if [ ! -d "$MISSIONS_DIR_ARG" ]; then
        log "ERROR" "Mission directory not found: $MISSIONS_DIR_ARG"
        exit 1
    fi
    MISSIONS_DIR="$MISSIONS_DIR_ARG"
else
    # Find the mission YAML file if not already found
    if [ -z "$MISSION_YAML" ]; then
        MISSION_YAML=$(find_mission_yaml "$MISSION")
        if [ -z "$MISSION_YAML" ]; then
            log "ERROR" "Cannot find YAML file for mission: $MISSION"
            exit 1
        fi
    fi
fi

OBLIGATIONS_FAILED=0
OUTLAYS_FAILED=0
JSON_FAILED=0
PROCESSED_COUNT=0

process_yaml_file() {
    local yaml_path="$1"
    local mission_label
    mission_label="$(basename "${yaml_path%.yaml}")"

    # Step 2 & 3: Calculate spending (if not skipped)
    if [ "$SKIP_SPENDING" = false ]; then
        # Calculate obligations
        log "INFO" "Calculating obligations for $mission_label..."
        if python "$SCRIPT_DIR/calculate_obligations.py" "$yaml_path"; then
            # Count the records in the obligations file
            OBLIGATIONS_FILE="$SPENDING_DIR/$(basename "${yaml_path%.yaml}")_obligations.csv"
            if [ -f "$OBLIGATIONS_FILE" ]; then
                RECORD_COUNT=$(tail -n +2 "$OBLIGATIONS_FILE" | wc -l | tr -d ' ')
                log "SUCCESS" "Found $RECORD_COUNT funding records"
            else
                log "WARNING" "No obligations data found"
            fi
        else
            OBLIGATIONS_FAILED=$((OBLIGATIONS_FAILED + 1))
            log "ERROR" "Failed to calculate obligations"
        fi

        # Calculate outlays
        log "INFO" "Calculating outlays for $mission_label..."
        if python "$SCRIPT_DIR/calculate_outlays.py" "$yaml_path"; then
            # Count the records in the outlays file
            OUTLAYS_FILE="$SPENDING_DIR/$(basename "${yaml_path%.yaml}")_outlays.csv"
            if [ -f "$OUTLAYS_FILE" ]; then
                RECORD_COUNT=$(tail -n +2 "$OUTLAYS_FILE" | wc -l | tr -d ' ')
                log "SUCCESS" "Found $RECORD_COUNT cumulative outlay records"
            else
                log "WARNING" "No outlays data found"
            fi
        else
            OUTLAYS_FAILED=$((OUTLAYS_FAILED + 1))
            log "ERROR" "Failed to calculate outlays"
        fi
    else
        log "INFO" "Skipping spending calculations for $mission_label"
    fi

    # Step 4: Generate JSON (always runs)
    log "INFO" "Generating JSON for $mission_label..."
    if python "$SCRIPT_DIR/generate_static.py" "$yaml_path" --spending-dir "$SPENDING_DIR"; then
        log "SUCCESS" "Generated JSON files"
    else
        JSON_FAILED=$((JSON_FAILED + 1))
        log "ERROR" "Failed to generate JSON"
    fi
}

if [ -n "$MISSIONS_DIR_ARG" ]; then
    YAML_FILES=("$MISSIONS_DIR"/*.yaml "$MISSIONS_DIR"/*.yml)
    VALID_YAMLS=()
    for yaml_path in "${YAML_FILES[@]}"; do
        if [ -f "$yaml_path" ]; then
            VALID_YAMLS+=("$yaml_path")
        fi
    done

    if [ ${#VALID_YAMLS[@]} -eq 0 ]; then
        log "ERROR" "No mission YAML files found in $MISSIONS_DIR"
        exit 1
    fi

    for yaml_path in "${VALID_YAMLS[@]}"; do
        PROCESSED_COUNT=$((PROCESSED_COUNT + 1))
        process_yaml_file "$yaml_path"
    done
else
    PROCESSED_COUNT=1
    process_yaml_file "$MISSION_YAML"
fi

# Print summary
echo ""
echo "============================================================"
echo "Processing Summary:"
echo "============================================================"

# Function to get status icon
get_status_icon() {
    local result="$1"
    case "$result" in
        *failed*)
            echo "$ERROR_EMOJI"
            ;;
        *skipped*)
            echo "$SKIP_EMOJI"
            ;;
        *)
            echo "$SUCCESS_EMOJI"
            ;;
    esac
}

if [ -n "$MISSIONS_DIR_ARG" ]; then
    OBLIGATIONS_RESULT=$([ "$SKIP_SPENDING" = true ] && echo "skipped" || echo "${OBLIGATIONS_FAILED} failed")
    OUTLAYS_RESULT=$([ "$SKIP_SPENDING" = true ] && echo "skipped" || echo "${OUTLAYS_FAILED} failed")
    JSON_RESULT="${JSON_FAILED} failed"
else
    OBLIGATIONS_RESULT=${OBLIGATIONS_RESULT:-not run}
    OUTLAYS_RESULT=${OUTLAYS_RESULT:-not run}
    JSON_RESULT=${JSON_RESULT:-not run}
fi

printf "  %-15s %s %s\n" "Import" "$(get_status_icon "$IMPORT_RESULT")" "${IMPORT_RESULT:-not run}"
printf "  %-15s %s %s\n" "Obligations" "$(get_status_icon "$OBLIGATIONS_RESULT")" "${OBLIGATIONS_RESULT}"
printf "  %-15s %s %s\n" "Outlays" "$(get_status_icon "$OUTLAYS_RESULT")" "${OUTLAYS_RESULT}"
printf "  %-15s %s %s\n" "JSON File" "$(get_status_icon "$JSON_RESULT")" "${JSON_RESULT}"
printf "  %-15s %s\n" "Missions" "${PROCESSED_COUNT}"

echo "============================================================"
echo ""

# Exit with error if any step failed
if [[ "$IMPORT_RESULT" == *failed* ]] || [[ "$OBLIGATIONS_RESULT" == *failed* ]] || [[ "$OUTLAYS_RESULT" == *failed* ]] || [[ "$JSON_RESULT" == *failed* ]]; then
    exit 1
fi
