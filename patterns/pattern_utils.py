"""
Shared utilities for geometry node pattern scripts.
Provides helper functions for creating node trees, linking sockets,
and exporting pattern structure as JSON.
"""

import bpy
import json


def create_node_tree(name="PatternTree"):
    """Create a new GeometryNodeTree and return (tree, group_input, group_output)."""
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")

    # Add mandatory Geometry in/out
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    # Blender does NOT auto-create Group Input/Output nodes via API
    # (only the UI does this). Create them manually.
    group_input = tree.nodes.new("NodeGroupInput")
    group_input.location = (-400, 0)

    group_output = tree.nodes.new("NodeGroupOutput")
    group_output.location = (600, 0)

    return tree, group_input, group_output


def add_node(tree, type_id, location=(0, 0), **properties):
    """Add a node to the tree, set properties, return the node."""
    node = tree.nodes.new(type_id)
    node.location = location

    for key, value in properties.items():
        if hasattr(node, key):
            setattr(node, key, value)

    return node


def link(tree, from_node, from_socket_name, to_node, to_socket_name):
    """Link two sockets by name. Returns the link."""
    out_socket = None
    for s in from_node.outputs:
        if s.name == from_socket_name:
            out_socket = s
            break

    in_socket = None
    for s in to_node.inputs:
        if s.name == to_socket_name:
            in_socket = s
            break

    if not out_socket:
        raise ValueError(f"Output socket '{from_socket_name}' not found on {from_node.name}. "
                        f"Available: {[s.name for s in from_node.outputs]}")
    if not in_socket:
        raise ValueError(f"Input socket '{to_socket_name}' not found on {to_node.name}. "
                        f"Available: {[s.name for s in to_node.inputs]}")

    return tree.links.new(out_socket, in_socket)


def apply_as_modifier(obj, tree, modifier_name="GeometryNodes"):
    """Apply a node tree as a geometry nodes modifier on an object."""
    mod = obj.modifiers.new(modifier_name, "NODES")
    mod.node_group = tree
    return mod


def create_test_mesh(mesh_type="cube"):
    """Create a test mesh object and return it.

    Uses bpy.ops operators for creation since data-level (bmesh)
    created objects don't get proper depsgraph evaluation for
    geometry nodes modifiers in headless mode.
    """
    # Deselect all first (safely)
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except RuntimeError:
        pass  # No objects or no context

    if mesh_type == "cube":
        bpy.ops.mesh.primitive_cube_add()
    elif mesh_type == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
    elif mesh_type == "plane":
        bpy.ops.mesh.primitive_plane_add(size=4)
    elif mesh_type == "monkey":
        bpy.ops.mesh.primitive_monkey_add()
    elif mesh_type == "grid":
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10)
    else:
        raise ValueError(f"Unknown mesh type: {mesh_type}")

    return bpy.context.active_object


def evaluate_and_check(obj):
    """Force evaluation and return basic geometry stats."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()

    stats = {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
        "bounding_box": {
            "min": list(eval_obj.bound_box[0]),
            "max": list(eval_obj.bound_box[6]),
        },
    }

    eval_obj.to_mesh_clear()
    return stats


def export_tree_structure(tree):
    """Export a node tree's structure as a JSON-serializable dict."""
    nodes = []
    for node in tree.nodes:
        node_data = {
            "type": node.bl_idname,
            "name": node.name,
            "label": node.label,
            "location": list(node.location),
        }

        # Capture key properties (filter out bl_ internal and UI-only props)
        props = {}
        for prop in node.bl_rna.properties:
            if prop.identifier in (
                "rna_type", "type", "name", "label", "location",
                "width", "width_hidden", "height", "dimensions",
                "color", "select", "show_options", "show_preview",
                "hide", "mute", "show_texture", "use_custom_color",
                "parent", "internal_links", "inputs", "outputs",
                "is_active_output",
                # bl_ internal properties - useless for generation
                "bl_idname", "bl_label", "bl_description", "bl_icon",
                "bl_static_type", "bl_width_default", "bl_width_min",
                "bl_width_max", "bl_height_default", "bl_height_min",
                "bl_height_max",
            ):
                continue
            # Catch any other bl_ prefixed properties we didn't list
            if prop.identifier.startswith("bl_"):
                continue
            if prop.is_readonly:
                continue
            try:
                val = getattr(node, prop.identifier)
                if isinstance(val, (int, float, str, bool)):
                    props[prop.identifier] = val
                elif hasattr(val, '__iter__') and not isinstance(val, str):
                    props[prop.identifier] = list(val)
            except (AttributeError, TypeError):
                pass

        if props:
            node_data["properties"] = props

        # Socket defaults
        input_defaults = {}
        for s in node.inputs:
            if hasattr(s, "default_value") and s.default_value is not None:
                try:
                    val = s.default_value
                    if hasattr(val, '__iter__') and not isinstance(val, str):
                        input_defaults[s.name] = list(val)
                    else:
                        input_defaults[s.name] = val
                except (TypeError, AttributeError):
                    pass
        if input_defaults:
            node_data["input_defaults"] = input_defaults

        nodes.append(node_data)

    links = []
    for lnk in tree.links:
        links.append({
            "from_node": lnk.from_node.name,
            "from_socket": lnk.from_socket.name,
            "to_node": lnk.to_node.name,
            "to_socket": lnk.to_socket.name,
            "is_valid": lnk.is_valid,
        })

    return {
        "name": tree.name,
        "nodes": nodes,
        "links": links,
        "interface": {
            "inputs": [
                {"name": item.name, "socket_type": item.socket_type}
                for item in tree.interface.items_tree
                if item.in_out == "INPUT" and hasattr(item, "socket_type")
            ],
            "outputs": [
                {"name": item.name, "socket_type": item.socket_type}
                for item in tree.interface.items_tree
                if item.in_out == "OUTPUT" and hasattr(item, "socket_type")
            ],
        },
    }


def cleanup():
    """Remove all objects and node trees from the scene.

    Uses data-level removal instead of operators to avoid
    EXCEPTION_ACCESS_VIOLATION crashes when running multiple
    patterns sequentially in headless mode.
    """
    # Remove all objects via data API (not operators)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Remove all node groups
    for tree in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(tree)

    # Clean orphaned meshes, curves, etc.
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for curve in list(bpy.data.curves):
        if curve.users == 0:
            bpy.data.curves.remove(curve)
