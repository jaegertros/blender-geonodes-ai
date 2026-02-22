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


def _match_socket(sockets, name):
    """Find a socket by identifier first, then by display name.

    Blender's C++ engine uses socket.identifier internally.  Display
    names can collide (e.g. Math node has two "Value" inputs), so
    matching by identifier is more reliable.
    """
    for s in sockets:
        if s.identifier == name:
            return s
    for s in sockets:
        if s.name == name:
            return s
    return None


def link(tree, from_node, from_socket, to_node, to_socket):
    """Link two sockets by identifier or name."""
    out_socket = _match_socket(from_node.outputs, from_socket)
    in_socket = _match_socket(to_node.inputs, to_socket)
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

        # Build properties string (filter out bl_ internal and UI-only props)
        props = {}
        if node.get("properties"):
            for pname, pval in node["properties"].items():
                if pname.startswith("bl_"):
                    continue
                if pname in ("color_tag", "warning_propagation", "location_absolute"):
                    continue
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
# Compositional generation — DAG builder (supports branching)
# ──────────────────────────────────────────────────────────────────────
#
# Geometry node trees are Directed Acyclic Graphs, not linear chains.
# The Python API assembles the DAG topology; the C++ runtime evaluates
# it.  Common patterns that require branching:
#
#   Fan-out:  Group Input ──> Distribute Points ──┐
#                         └──> Instance on Points ─┘──> Group Output
#
#   Fan-in:   Branch A ──┐
#                         ├──> Join Geometry / Boolean ──> ...
#             Branch B ──┘
#
#   Side-input: Field node (Math, Noise, etc.) feeding a non-geometry
#               socket of a processor node.
#
# Strategy:
#   1. Classify matched nodes by role (generator / processor / field)
#   2. Detect common multi-node idioms that imply branching
#   3. Build a placement graph with explicit edges
#   4. Emit code that adds nodes and wires them according to the graph

# Recognised multi-node idioms (order matters — first match wins)
IDIOMS = [
    {
        "name": "scatter_instances",
        "description": "Distribute points on a surface then instance objects on them",
        "trigger_nodes": {"GeometryNodeDistributePointsOnFaces", "GeometryNodeInstanceOnPoints"},
        "optional_nodes": {"GeometryNodeRealizeInstances"},
        "build": "_build_scatter_instances",
    },
    {
        "name": "boolean_op",
        "description": "Combine two geometry streams with a boolean operation",
        "trigger_nodes": {"GeometryNodeMeshBoolean"},
        "optional_nodes": set(),
        "build": "_build_boolean_op",
    },
    {
        "name": "join_geometry",
        "description": "Merge multiple geometry streams",
        "trigger_nodes": {"GeometryNodeJoinGeometry"},
        "optional_nodes": set(),
        "build": "_build_join_geometry",
    },
    {
        "name": "curve_to_mesh",
        "description": "Sweep a profile curve along a path curve",
        "trigger_nodes": {"GeometryNodeCurveToMesh"},
        "optional_nodes": {"GeometryNodeCurvePrimitiveCircle", "GeometryNodeCurvePrimitiveLine"},
        "build": "_build_curve_to_mesh",
    },
]


def _find_socket(spec, direction, socket_type):
    """Find the first socket of a given type in a node spec."""
    key = "inputs" if direction == "in" else "outputs"
    for s in spec.get(key, []):
        if s["type"] == socket_type:
            return s["name"]
    return None


def _find_all_sockets(spec, direction, socket_type):
    """Find all sockets of a given type in a node spec."""
    key = "inputs" if direction == "in" else "outputs"
    return [s["name"] for s in spec.get(key, []) if s["type"] == socket_type]


# Node types whose geometry output contains unrealized instances.
# Without Realize Instances, to_mesh() returns 0 vertices.
_INSTANCE_PRODUCING_NODES = {
    "GeometryNodeInstanceOnPoints",
    "GeometryNodeGeometryToInstance",
    "GeometryNodeCollectionInfo",
    "GeometryNodeObjectInfo",
    "GeometryNodeDuplicateElements",
}


