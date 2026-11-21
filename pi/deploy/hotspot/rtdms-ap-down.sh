#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=1
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run]"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

CON_NAME="rtdms-ap"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "nmcli con down $CON_NAME"
    echo "nmcli radio wifi off"
    exit 0
fi

nmcli con down "$CON_NAME" || true
nmcli radio wifi off || true
