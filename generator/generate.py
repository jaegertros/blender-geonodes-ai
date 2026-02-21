"""
Geometry Node Tree Generator
==============================
Generates Python scripts that build geometry node trees in Blender,
using the empirical knowledge base for accuracy.

Two modes:
  1. Template-based: matches known patterns and adapts them
  2. Compositional: builds novel trees from individual node specs

The generator produces standalone Python scripts that can be run
directly in Blender (headless or interactive).

Usage:
  python generator/generate.py "scatter small spheres on a plane surface"
  python generator/generate.py "extrude faces of a cube and scale them down"
  python generator/generate.py "create a pipe along a spiral curve"
"""

import json
import os
import sys
import argparse
from datetime import datetime

# Add project root to path
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_dir)

from generator.context_builder import load_kb, build_context, format_context_for_prompt


# ──────────────────────────────────────────────────────────────────────
# Script template
# ──────────────────────────────────────────────────────────────────────

SCRIPT_HEADER = '''"""
Auto-generated Geometry Node Tree
===================================
Description: {description}
Generated:   {timestamp}
Blender:     {blender_version}

Run in Blender:
  blender --background --factory-startup --python this_script.py
Or paste into Blender's scripting workspace.
"""

import bpy
import json


def cleanup():
    """Remove all objects and node trees."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for tree in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(tree)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def create_node_tree(name="GeneratedTree"):
    """Create a new geometry node tree with Geometry I/O."""
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    # IMPORTANT: Group Input/Output nodes must be created manually via API
    gin = tree.nodes.new("NodeGroupInput")
    gin.location = (-400, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.location = (800, 0)

    return tree, gin, gout


def add_node(tree, type_id, location=(0, 0), **properties):
    """Add a node to the tree and set properties."""
    node = tree.nodes.new(type_id)
    node.location = location
    for key, value in properties.items():
        if hasattr(node, key):
            setattr(node, key, value)
    return node


def link(tree, from_node, from_socket, to_node, to_socket):
    """Link two sockets by name."""
    out_socket = None
    for s in from_node.outputs:
        if s.name == from_socket:
            out_socket = s
            break
    in_socket = None
    for s in to_node.inputs:
        if s.name == to_socket:
            in_socket = s
            break
    if not out_socket:
        raise ValueError(f"Output '{{from_socket}}' not found on {{from_node.name}}")
    if not in_socket:
        raise ValueError(f"Input '{{to_socket}}' not found on {{to_node.name}}")
    return tree.links.new(out_socket, in_socket)

'''

SCRIPT_FOOTER = '''

def main():
    cleanup()
    tree = build_tree()

    # Create test object and apply
    {create_mesh_code}
    obj = bpy.context.active_object

    # Apply geometry nodes modifier
    mod = obj.modifiers.new("GeneratedGeoNodes", "NODES")
    mod.node_group = tree

    # Verify
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    print(f"Result: {{len(mesh.vertices)}} vertices, {{len(mesh.edges)}} edges, {{len(mesh.polygons)}} faces")
    eval_obj.to_mesh_clear()

    print("\\nGeometry node tree generated successfully!")


if __name__ == "__main__":
    main()
'''


# ──────────────────────────────────────────────────────────────────────
# Pattern-based generation
# ──────────────────────────────────────────────────────────────────────

