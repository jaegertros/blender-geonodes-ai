"""
Pattern 05: Random Scatter with Position Offset (Crowd Generator)
==================================================================
Distributes points on a surface, applies random position offsets,
then instances cubes on those points and realizes them.
A common "crowd/scatter" setup used for placing objects with variation.

Input: Mesh surface
Output: Realized cube instances with random offsets

Nodes used:
  - Distribute Points on Faces (GeometryNodeDistributePointsOnFaces)
  - Set Position (GeometryNodeSetPosition) -- applies random offset
  - Random Value (FunctionNodeRandomValue) -- generates random vectors
  - Instance on Points (GeometryNodeInstanceOnPoints)
  - Mesh Cube (GeometryNodeMeshCube) -- instance source
  - Realize Instances (GeometryNodeRealizeInstances)

Based on the "CubeCrowdGenerator" pattern for scattering objects
with per-instance randomization.
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

PATTERN_NAME = "random_scatter_instances"
PATTERN_DESCRIPTION = "Scatter cubes on surface with random position offsets, then realize"


def build_tree():
    tree, gin, gout = create_node_tree("RandomScatterInstances")

    # Scatter points on input mesh
    scatter = add_node(tree, "GeometryNodeDistributePointsOnFaces", location=(0, 0))
    scatter.distribute_method = 'RANDOM'
    scatter.inputs["Density"].default_value = 10.0

    # Random vector for position offset
    rand_vec = add_node(tree, "FunctionNodeRandomValue", location=(100, -200))
    rand_vec.data_type = 'FLOAT_VECTOR'
    rand_vec.inputs["Min"].default_value = (-0.5, -0.5, 0.0)
    rand_vec.inputs["Max"].default_value = (0.5, 0.5, 0.5)

    # Set Position with random offset
    set_pos = add_node(tree, "GeometryNodeSetPosition", location=(250, 0))

    # Small cube as instance geometry
    cube = add_node(tree, "GeometryNodeMeshCube", location=(100, -400))
    cube.inputs["Size"].default_value = (0.1, 0.1, 0.1)

    # Instance cubes on offset points
    instance = add_node(tree, "GeometryNodeInstanceOnPoints", location=(450, 0))

    # Realize instances
    realize = add_node(tree, "GeometryNodeRealizeInstances", location=(650, 0))

    # Wire it up
    link(tree, gin, "Geometry", scatter, "Mesh")
    link(tree, scatter, "Points", set_pos, "Geometry")
    link(tree, rand_vec, "Value", set_pos, "Offset")
    link(tree, set_pos, "Geometry", instance, "Points")
    link(tree, cube, "Mesh", instance, "Instance")
    link(tree, instance, "Instances", realize, "Geometry")
    link(tree, realize, "Geometry", gout, "Geometry")

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

    # After realizing, should have many more vertices (cubes * 8 verts each)
    if stats_after["vertices"] > stats_before["vertices"] * 2:
        result["assertions"].append({"check": "cubes_realized", "passed": True})
    else:
        result["assertions"].append({"check": "cubes_realized", "passed": False})
        result["verified"] = False

    # Bounding box should extend beyond original plane due to random offsets
    bb_before = stats_before["bounding_box"]
    bb_after = stats_after["bounding_box"]
    z_grew = bb_after["max"][2] > bb_before["max"][2]
    if z_grew:
        result["assertions"].append({"check": "z_offset_applied", "passed": True})
    else:
        result["assertions"].append({"check": "z_offset_applied", "passed": False})
        # Not a hard failure - random could theoretically give 0 offset

    return result


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, default=str))

    if result["verified"]:
        print(f"\nPATTERN VERIFIED: {PATTERN_NAME}")
    else:
        print(f"\nPATTERN FAILED: {PATTERN_NAME}")
        sys.exit(1)