class _DAGBuilder:
    """Accumulates nodes and edges, then emits code."""

    def __init__(self, description):
        self.description = description
        self.nodes = []          # (var_name, type_id, label, col, row)
        self.links = []          # (from_var, from_sock, to_var, to_sock)
        self.defaults = []       # (var_name, socket_name, value)
        self.properties = []     # (var_name, prop_name, value)
        self._var_counter = 0

    def add(self, type_id, label, col=0, row=0):
        """Add a node, return its variable name."""
        var = f"node_{self._var_counter}"
        self._var_counter += 1
        self.nodes.append((var, type_id, label, col, row))
        return var

    def wire(self, from_var, from_sock, to_var, to_sock):
        self.links.append((from_var, from_sock, to_var, to_sock))

    def set_default(self, var, socket_name, value):
        self.defaults.append((var, socket_name, value))

    def set_prop(self, var, prop_name, value):
        self.properties.append((var, prop_name, value))

    def _ensure_realize_instances(self):
        """Auto-insert Realize Instances before Group Output if needed.

        The C++ engine keeps instances as a lightweight InstancesComponent
        until explicitly realized.  Without this, to_mesh() returns zero
        vertices and the generated script appears to produce nothing.
        """
        # Build var -> type_id lookup
        var_to_type = {var: tid for var, tid, _, _, _ in self.nodes}

        # Check if any instance-producing node wires directly to gout
        needs_realize = False
        links_to_patch = []
        for i, (fv, fs, tv, ts) in enumerate(self.links):
            if tv == "gout" and var_to_type.get(fv) in _INSTANCE_PRODUCING_NODES:
                needs_realize = True
                links_to_patch.append(i)

        if not needs_realize:
            return

        # Check if Realize Instances already exists in the graph
        for _, tid, _, _, _ in self.nodes:
            if tid == "GeometryNodeRealizeInstances":
                return  # Already present, builder handled it

        # Find max column for placement
        max_col = max((col for _, _, _, col, _ in self.nodes), default=1)
        realize_var = self.add("GeometryNodeRealizeInstances",
                               "Realize Instances", col=max_col + 1, row=0)

        # Re-route: instance_node -> gout  becomes  instance_node -> realize -> gout
        for idx in links_to_patch:
            fv, fs, _, _ = self.links[idx]
            self.links[idx] = (fv, fs, realize_var, "Geometry")

        self.wire(realize_var, "Geometry", "gout", "Geometry")

    def emit(self):
        """Emit the build_tree() function as a string.

        Emission order matters because the C++ engine rebuilds socket
        declarations when node properties change (e.g. Math.operation,
        RandomValue.data_type).  We must set properties and defaults
        per-node *before* emitting any links that reference those sockets.
        """
        # Post-processing: auto-insert Realize Instances if needed
        self._ensure_realize_instances()

        lines = []
        lines.append("def build_tree():")
        lines.append(f'    """Build geometry node tree: {self.description}"""')
        lines.append('    tree, gin, gout = create_node_tree("GeneratedTree")')
        lines.append("")

        # Build lookup tables for per-node properties and defaults
        props_by_var = {}
        for var, pname, pval in self.properties:
            props_by_var.setdefault(var, []).append((pname, pval))

        defaults_by_var = {}
        for var, sname, sval in self.defaults:
            defaults_by_var.setdefault(var, []).append((sname, sval))

        # Emit each node with its properties and defaults together
        # (properties MUST be set before links — sockets can change)
        for var, tid, label, col, row in self.nodes:
            x = col * 250
            y = row * -250
            lines.append(f"    # {label}")
            lines.append(f'    {var} = add_node(tree, "{tid}", location=({x}, {y}))')

            # Set properties immediately (triggers socket rebuild in C++)
            for pname, pval in props_by_var.get(var, []):
                lines.append(f'    {var}.{pname} = {repr(pval)}')

            # Set socket defaults
            for sname, sval in defaults_by_var.get(var, []):
                if isinstance(sval, (list, tuple)):
                    lines.append(f'    {var}.inputs["{sname}"].default_value = {tuple(sval)}')
                else:
                    lines.append(f'    {var}.inputs["{sname}"].default_value = {repr(sval)}')

        lines.append("")

        # Emit links (safe now — all nodes have their final socket layout)
        lines.append("    # Wire connections")
        for fv, fs, tv, ts in self.links:
            lines.append(f'    link(tree, {fv}, "{fs}", {tv}, "{ts}")')

        lines.append("")
        lines.append("    return tree")
        return "\n".join(lines)