def generate_from_pattern(pattern, description, kb):
    """Generate a script based on a matched verified pattern."""
    nodes = pattern["nodes_used"]
    links = pattern["links"]

    lines = []
    lines.append("def build_tree():")
    lines.append(f'    """Build geometry node tree: {description}"""')
    lines.append('    tree, gin, gout = create_node_tree("GeneratedTree")')
    lines.append("")

    # Map pattern node names to variable names
    node_vars = {}
    x_pos = 0
    for i, node in enumerate(nodes):
        var_name = f"node_{i}"
        type_id = node["type"]
        node_name = node.get("name", type_id)
        node_vars[node_name] = var_name

        # Build properties string
        props = {}
        if node.get("properties"):
            for pname, pval in node["properties"].items():
                if pname not in ("color_tag", "warning_propagation", "location_absolute"):
                    props[pname] = pval

        # Build input defaults
        defaults = node.get("input_defaults", {})

        lines.append(f"    # {node_name}")
        prop_str = ""
        if props:
            prop_items = [f"{k}={repr(v)}" for k, v in props.items()]
            prop_str = ", " + ", ".join(prop_items)

        lines.append(f'    {var_name} = add_node(tree, "{type_id}", location=({x_pos}, 0){prop_str})')

        # Set input defaults
        for dname, dval in defaults.items():
            if isinstance(dval, (list, tuple)):
                lines.append(f'    {var_name}.inputs["{dname}"].default_value = {tuple(dval)}')
            elif isinstance(dval, (int, float)):
                lines.append(f'    {var_name}.inputs["{dname}"].default_value = {dval}')

        lines.append("")
        x_pos += 250

    # Generate links
    lines.append("    # Wire connections")
    for lnk in links:
        from_node = lnk["from_node"]
        from_socket = lnk["from_socket"]
        to_node = lnk["to_node"]
        to_socket = lnk["to_socket"]

        # Map pattern node names to our variable names
        if from_node == "Group Input":
            from_var = "gin"
        elif from_node in node_vars:
            from_var = node_vars[from_node]
        else:
            from_var = f'tree.nodes["{from_node}"]'

        if to_node == "Group Output":
            to_var = "gout"
        elif to_node in node_vars:
            to_var = node_vars[to_node]
        else:
            to_var = f'tree.nodes["{to_node}"]'

        lines.append(f'    link(tree, {from_var}, "{from_socket}", {to_var}, "{to_socket}")')

    lines.append("")
    lines.append("    return tree")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Compositional generation (for novel combinations)
# ──────────────────────────────────────────────────────────────────────

def generate_compositional(context, description, kb):
    """Generate a script by composing nodes from the context.

    Strategy:
      1. Identify the processing pipeline from the description
      2. Select nodes that chain together (geo_out -> geo_in)
      3. Connect them in sequence
      4. Add field/value nodes as modifiers where appropriate
    """
    nodes = context["matched_nodes"]

    # Separate by role
    generators = [(nid, spec) for nid, spec in nodes.items() if spec.get("role") == "generator"]
    processors = [(nid, spec) for nid, spec in nodes.items() if spec.get("role") == "processor"]
    fields = [(nid, spec) for nid, spec in nodes.items() if spec.get("role") == "field"]

    # Build a linear chain: input -> processors -> output
    # If there are generators, they create geometry that feeds in
    chain = []

    # Start with processors that modify geometry
    for nid, spec in processors:
        if spec.get("observed_behavior") in ("MODIFIED", "PASSTHROUGH", "TYPE_CONVERTED"):
            chain.append((nid, spec))

    # If no processors, try generators
    if not chain and generators:
        for nid, spec in generators:
            chain.append((nid, spec))

    # If still nothing, just passthrough
    if not chain:
        chain = [("GeometryNodeSubdivideMesh", nodes.get("GeometryNodeSubdivideMesh", {
            "name": "Subdivide Mesh",
            "inputs": [{"name": "Mesh", "type": "GEOMETRY"}, {"name": "Level", "type": "INT"}],
            "outputs": [{"name": "Mesh", "type": "GEOMETRY"}],
        }))]

    lines = []
    lines.append("def build_tree():")
    lines.append(f'    """Build geometry node tree: {description}"""')
    lines.append('    tree, gin, gout = create_node_tree("GeneratedTree")')
    lines.append("")

    node_vars = {}
    x_pos = 0
    prev_geo_output = ("gin", "Geometry")  # Start from group input

    for i, (nid, spec) in enumerate(chain[:8]):  # Limit chain length
        var_name = f"node_{i}"
        node_vars[nid] = var_name
        name = spec.get("name", nid)

        lines.append(f"    # {name}")
        lines.append(f'    {var_name} = add_node(tree, "{nid}", location=({x_pos}, 0))')

        # Find geometry input socket
        geo_in = None
        for s in spec.get("inputs", []):
            if s["type"] == "GEOMETRY":
                geo_in = s["name"]
                break

        # Find geometry output socket
        geo_out = None
        for s in spec.get("outputs", []):
            if s["type"] == "GEOMETRY":
                geo_out = s["name"]
                break

        # Connect previous output to this input
        if geo_in and prev_geo_output:
            from_var, from_sock = prev_geo_output
            lines.append(f'    link(tree, {from_var}, "{from_sock}", {var_name}, "{geo_in}")')

        # Track output for next node
        if geo_out:
            prev_geo_output = (var_name, geo_out)

        lines.append("")
        x_pos += 250

    # Connect last node to output
    if prev_geo_output:
        from_var, from_sock = prev_geo_output
        lines.append(f'    link(tree, {from_var}, "{from_sock}", gout, "Geometry")')

    lines.append("")
    lines.append("    return tree")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Main generation pipeline
