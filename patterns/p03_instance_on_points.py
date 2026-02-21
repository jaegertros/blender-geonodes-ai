"""
Pattern 03: Instance on Points (Realized)
===========================================
Scatters copies of one mesh onto points generated on another mesh,
then realizes the instances into actual mesh data.

Input: Base mesh (surface)
Output: Realized instances + original mesh

Nodes used:
  - Distribute Points on Faces (GeometryNodeDistributePointsOnFaces)
  - Instance on Points (GeometryNodeInstanceOnPoints)
  - Realize Instances (GeometryNodeRealizeInstances)
  - Mesh Ico Sphere (GeometryNodeMeshIcoSphere) -- self-contained instance source
  - Join Geometry (GeometryNodeJoinGeometry)

Note: Without Realize Instances, instanced geometry won't appear in
      to_mesh() evaluation. Instances are lightweight references;
      Realize converts them to actual geometry data.
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

PATTERN_NAME = "instance_on_points"
PATTERN_DESCRIPTION = "Instances small spheres on surface points, then realizes them"


def build_tree():
    tree, gin, gout = create_node_tree("InstanceOnPoints")

    # Scatter points on the input mesh
    scatter = add_node(tree, "GeometryNodeDistributePointsOnFaces", location=(0, 100))
    scatter.distribute_method = 'RANDOM'
    scatter.inputs["Density"].default_value = 20.0

    # Create a small ico sphere as instance geometry
    ico = add_node(tree, "GeometryNodeMeshIcoSphere", location=(0, -100))
    ico.inputs["Radius"].default_value = 0.05
    ico.inputs["Subdivisions"].default_value = 1

    # Instance the ico sphere on the scattered points
    instance = add_node(tree, "GeometryNodeInstanceOnPoints", location=(250, 0))

    # Realize instances to convert to actual mesh data
    realize = add_node(tree, "GeometryNodeRealizeInstances", location=(450, 0))

    # Join realized instances with original mesh
    join = add_node(tree, "GeometryNodeJoinGeometry", location=(650, 0))

    # Wire it up
    link(tree, gin, "Geometry", scatter, "Mesh")
    link(tree, scatter, "Points", instance, "Points")
    link(tree, ico, "Mesh", instance, "Instance")
    link(tree, instance, "Instances", realize, "Geometry")
    link(tree, realize, "Geometry", join, "Geometry")
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

    # After instancing + realize, vertex count should be much higher
    if stats_after["vertices"] > stats_before["vertices"] * 2:
        result["assertions"].append({"check": "instances_realized", "passed": True})
    else:
        result["assertions"].append({"check": "instances_realized", "passed": False})
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