# ── Idiom builders ───────────────────────────────────────────────────

def _build_scatter_instances(dag, nodes, context):
    """Scatter + Instance pattern (fan-out from input geometry)."""
    dist_spec = nodes.get("GeometryNodeDistributePointsOnFaces", {})
    inst_spec = nodes.get("GeometryNodeInstanceOnPoints", {})

    # Find a generator to use as instance source (ico sphere, cube, etc.)
    instance_source = None
    for nid, spec in nodes.items():
        if spec.get("role") == "generator" and nid not in (
            "GeometryNodeDistributePointsOnFaces", "GeometryNodeInstanceOnPoints",
        ):
            instance_source = (nid, spec)
            break

    # Distribute Points on Faces — takes the input geometry
    dist = dag.add("GeometryNodeDistributePointsOnFaces", "Distribute Points on Faces", col=1, row=0)
    dag.wire("gin", "Geometry", dist, _find_socket(dist_spec, "in", "GEOMETRY") or "Mesh")

    # Instance source (generator or default to Ico Sphere)
    if instance_source:
        src_id, src_spec = instance_source
        src = dag.add(src_id, src_spec.get("name", src_id), col=1, row=1)
    else:
        src = dag.add("GeometryNodeMeshIcoSphere", "Ico Sphere", col=1, row=1)
        dag.set_default(src, "Radius", 0.05)

    # Instance on Points — fan-in: points from Distribute + instance from source
    iop = dag.add("GeometryNodeInstanceOnPoints", "Instance on Points", col=2, row=0)
    dag.wire(dist, "Points", iop, "Points")
    dag.wire(src, _find_socket(nodes.get(instance_source[0] if instance_source else "", {}), "out", "GEOMETRY") or "Mesh", iop, "Instance")

    # Optionally realize instances
    if "GeometryNodeRealizeInstances" in nodes:
        real = dag.add("GeometryNodeRealizeInstances", "Realize Instances", col=3, row=0)
        dag.wire(iop, "Instances", real, "Geometry")
        dag.wire(real, "Geometry", "gout", "Geometry")
    else:
        dag.wire(iop, "Instances", "gout", "Geometry")


def _build_boolean_op(dag, nodes, context):
    """Boolean operation — fan-in of two geometry streams."""
    bool_spec = nodes.get("GeometryNodeMeshBoolean", {})

    # Find a generator for the second operand
    gen_source = None
    for nid, spec in nodes.items():
        if spec.get("role") == "generator":
            gen_source = (nid, spec)
            break

    # Second geometry source (or default to a sphere)
    if gen_source:
        src_id, src_spec = gen_source
        src = dag.add(src_id, src_spec.get("name", src_id), col=1, row=1)
        src_out = _find_socket(src_spec, "out", "GEOMETRY") or "Mesh"
    else:
        src = dag.add("GeometryNodeMeshUVSphere", "UV Sphere", col=1, row=1)
        dag.set_default(src, "Radius", 0.8)
        src_out = "Mesh"

    # Boolean node — two geometry inputs
    boolean = dag.add("GeometryNodeMeshBoolean", "Mesh Boolean", col=2, row=0)

    # Determine the operation enum if available
    enum_props = bool_spec.get("enum_properties", {})
    if "operation" in enum_props:
        dag.set_prop(boolean, "operation", "DIFFERENCE")

    # Mesh Boolean has "Mesh 1" (or "Mesh") + "Mesh 2" inputs
    bool_geo_ins = _find_all_sockets(bool_spec, "in", "GEOMETRY")
    if len(bool_geo_ins) >= 2:
        dag.wire("gin", "Geometry", boolean, bool_geo_ins[0])
        dag.wire(src, src_out, boolean, bool_geo_ins[1])
    else:
        # Fallback: single geometry input (join first)
        dag.wire("gin", "Geometry", boolean, bool_geo_ins[0] if bool_geo_ins else "Mesh")

    bool_geo_out = _find_socket(bool_spec, "out", "GEOMETRY") or "Mesh"
    dag.wire(boolean, bool_geo_out, "gout", "Geometry")


