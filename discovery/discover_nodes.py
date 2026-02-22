"""
Blender Geometry Nodes Discovery Script
========================================
Run in headless Blender to enumerate all geometry node types,
their inputs, outputs, socket types, and default values.

Usage:
    blender --background --python discovery/discover_nodes.py

Output:
    discovery/node_catalog.json
"""

import bpy
import json
import sys
import os
from datetime import datetime


def get_socket_info(socket):
    """Extract detailed information from a node socket."""
    info = {
        "name": socket.name,
        "identifier": socket.identifier,
        "type": socket.type,
        "in_out": socket.is_output and "OUTPUT" or "INPUT",
    }

    # Check if it's a multi-input socket (can accept multiple connections)
    if hasattr(socket, "is_multi_input"):
        info["is_multi_input"] = socket.is_multi_input

    # Try to get default value and its range
    if hasattr(socket, "default_value"):
        try:
            val = socket.default_value
            # Handle different value types
            if hasattr(val, "__len__"):
                # Vector, Color, etc.
                info["default_value"] = list(val)
            elif isinstance(val, (int, float, bool, str)):
                info["default_value"] = val
            else:
                info["default_value"] = str(val)
        except Exception:
            pass

    # Try to get min/max values
    if hasattr(socket, "min_value"):
        try:
            info["min_value"] = socket.min_value
        except Exception:
            pass
    if hasattr(socket, "max_value"):
        try:
            info["max_value"] = socket.max_value
        except Exception:
            pass

    return info


def get_node_properties(node):
    """Extract configurable properties from a node (enums, modes, etc.)."""
    properties = {}

    # Get RNA properties that are user-configurable
    for prop in node.bl_rna.properties:
        # Skip built-in properties that every node has
        if prop.identifier in (
            "rna_type", "type", "location", "width", "width_hidden",
            "height", "name", "label", "inputs", "outputs", "internal_links",
            "parent", "use_custom_color", "color", "select", "show_options",
            "show_preview", "hide", "mute", "show_texture", "bl_idname",
            "bl_label", "bl_description", "bl_icon", "bl_static_type",
            "bl_width_default", "bl_width_min", "bl_width_max",
            "bl_height_default", "bl_height_min", "bl_height_max",
            "dimensions", "is_active_output",
        ):
            continue
        # Catch any other bl_ prefixed internal properties
        if prop.identifier.startswith("bl_"):
            continue

        prop_info = {
            "name": prop.name,
            "description": prop.description,
            "type": prop.type,
        }

        # For enum properties, capture the available options
        if prop.type == "ENUM":
            try:
                prop_info["enum_items"] = [
                    {
                        "identifier": item.identifier,
                        "name": item.name,
                        "description": item.description,
                    }
                    for item in prop.enum_items
                ]
            except Exception:
                pass
            # Get current/default value
            try:
                prop_info["default"] = prop.default
            except Exception:
                pass

        elif prop.type in ("INT", "FLOAT"):
            try:
                prop_info["default"] = prop.default
                prop_info["min"] = prop.hard_min
                prop_info["max"] = prop.hard_max
                prop_info["soft_min"] = prop.soft_min
                prop_info["soft_max"] = prop.soft_max
            except Exception:
                pass

        elif prop.type == "BOOLEAN":
            try:
                prop_info["default"] = prop.default
            except Exception:
                pass

        elif prop.type == "STRING":
            try:
                prop_info["default"] = prop.default
            except Exception:
                pass

        properties[prop.identifier] = prop_info

    return properties


def discover_geometry_node_types():
    """Find all geometry node type identifiers available in this Blender version."""
    node_types = []

    # Method 1: Scan bpy.types for GeometryNode* classes
    for attr_name in dir(bpy.types):
        if attr_name.startswith("GeometryNode"):
            cls = getattr(bpy.types, attr_name)
            # Check it's actually a node type (has bl_rna)
            if hasattr(cls, "bl_rna"):
                node_types.append(attr_name)

    # Method 2: Also check for function/utility nodes used in geometry node trees
    # These have different prefixes but are valid in GeometryNodeTree
    additional_prefixes = [
        "FunctionNode",
        "ShaderNodeMath",
        "ShaderNodeVectorMath",
        "ShaderNodeMapRange",
        "ShaderNodeClamp",
        "ShaderNodeMixRGB",
        "ShaderNodeMix",
        "ShaderNodeValToRGB",  # ColorRamp
        "ShaderNodeRGBCurve",
        "ShaderNodeSeparateXYZ",
        "ShaderNodeCombineXYZ",
        "ShaderNodeSeparateColor",
        "ShaderNodeCombineColor",
    ]

    for attr_name in dir(bpy.types):
        for prefix in additional_prefixes:
            if attr_name == prefix and attr_name not in node_types:
                cls = getattr(bpy.types, attr_name)
                if hasattr(cls, "bl_rna"):
                    node_types.append(attr_name)

    return sorted(set(node_types))


