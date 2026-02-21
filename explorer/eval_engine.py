"""
Multi-Tier Geometry Evaluation Engine
======================================
Evaluates the result of a geometry node tree with nuanced classification
instead of simple pass/fail.

Result categories:
  - MODIFIED:        Geometry changed (verts/edges/faces differ)
  - PASSTHROUGH:     Geometry unchanged (node connected but no visible effect)
  - TYPE_CONVERTED:  Output is a different geometry type (mesh->curve, mesh->points)
  - EMPTY_OUTPUT:    Geometry vanished entirely (0 verts, 0 everything)
  - GENERATED:       New geometry created from nothing (primitive nodes)
  - ERROR:           Python exception or Blender crash
  - LINK_INVALID:    Links created but marked invalid by Blender

Runs inside Blender Python.
"""

import bpy
import json
import traceback


# ──────────────────────────────────────────────────────────────────────
# Known type converter nodes: these convert mesh to a different geometry
# type, so mesh data vanishing is the EXPECTED behavior, not failure.
# ──────────────────────────────────────────────────────────────────────
TYPE_CONVERTER_NODES = {
    "GeometryNodeMeshToCurve",
    "GeometryNodeMeshToPoints",
    "GeometryNodeMeshToVolume",
    "GeometryNodeMeshToDensityGrid",
    "GeometryNodeMeshToSDFGrid",
    "GeometryNodeEdgePathsToCurves",
    "GeometryNodeCurveFillNgons",
    "GeometryNodeCurveFill",
    "GeometryNodeCurveToMesh",
    "GeometryNodeCurveToPoints",
    "GeometryNodePointsToVolume",
    "GeometryNodePointsToCurves",
    "GeometryNodeVolumeCubeGrid",
    "GeometryNodeVolumeToMesh",
    "GeometryNodeDistributePointsInVolume",
    "GeometryNodeDistributePointsOnFaces",  # mesh -> points (different geo type)
}


# ──────────────────────────────────────────────────────────────────────
# Geometry snapshot: captures ALL geometry component types, not just mesh
# ──────────────────────────────────────────────────────────────────────

def snapshot_geometry(obj):
    """Take a comprehensive snapshot of evaluated geometry.

    Captures mesh data via to_mesh(), but also detects non-mesh
    components (point clouds, curves, instances) by checking if
    the evaluated object has them.

    Returns a dict with geometry stats.
    """
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
    except Exception as e:
        return {"error": str(e), "has_geometry": False}

    snap = {
        "has_geometry": False,
        "mesh": {"vertices": 0, "edges": 0, "polygons": 0},
        "bounding_box": None,
    }

    # Try to get mesh data
    try:
        mesh = eval_obj.to_mesh()
        if mesh is not None:
            snap["mesh"]["vertices"] = len(mesh.vertices)
            snap["mesh"]["edges"] = len(mesh.edges)
            snap["mesh"]["polygons"] = len(mesh.polygons)

            if len(mesh.vertices) > 0:
                snap["has_geometry"] = True

            eval_obj.to_mesh_clear()
    except Exception:
        pass  # to_mesh() can fail for non-mesh types

    # Get bounding box (works for any evaluated object)
    try:
        if eval_obj.bound_box:
            coords = [list(v) for v in eval_obj.bound_box]
            mins = [min(c[i] for c in coords) for i in range(3)]
            maxs = [max(c[i] for c in coords) for i in range(3)]
            volume = 1.0
            for i in range(3):
                volume *= max(maxs[i] - mins[i], 0)
            snap["bounding_box"] = {
                "min": mins,
                "max": maxs,
                "volume": volume,
            }
            if volume > 0:
                snap["has_geometry"] = True
    except Exception:
        pass

    return snap


