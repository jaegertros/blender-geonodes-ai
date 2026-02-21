#!/usr/bin/env bash
# Blender Geometry Nodes Discovery - Linux/macOS Launcher
#
# Usage: ./scripts/run_discovery.sh [path_to_blender]
# Example: ./scripts/run_discovery.sh /Applications/Blender.app/Contents/MacOS/Blender
#
# If no path provided, tries 'blender' from PATH.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Use provided path or try to find Blender
if [ -n "$1" ]; then
    BLENDER="$1"
elif command -v blender &> /dev/null; then
    BLENDER="blender"
elif [ -x "/Applications/Blender.app/Contents/MacOS/Blender" ]; then
    BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
else
    echo "ERROR: Could not find Blender. Please provide the path as an argument."
    echo "Usage: $0 /path/to/blender"
    exit 1
fi

echo "Using Blender: $BLENDER"
echo

# Phase 1: Node Catalog Discovery
echo "================================================"
echo "Phase 1: Discovering geometry node types..."
echo "================================================"
"$BLENDER" --background --python "$PROJECT_DIR/discovery/discover_nodes.py"

echo

# Phase 2: Connection Compatibility Matrix
echo "================================================"
echo "Phase 2: Testing connection compatibility..."
echo "================================================"
"$BLENDER" --background --python "$PROJECT_DIR/discovery/test_connections.py"

echo
echo "================================================"
echo "All discovery phases complete!"
echo "Check discovery/ for output files."
echo "================================================"
