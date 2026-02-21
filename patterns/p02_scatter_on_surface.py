"""
Pattern 02: Scatter Points on Surface -> Vertices
===================================================
Distributes random points on a mesh surface and converts them
to mesh vertices so the result is pure mesh geometry.

Input: Mesh geometry
Output: Original mesh + scattered vertices merged

Nodes used:
  - Distribute Points on Faces (GeometryNodeDistributePointsOnFaces)
  - Points to Vertices (GeometryNodePointsToVertices)
  - Join Geometry (GeometryNodeJoinGeometry)

Note: Without Points to Vertices, scatter outputs a point cloud which
      won't show up in to_mesh() evaluation. This is an important
      lesson: point clouds and meshes are different geometry types.
"""

import bpy
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pattern_utils import (
    create_node_tree, add_node, link, apply_as_modifier,
    create_test_mesh, evaluate_and_check, export_tree_structure, cleanup
)

PATTERN_NAME = "scatter_on_surface"
PATTERN_DESCRIPTION = "Distributes random points on mesh faces, converts to vertices"


def build_tree():
    tree, gin, gout = create_node_tree("ScatterOnSurface")

    # Distribute Points on Faces
    scatter = add_node(tree, "GeometryNodeDistributePointsOnFaces", location=(0, 0))
    scatter.distribute_method = 'RANDOM'
    scatter.inputs["Density"].default_value = 50.0

    # Convert point cloud to mesh vertices
    to_verts = add_node(tree, "GeometryNodePointsToVertices", location=(200, 0))

    # Join original mesh with converted points
    join = add_node(tree, "GeometryNodeJoinGeometry", location=(400, 0))

    # Wire it up
    link(tree, gin, "Geometry", scatter, "Mesh")
    link(tree, scatter, "Points", to_verts, "Points")
    link(tree, to_verts, "Mesh", join, "Geometry")
    link(tree, gin, "Geometry", join, "Geometry")
    link(tree, join, "Geometry", gout, "Geometry")

    return tree


def verify():
    cleanup()
    tree = build_tree()
    obj = create_test_mesh("plane")

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

    # Verify points were added as vertices
    if stats_after["vertices"] > stats_before["vertices"]:
        result["assertions"].append({"check": "vertices_added", "passed": True})
    else:
        result["assertions"].append({"check": "vertices_added", "passed": False})
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