def instantiate_and_inspect(node_tree, node_type_id):
    """
    Add a node of the given type to the tree, inspect it, then remove it.
    Returns node info dict or None if the node can't be created.
    """
    try:
        node = node_tree.nodes.new(type=node_type_id)
    except Exception as e:
        return {"error": str(e), "type_id": node_type_id}

    info = {
        "type_id": node_type_id,
        "name": node.name,
        "bl_label": getattr(node, "bl_label", node.name),
        "bl_description": getattr(node.bl_rna, "description", ""),
        "bl_icon": getattr(node, "bl_icon", ""),
        "inputs": [],
        "outputs": [],
        "properties": {},
    }

    # Collect input sockets
    for socket in node.inputs:
        info["inputs"].append(get_socket_info(socket))

    # Collect output sockets
    for socket in node.outputs:
        info["outputs"].append(get_socket_info(socket))

    # Collect configurable properties
    info["properties"] = get_node_properties(node)

    # Clean up
    node_tree.nodes.remove(node)

    return info


def collect_socket_types(catalog):
    """Analyze the catalog to produce a summary of all socket types found."""
    socket_types = set()
    for node_id, node_info in catalog["nodes"].items():
        if "error" in node_info:
            continue
        for socket in node_info.get("inputs", []):
            socket_types.add(socket["type"])
        for socket in node_info.get("outputs", []):
            socket_types.add(socket["type"])
    return sorted(socket_types)


def main():
    print("=" * 60)
    print("Blender Geometry Nodes Discovery")
    print("=" * 60)
    print(f"Blender version: {bpy.app.version_string}")
    print(f"Python version: {sys.version}")
    print()

    # Create a temporary node tree for inspection
    temp_tree = bpy.data.node_groups.new("__discovery_temp__", "GeometryNodeTree")

    # Discover all geometry node types
    print("Discovering geometry node types...")
    node_type_ids = discover_geometry_node_types()
    print(f"Found {len(node_type_ids)} potential node types")
    print()

    # Build the catalog
    catalog = {
        "blender_version": bpy.app.version_string,
        "blender_version_tuple": list(bpy.app.version),
        "discovery_date": datetime.now().isoformat(),
        "discovery_script_version": "1.0.0",
        "total_node_types_scanned": len(node_type_ids),
        "nodes": {},
        "errors": [],
        "socket_types_found": [],
    }

    success_count = 0
    error_count = 0

    for i, type_id in enumerate(node_type_ids):
        progress = f"[{i+1}/{len(node_type_ids)}]"
        print(f"{progress} Inspecting {type_id}...", end=" ")

        result = instantiate_and_inspect(temp_tree, type_id)

        if result and "error" in result:
            print(f"ERROR: {result['error']}")
            catalog["errors"].append(result)
            error_count += 1
        elif result:
            in_count = len(result["inputs"])
            out_count = len(result["outputs"])
            prop_count = len(result["properties"])
            print(f"OK ({in_count} inputs, {out_count} outputs, {prop_count} props)")
            catalog["nodes"][type_id] = result
            success_count += 1
        else:
            print("SKIP (no result)")
            error_count += 1

    # Collect socket type summary
    catalog["socket_types_found"] = collect_socket_types(catalog)
    catalog["total_nodes_cataloged"] = success_count
    catalog["total_errors"] = error_count

    # Clean up temporary node tree
    bpy.data.node_groups.remove(temp_tree)

    # Determine output path
    # If run from the project root, output next to the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "node_catalog.json")

    # Write catalog
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False, default=str)

    print()
    print("=" * 60)
    print("Discovery complete!")
    print(f"  Nodes cataloged: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Socket types found: {catalog['socket_types_found']}")
    print(f"  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
