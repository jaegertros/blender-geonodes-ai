"""
Pattern 04: Mesh Boolean (Difference)
=======================================
Subtracts one mesh from another using the Boolean node.
Demonstrates combining two geometry streams.

Input: Base mesh
Output: Mesh with a sphere-shaped hole cut out of it

Nodes used:
  - Mesh Boolean (GeometryNodeMeshBoolean)
  - Mesh UV Sphere (GeometryNodeMeshUVSphere) -- as the cutter
  - Transform Geometry (GeometryNodeTransform)
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

PATTERN_NAME = "mesh_boolean_difference"
PATTERN_DESCRIPTION = "Subtracts a sphere from the input mesh using Boolean Difference"


def build_tree():
    tree, gin, gout = create_node_tree("MeshBooleanDifference")

    # Create a sphere as the cutter
    sphere = add_node(tree, "GeometryNodeMeshUVSphere", location=(0, -100))
    sphere.inputs["Radius"].default_value = 0.7
    sphere.inputs["Segments"].default_value = 32
    sphere.inputs["Rings"].default_value = 16

    # Offset the sphere so it partially intersects
    transform = add_node(tree, "GeometryNodeTransform", location=(200, -100))
    transform.inputs["Translation"].default_value = (0.5, 0.5, 0.5)

    # Boolean difference
    boolean = add_node(tree, "GeometryNodeMeshBoolean", location=(400, 0))
    boolean.operation = 'DIFFERENCE'

    # Wire it up
    link(tree, sphere, "Mesh", transform, "Geometry")
    link(tree, gin, "Geometry", boolean, "Mesh 1")
    link(tree, transform, "Geometry", boolean, "Mesh 2")
    link(tree, boolean, "Mesh", gout, "Geometry")

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

    # Boolean should change the mesh topology
    if stats_after["vertices"] != stats_before["vertices"]:
        result["assertions"].append({"check": "topology_changed", "passed": True})
    else:
        result["assertions"].append({"check": "topology_changed", "passed": False})
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