def compare_snapshots(before, after, is_type_converter=False):
    """Compare two geometry snapshots and classify the change.

    Args:
        before: snapshot before node insertion
        after: snapshot after node insertion
        is_type_converter: if True, the node is known to output a different
            geometry type (e.g., Mesh to Curve, Mesh to Points). Empty mesh
            output is expected and classified as TYPE_CONVERTED not EMPTY_OUTPUT.

    Returns (category, details) tuple.
    """
    # Error cases
    if "error" in after:
        return "ERROR", {"reason": after["error"]}

    b_mesh = before.get("mesh", {})
    a_mesh = after.get("mesh", {})

    b_verts = b_mesh.get("vertices", 0)
    b_edges = b_mesh.get("edges", 0)
    b_polys = b_mesh.get("polygons", 0)

    a_verts = a_mesh.get("vertices", 0)
    a_edges = a_mesh.get("edges", 0)
    a_polys = a_mesh.get("polygons", 0)

    b_has = before.get("has_geometry", False)
    a_has = after.get("has_geometry", False)

    # Known type converter: mesh data vanishing is expected
    if is_type_converter and b_verts > 0 and a_verts == 0:
        return "TYPE_CONVERTED", {
            "reason": "Node converts geometry type (mesh -> curve/points/volume/etc.)",
            "before_verts": b_verts,
        }

    # EMPTY_OUTPUT: geometry vanished
    if b_has and not a_has:
        return "EMPTY_OUTPUT", {
            "reason": "Geometry vanished after node insertion",
            "before_verts": b_verts,
        }

    # EMPTY_OUTPUT: started with geometry, now 0 mesh but maybe non-mesh?
    if b_verts > 0 and a_verts == 0:
        # Check if bounding box still exists (could be curves/instances)
        a_bb = after.get("bounding_box")
        if a_bb and a_bb.get("volume", 0) > 0:
            return "TYPE_CONVERTED", {
                "reason": "Mesh vertices gone but bounding box exists (likely curve/instance/pointcloud)",
                "before_verts": b_verts,
                "after_bb_volume": a_bb["volume"],
            }
        return "EMPTY_OUTPUT", {
            "reason": "All mesh data gone, no bounding box",
            "before_verts": b_verts,
        }

    # GENERATED: started with nothing, now has geometry
    if not b_has and a_has:
        return "GENERATED", {
            "after_verts": a_verts,
            "after_edges": a_edges,
            "after_polys": a_polys,
        }

    # MODIFIED: mesh topology changed
    if a_verts != b_verts or a_edges != b_edges or a_polys != b_polys:
        return "MODIFIED", {
            "vertex_delta": a_verts - b_verts,
            "edge_delta": a_edges - b_edges,
            "polygon_delta": a_polys - b_polys,
        }

    # Check bounding box change (position/scale modification)
    b_bb = before.get("bounding_box")
    a_bb = after.get("bounding_box")
    if b_bb and a_bb:
        bb_changed = False
        for i in range(3):
            if abs(b_bb["min"][i] - a_bb["min"][i]) > 0.0001:
                bb_changed = True
            if abs(b_bb["max"][i] - a_bb["max"][i]) > 0.0001:
                bb_changed = True
        if bb_changed:
            return "MODIFIED", {
                "reason": "Topology unchanged but bounds shifted (transform/position change)",
                "vertex_delta": 0,
            }

    # PASSTHROUGH: nothing changed
    return "PASSTHROUGH", {
        "reason": "Geometry passed through unchanged",
        "verts": a_verts,
    }


# ──────────────────────────────────────────────────────────────────────
# Test harness: insert a node into a base tree and evaluate
# ──────────────────────────────────────────────────────────────────────