def _build_join_geometry(dag, nodes, context):
    """Join Geometry — fan-in of input geometry plus generated geometry."""
    join_spec = nodes.get("GeometryNodeJoinGeometry", {})

    # Find generators to join
    gen_nodes = [(nid, spec) for nid, spec in nodes.items() if spec.get("role") == "generator"]

    # If no generators are available, skip the Join Geometry node and pass
    # input geometry straight through — a join with a single input is a no-op.
    if not gen_nodes:
        dag.wire("gin", "Geometry", "gout", "Geometry")
        return

    placed_gens = []
    for i, (nid, spec) in enumerate(gen_nodes[:3]):  # Max 3 generators
        g = dag.add(nid, spec.get("name", nid), col=1, row=i + 1)
        placed_gens.append((g, spec))

    join = dag.add("GeometryNodeJoinGeometry", "Join Geometry", col=2, row=0)

    # Input geometry is the first stream
    join_geo_in = _find_socket(join_spec, "in", "GEOMETRY") or "Geometry"
    dag.wire("gin", "Geometry", join, join_geo_in)

    # Connect generators (Join Geometry has a multi-input socket —
    # linking multiple outputs to the same input socket is valid)
    for g_var, g_spec in placed_gens:
        g_out = _find_socket(g_spec, "out", "GEOMETRY") or "Mesh"
        dag.wire(g_var, g_out, join, join_geo_in)

    join_geo_out = _find_socket(join_spec, "out", "GEOMETRY") or "Geometry"
    dag.wire(join, join_geo_out, "gout", "Geometry")


def _build_curve_to_mesh(dag, nodes, context):
    """Curve to Mesh — sweep a profile along a path."""
    ctm_spec = nodes.get("GeometryNodeCurveToMesh", {})

    # Profile curve source
    profile_src = None
    for nid in ("GeometryNodeCurvePrimitiveCircle",):
        if nid in nodes:
            profile_src = (nid, nodes[nid])
            break

    profile = dag.add(
        profile_src[0] if profile_src else "GeometryNodeCurvePrimitiveCircle",
        profile_src[1].get("name", "Curve Circle") if profile_src else "Curve Circle",
        col=1, row=1,
    )
    if not profile_src:
        dag.set_default(profile, "Radius", 0.1)

    # Curve to Mesh
    ctm = dag.add("GeometryNodeCurveToMesh", "Curve to Mesh", col=2, row=0)

    # Path curve from input geometry
    ctm_ins = [s["name"] for s in ctm_spec.get("inputs", []) if s["type"] == "GEOMETRY"]
    # Typically: "Curve" and "Profile Curve"
    if len(ctm_ins) >= 2:
        dag.wire("gin", "Geometry", ctm, ctm_ins[0])  # path
        profile_out = _find_socket(
            nodes.get(profile_src[0], {}) if profile_src else {}, "out", "GEOMETRY"
        ) or "Curve"
        dag.wire(profile, profile_out, ctm, ctm_ins[1])  # profile
    elif ctm_ins:
        dag.wire("gin", "Geometry", ctm, ctm_ins[0])

    ctm_out = _find_socket(ctm_spec, "out", "GEOMETRY") or "Mesh"
    dag.wire(ctm, ctm_out, "gout", "Geometry")


