"""
Pattern Verification Runner
=============================
Runs all pattern scripts (p01_*, p02_*, ...) each in a SEPARATE Blender
process to avoid crash-causing state contamination between patterns.

Usage (standalone, needs Python - not Blender):
    python patterns/verify_patterns.py [path_to_blender]

Or from within Blender (uses same Blender executable):
    blender --background --factory-startup --python patterns/verify_patterns.py

Output:
    patterns/pattern_catalog.json
"""

import subprocess
import sys
import os
import json
from datetime import datetime


# Hardcoded default; can be overridden by argv
DEFAULT_BLENDER = r"C:\Tools\Blender\stable\blender-4.5.6-lts.a78963ed6435\blender.exe"


def find_blender():
    """Find the Blender executable."""
    # Check if we're running inside Blender already
    try:
        import bpy
        return bpy.app.binary_path
    except ImportError:
        pass

    # Check command line arg
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[-1]):
        return sys.argv[-1]

    # Hardcoded default
    if os.path.isfile(DEFAULT_BLENDER):
        return DEFAULT_BLENDER

    print("ERROR: Could not find Blender. Pass path as argument.")
    sys.exit(1)


def find_pattern_scripts(patterns_dir):
    """Find all p##_*.py pattern files."""
    scripts = []
    for fname in sorted(os.listdir(patterns_dir)):
        if fname.startswith("p") and fname.endswith(".py") and "_" in fname:
            prefix = fname.split("_")[0]
            if prefix[0] == "p" and prefix[1:].isdigit():
                scripts.append(os.path.join(patterns_dir, fname))
    return scripts


def run_pattern_subprocess(blender_path, script_path):
    """Run a pattern script in a fresh Blender subprocess.

    Returns the parsed JSON result from the script's stdout.
    """
    cmd = [
        blender_path,
        "--background",
        "--factory-startup",
        "--python", script_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Parse JSON from stdout (pattern scripts print JSON + a status line)
        stdout = result.stdout.strip()
        if not stdout:
            return {
                "pattern_name": os.path.basename(script_path),
                "verified": False,
                "error": f"No output. stderr: {result.stderr[:500]}",
            }

        # Find the JSON block in the output (skip Blender header lines)
        json_start = stdout.find("{")
        json_end = stdout.rfind("}")
        if json_start >= 0 and json_end >= 0:
            json_str = stdout[json_start:json_end + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        return {
            "pattern_name": os.path.basename(script_path),
            "verified": False,
            "error": f"Could not parse JSON. Exit code: {result.returncode}. Output: {stdout[:300]}",
        }

    except subprocess.TimeoutExpired:
        return {
            "pattern_name": os.path.basename(script_path),
            "verified": False,
            "error": "Timeout (120s)",
        }
    except Exception as e:
        return {
            "pattern_name": os.path.basename(script_path),
            "verified": False,
            "error": str(e),
        }


def main():
    print("=" * 60)
    print("Pattern Verification Runner")
    print("=" * 60)

    blender_path = find_blender()
    print(f"Blender: {blender_path}")

    patterns_dir = os.path.dirname(os.path.abspath(__file__))
    scripts = find_pattern_scripts(patterns_dir)

    print(f"Found {len(scripts)} pattern scripts")
    print()

    # Get Blender version from a quick invocation
    try:
        ver_result = subprocess.run(
            [blender_path, "--version"],
            capture_output=True, text=True, timeout=10
        )
        blender_version = ver_result.stdout.strip().split("\n")[0]
    except Exception:
        blender_version = "unknown"

    catalog = {
        "blender_version": blender_version,
        "verification_date": datetime.now().isoformat(),
        "total_patterns": len(scripts),
        "verified_count": 0,
        "failed_count": 0,
        "patterns": [],
    }

    for script_path in scripts:
        script_name = os.path.basename(script_path)
        print(f"  Running {script_name}...", end=" ", flush=True)

        result = run_pattern_subprocess(blender_path, script_path)

        if result.get("verified"):
            catalog["verified_count"] += 1
            print("VERIFIED")
        else:
            catalog["failed_count"] += 1
            err = result.get("error", "")
            print(f"FAILED{' - ' + err[:80] if err else ''}")

        result["script_file"] = script_name
        catalog["patterns"].append(result)

    # Write catalog
    output_path = os.path.join(patterns_dir, "pattern_catalog.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False, default=str)

    print()
    print("=" * 60)
    print(f"Results: {catalog['verified_count']} verified, {catalog['failed_count']} failed")
    print(f"Output: {output_path}")
    print("=" * 60)

    if catalog["failed_count"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