def test_node_insertion(node_type_id, node_catalog_entry, base_mesh_type="cube"):
    """Test inserting a single node into a passthrough tree.

    Creates: GroupInput -> [TEST_NODE] -> GroupOutput
    Connects via the first compatible Geometry socket pair.
    If the node has no Geometry in/out, tries to connect it
    as a field/value modifier via Set Position or similar.

    Returns a result dict.
    """
    result = {
        "node_type": node_type_id,
        "node_name": node_catalog_entry.get("name", ""),
        "base_mesh": base_mesh_type,
        "category": "ERROR",
        "details": {},
        "links_valid": True,
        "tree_structure": None,
    }

    try:
        # Clean slate
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for ng in list(bpy.data.node_groups):
            bpy.data.node_groups.remove(ng)
        for m in list(bpy.data.meshes):
            if m.users == 0:
                bpy.data.meshes.remove(m)

        # Create test object
        if base_mesh_type == "cube":
            bpy.ops.mesh.primitive_cube_add()
        elif base_mesh_type == "plane":
            bpy.ops.mesh.primitive_plane_add(size=4)
        elif base_mesh_type == "sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        obj = bpy.context.active_object

        # Snapshot before
        snap_before = snapshot_geometry(obj)

        # Build node tree
        tree = bpy.data.node_groups.new("ExploreTree", "GeometryNodeTree")
        tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

        gin = tree.nodes.new("NodeGroupInput")
        gin.location = (-400, 0)
        gout = tree.nodes.new("NodeGroupOutput")
        gout.location = (400, 0)

        # Try to add the test node
        test_node = tree.nodes.new(node_type_id)
        test_node.location = (0, 0)

        # Analyze sockets
        inputs = node_catalog_entry.get("inputs", [])
        outputs = node_catalog_entry.get("outputs", [])

        geo_inputs = [s for s in inputs if s["type"] == "GEOMETRY"]
        geo_outputs = [s for s in outputs if s["type"] == "GEOMETRY"]

        links_made = []
        all_valid = True

        if geo_inputs and geo_outputs:
            # GEO_IO: Insert inline between input and output
            # GroupInput.Geometry -> TestNode.first_geo_in
            lnk1 = tree.links.new(
                gin.outputs["Geometry"],
                test_node.inputs[geo_inputs[0]["name"]]
            )
            links_made.append(("GroupInput.Geometry", f"{test_node.name}.{geo_inputs[0]['name']}", lnk1.is_valid))
            if not lnk1.is_valid:
                all_valid = False

            # TestNode.first_geo_out -> GroupOutput.Geometry
            lnk2 = tree.links.new(
                test_node.outputs[geo_outputs[0]["name"]],
                gout.inputs["Geometry"]
            )
            links_made.append((f"{test_node.name}.{geo_outputs[0]['name']}", "GroupOutput.Geometry", lnk2.is_valid))
            if not lnk2.is_valid:
                all_valid = False

        elif geo_outputs and not geo_inputs:
            # GEO_OUT only (generator/primitive): TestNode.geo_out -> GroupOutput
            # Don't connect GroupInput at all - this node generates geometry
            lnk = tree.links.new(
                test_node.outputs[geo_outputs[0]["name"]],
                gout.inputs["Geometry"]
            )
            links_made.append((f"{test_node.name}.{geo_outputs[0]['name']}", "GroupOutput.Geometry", lnk.is_valid))
            if not lnk.is_valid:
                all_valid = False

        elif geo_inputs and not geo_outputs:
            # GEO_IN only (consumer like Viewer, Raycast):
            # Pass geometry through and also feed it to the consumer
            # GroupInput -> GroupOutput (passthrough)
            tree.links.new(gin.outputs["Geometry"], gout.inputs["Geometry"])
            # GroupInput -> TestNode (for exploration, won't affect output)
            lnk = tree.links.new(
                gin.outputs["Geometry"],
                test_node.inputs[geo_inputs[0]["name"]]
            )
            links_made.append(("GroupInput.Geometry", f"{test_node.name}.{geo_inputs[0]['name']}", lnk.is_valid))
            # This will always be PASSTHROUGH since consumer doesn't feed output
            result["details"]["note"] = "Consumer node (geo_in only) - connected but cannot affect output"

        else:
            # No geometry sockets at all (math/utility node)
            # Just pass geometry through - node is a field/value tool
            tree.links.new(gin.outputs["Geometry"], gout.inputs["Geometry"])
            result["details"]["note"] = "No geometry sockets - field/value utility node"

        result["links_valid"] = all_valid
        result["links"] = links_made

        if not all_valid:
            result["category"] = "LINK_INVALID"
            result["details"]["reason"] = "One or more links marked invalid by Blender"
            return result

        # Apply modifier and evaluate
        mod = obj.modifiers.new("TestGeoNodes", "NODES")
        mod.node_group = tree

        snap_after = snapshot_geometry(obj)

        # Classify the result
        is_converter = node_type_id in TYPE_CONVERTER_NODES
        category, details = compare_snapshots(snap_before, snap_after, is_type_converter=is_converter)
        result["category"] = category
        result["details"].update(details)
        if is_converter:
            result["details"]["is_type_converter"] = True
        result["snapshot_before"] = snap_before
        result["snapshot_after"] = snap_after

    except Exception as e:
        result["category"] = "ERROR"
        result["details"] = {
            "exception": str(e),
            "traceback": traceback.format_exc(),
        }

    return result