# ── Idiom dispatch table ─────────────────────────────────────────────

_IDIOM_BUILDERS = {
    "scatter_instances": _build_scatter_instances,
    "boolean_op": _build_boolean_op,
    "join_geometry": _build_join_geometry,
    "curve_to_mesh": _build_curve_to_mesh,
}


# ── Linear fallback (for simple single-stream processing) ────────────

def _build_linear_chain(dag, nodes, context):
    """Fallback: chain processors in sequence with field side-inputs."""
    processors = [(nid, spec) for nid, spec in nodes.items()
                  if spec.get("role") == "processor"
                  and spec.get("observed_behavior") in ("MODIFIED", "PASSTHROUGH", "TYPE_CONVERTED")]

    generators = [(nid, spec) for nid, spec in nodes.items()
                  if spec.get("role") == "generator"]

    fields = [(nid, spec) for nid, spec in nodes.items()
              if spec.get("role") == "field"]

    chain = processors if processors else generators

    if not chain:
        chain = [("GeometryNodeSubdivideMesh", {
            "name": "Subdivide Mesh",
            "inputs": [{"name": "Mesh", "type": "GEOMETRY"}, {"name": "Level", "type": "INT"}],
            "outputs": [{"name": "Mesh", "type": "GEOMETRY"}],
        })]

    prev_geo = ("gin", "Geometry")
    field_row = 1  # Place field nodes below the main chain

    for col, (nid, spec) in enumerate(chain[:8]):
        name = spec.get("name", nid)
        var = dag.add(nid, name, col=col + 1, row=0)

        geo_in = _find_socket(spec, "in", "GEOMETRY")
        geo_out = _find_socket(spec, "out", "GEOMETRY")

        # Connect geometry stream
        if geo_in and prev_geo:
            dag.wire(prev_geo[0], prev_geo[1], var, geo_in)
        if geo_out:
            prev_geo = (var, geo_out)

        # Attach relevant field nodes as side-inputs
        non_geo_inputs = [s for s in spec.get("inputs", []) if s["type"] != "GEOMETRY"]
        for field_nid, field_spec in fields:
            field_outputs = field_spec.get("outputs", [])
            for f_out in field_outputs:
                for ng_in in non_geo_inputs:
                    if _types_compatible(f_out["type"], ng_in["type"]):
                        f_var = dag.add(field_nid, field_spec.get("name", field_nid),
                                        col=col + 1, row=field_row)
                        dag.wire(f_var, f_out["name"], var, ng_in["name"])
                        field_row += 1
                        break  # Only one field per input
                else:
                    continue
                break  # Move to next field node

    # Final output
    if prev_geo:
        dag.wire(prev_geo[0], prev_geo[1], "gout", "Geometry")


def _types_compatible(out_type, in_type):
    """Check if two socket types can connect (based on Blender's implicit conversions)."""
    if out_type == in_type:
        return True
    numeric = {"BOOLEAN", "INT", "VALUE", "FLOAT", "RGBA", "VECTOR"}
    if out_type in numeric and in_type in numeric:
        return True
    return False


# ── Main compositional entry point ───────────────────────────────────

def generate_compositional(context, description, kb):
    """Generate a script by composing nodes into a DAG.

    Strategy:
      1. Check matched nodes against known multi-node idioms
      2. If an idiom matches, use its specialised builder (handles branching)
      3. Otherwise, fall back to linear chain with field side-inputs
    """
    nodes = context["matched_nodes"]
    matched_ids = set(nodes.keys())

    dag = _DAGBuilder(description)

    # Try idioms (first match wins)
    used_idiom = None
    for idiom in IDIOMS:
        if idiom["trigger_nodes"].issubset(matched_ids):
            builder_fn = _IDIOM_BUILDERS[idiom["name"]]
            builder_fn(dag, nodes, context)
            used_idiom = idiom["name"]
            break

    if not used_idiom:
        _build_linear_chain(dag, nodes, context)

    return dag.emit()


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