# ──────────────────────────────────────────────────────────────────────

def generate_script(description, kb=None, mesh_type="cube"):
    """Generate a complete Blender Python script for the given description.

    Returns the script as a string.
    """
    if kb is None:
        kb = load_kb()

    context = build_context(kb, description)

    # Try pattern matching first
    pattern_matches = context.get("example_patterns", [])
    if pattern_matches:
        best_pattern = pattern_matches[0]
        build_tree_code = generate_from_pattern(best_pattern, description, kb)
        generation_method = f"pattern:{best_pattern['name']}"
    else:
        build_tree_code = generate_compositional(context, description, kb)
        generation_method = "compositional"

    # Determine mesh creation code
    mesh_map = {
        "cube": 'bpy.ops.mesh.primitive_cube_add()',
        "plane": 'bpy.ops.mesh.primitive_plane_add(size=4)',
        "sphere": 'bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)',
        "monkey": 'bpy.ops.mesh.primitive_monkey_add()',
        "grid": 'bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10)',
    }
    create_mesh_code = mesh_map.get(mesh_type, mesh_map["cube"])

    # Assemble
    header = SCRIPT_HEADER.format(
        description=description,
        timestamp=datetime.now().isoformat(),
        blender_version=kb.get("metadata", {}).get("blender_version", "4.5.x"),
    )

    footer = SCRIPT_FOOTER.format(create_mesh_code=create_mesh_code)

    script = header + "\n" + build_tree_code + "\n" + footer

    # Add generation metadata as comment
    script += f"\n# Generation method: {generation_method}\n"
    script += f"# Context: {len(context['matched_nodes'])} nodes, {len(context.get('example_patterns', []))} patterns\n"

    return script, context, generation_method


def main():
    parser = argparse.ArgumentParser(description="Generate geometry node tree scripts")
    parser.add_argument("description", help="Natural language description of desired geometry")
    parser.add_argument("--mesh-type", default="cube", help="Base mesh type (cube, plane, sphere, monkey, grid)")
    parser.add_argument("--output", help="Output file path (default: print to stdout)")
    parser.add_argument("--context", action="store_true", help="Also print the KB context used")
    args = parser.parse_args()

    kb = load_kb()
    script, context, method = generate_script(args.description, kb, args.mesh_type)

    if args.context:
        print("=" * 60)
        print("KB CONTEXT USED:")
        print("=" * 60)
        print(format_context_for_prompt(context))
        print("=" * 60)
        print()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(script)
        print(f"Script written to: {args.output}")
        print(f"Generation method: {method}")
        print(f"Matched {len(context['matched_nodes'])} nodes, {len(context.get('example_patterns', []))} patterns")
    else:
        print(script)


if __name__ == "__main__":
    main()
