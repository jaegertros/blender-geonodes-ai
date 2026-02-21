"""
Pattern 01: Subdivide + Shade Smooth
=====================================
The simplest useful geometry node tree.
Takes input geometry, subdivides it, applies smooth shading.

Input: Any mesh
Output: Subdivided, smooth-shaded mesh

Nodes used:
  - Subdivide Mesh (GeometryNodeSubdivideMesh)
  - Set Shade Smooth (GeometryNodeSetShadeSmooth)
"""

import bpy
import sys
import os
import json

# Add parent dir to path so we can import pattern_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pattern_utils import (
    create_node_tree, add_node, link, apply_as_modifier,
    create_test_mesh, evaluate_and_check, export_tree_structure, cleanup
)

PATTERN_NAME = "subdivide_smooth"
PATTERN_DESCRIPTION = "Subdivides mesh geometry and applies smooth shading"


def build_tree():
    tree, gin, gout = create_node_tree("SubdivideSmooth")

    # Add nodes
    subdiv = add_node(tree, "GeometryNodeSubdivideMesh", location=(0, 0))
    subdiv.inputs["Level"].default_value = 2

    smooth = add_node(tree, "GeometryNodeSetShadeSmooth", location=(200, 0))

    # Connect: Input.Geometry -> Subdivide.Mesh -> SmoothShade.Geometry -> Output.Geometry
    link(tree, gin, "Geometry", subdiv, "Mesh")
    link(tree, subdiv, "Mesh", smooth, "Geometry")
    link(tree, smooth, "Geometry", gout, "Geometry")

    return tree


def verify():
    cleanup()
    tree = build_tree()
    obj = create_test_mesh("cube")

    stats_before = evaluate_and_check(obj)
    apply_as_modifier(obj, tree)
    stats_after = evaluate_and_check(obj)

    result = {
        "pattern_name": PATTERN_NAME,
        "description": PATTERN_DESCRIPTION,
        "blender_version": bpy.app.version_string,
        "verified": True,
        "stats_before": stats_before,
        "stats_after": stats_after,
        "tree_structure": export_tree_structure(tree),
        "assertions": [],
    }

    # Verify subdivision worked (cube: 8 verts -> should be many more at level 2)
    if stats_after["vertices"] > stats_before["vertices"]:
        result["assertions"].append({"check": "vertex_count_increased", "passed": True})
    else:
        result["assertions"].append({"check": "vertex_count_increased", "passed": False})
        result["verified"] = False

    return result


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, default=str))

    if result["verified"]:
        print(f"\nPATTERN VERIFIED: {PATTERN_NAME}")
    else:
        print(f"\nPATTERN FAILED: {PATTERN_NAME}")
        sys.exit(1)