def test_node_with_property_variations(node_type_id, node_catalog_entry, base_mesh_type="cube"):
    """Test a node with all its enum property variations.

    For nodes like Math (ADD, SUBTRACT, MULTIPLY...) or Boolean
    (UNION, INTERSECT, DIFFERENCE), cycles through each enum value
    and records the result.

    Returns a list of results.
    """
    results = []

    # Get properties with enum options
    properties = node_catalog_entry.get("properties", {})
    enum_props = {}
    for prop_name, prop_info in properties.items():
        if isinstance(prop_info, dict) and "enum_items" in prop_info:
            enum_props[prop_name] = prop_info["enum_items"]

    if not enum_props:
        # No enum properties - just test default
        r = test_node_insertion(node_type_id, node_catalog_entry, base_mesh_type)
        r["property_variation"] = "default"
        results.append(r)
        return results

    # Test each enum variation for the first (usually most important) enum prop
    # Testing all combinations would be combinatorial explosion
    for prop_name, enum_items in enum_props.items():
        for item in enum_items:
            item_id = item["identifier"] if isinstance(item, dict) else item

            r = test_node_insertion_with_props(
                node_type_id, node_catalog_entry, base_mesh_type,
                {prop_name: item_id}
            )
            r["property_variation"] = f"{prop_name}={item_id}"
            results.append(r)

        break  # Only first enum prop for now

    return results


def test_node_insertion_with_props(node_type_id, node_catalog_entry, base_mesh_type, props_to_set):
    """Like test_node_insertion but sets properties on the test node before evaluation."""
    # We modify the test to set properties after node creation
    result = {
        "node_type": node_type_id,
        "node_name": node_catalog_entry.get("name", ""),
        "base_mesh": base_mesh_type,
        "properties_set": props_to_set,
        "category": "ERROR",
        "details": {},
        "links_valid": True,
    }

    try:
        # Clean slate
        for obj_item in list(bpy.data.objects):
            bpy.data.objects.remove(obj_item, do_unlink=True)
        for ng in list(bpy.data.node_groups):
            bpy.data.node_groups.remove(ng)
        for m in list(bpy.data.meshes):
            if m.users == 0:
                bpy.data.meshes.remove(m)

        # Create test object
        if base_mesh_type == "cube":
            bpy.ops.mesh.primitive_cube_add()
        elif base_mesh_type == "plane":
            bpy.ops.mesh.primitive_plane_add(size=4)
        elif base_mesh_type == "sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        obj = bpy.context.active_object

        snap_before = snapshot_geometry(obj)

        # Build tree
        tree = bpy.data.node_groups.new("ExploreTree", "GeometryNodeTree")
        tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

        gin = tree.nodes.new("NodeGroupInput")
        gin.location = (-400, 0)
        gout = tree.nodes.new("NodeGroupOutput")
        gout.location = (400, 0)

        test_node = tree.nodes.new(node_type_id)
        test_node.location = (0, 0)

        # SET PROPERTIES BEFORE WIRING (important - sockets can change!)
        for prop_name, prop_value in props_to_set.items():
            try:
                setattr(test_node, prop_name, prop_value)
            except Exception as e:
                result["details"][f"prop_error_{prop_name}"] = str(e)

        # Re-read sockets after property change (they may have changed!)
        geo_inputs = [s for s in test_node.inputs if s.type == "GEOMETRY"]
        geo_outputs = [s for s in test_node.outputs if s.type == "GEOMETRY"]

        all_valid = True

        if geo_inputs and geo_outputs:
            lnk1 = tree.links.new(gin.outputs["Geometry"], geo_inputs[0])
            lnk2 = tree.links.new(geo_outputs[0], gout.inputs["Geometry"])
            if not lnk1.is_valid or not lnk2.is_valid:
                all_valid = False
        elif geo_outputs:
            lnk = tree.links.new(geo_outputs[0], gout.inputs["Geometry"])
            if not lnk.is_valid:
                all_valid = False
        elif geo_inputs:
            tree.links.new(gin.outputs["Geometry"], gout.inputs["Geometry"])
            tree.links.new(gin.outputs["Geometry"], geo_inputs[0])
        else:
            tree.links.new(gin.outputs["Geometry"], gout.inputs["Geometry"])

        result["links_valid"] = all_valid
        if not all_valid:
            result["category"] = "LINK_INVALID"
            return result

        mod = obj.modifiers.new("TestGeoNodes", "NODES")
        mod.node_group = tree

        snap_after = snapshot_geometry(obj)
        is_converter = node_type_id in TYPE_CONVERTER_NODES
        category, details = compare_snapshots(snap_before, snap_after, is_type_converter=is_converter)
        result["category"] = category
        result["details"].update(details)
        if is_converter:
            result["details"]["is_type_converter"] = True
        result["snapshot_before"] = snap_before
        result["snapshot_after"] = snap_after

    except Exception as e:
        result["category"] = "ERROR"
        result["details"] = {
            "exception": str(e),
            "traceback": traceback.format_exc(),
        }

    return result
