"""
Node Domain Classification
===========================
Categorizes all discovered geometry nodes by functional domain and purpose.
Uses name prefixes, socket types, and heuristics to classify.

Does NOT require Blender - runs on the node_catalog.json output.

Usage:
    python discovery/classify_nodes.py

Output:
    discovery/node_classification.json
"""

import json
import os
import sys
from datetime import datetime


def load_catalog(script_dir):
    path = os.path.join(script_dir, "node_catalog.json")
    if not os.path.exists(path):
        print(f"ERROR: {path} not found. Run discover_nodes.py first.")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────
# Classification rules - ordered by specificity (most specific first)
# ──────────────────────────────────────────────────────────────────────

# Prefix-based domain detection
PREFIX_RULES = [
    # Mesh operations
    ("GeometryNodeMesh",             "mesh",        "primitive"),
    ("GeometryNodeSubdivide",        "mesh",        "operation"),
    ("GeometryNodeDualMesh",         "mesh",        "operation"),
    ("GeometryNodeFlipFaces",        "mesh",        "operation"),
    ("GeometryNodeTriangulate",      "mesh",        "operation"),
    ("GeometryNodeExtrudeMesh",      "mesh",        "operation"),
    ("GeometryNodeSplitEdges",       "mesh",        "operation"),
    ("GeometryNodeEdgePaths",        "mesh",        "query"),
    ("GeometryNodeMeshBoolean",      "mesh",        "operation"),
    ("GeometryNodeMeshToCurve",      "mesh",        "conversion"),
    ("GeometryNodeMeshToPoints",     "mesh",        "conversion"),
    ("GeometryNodeMeshToVolume",     "mesh",        "conversion"),
    ("GeometryNodeMeshToSDFVolume",  "mesh",        "conversion"),

    # Curve operations
    ("GeometryNodeCurvePrimitive",   "curve",       "primitive"),
    ("GeometryNodeCurveArc",         "curve",       "primitive"),
    ("GeometryNodeCurveSpiral",      "curve",       "primitive"),
    ("GeometryNodeCurveStar",        "curve",       "primitive"),
    ("GeometryNodeCurve",            "curve",       "operation"),
    ("GeometryNodeFillCurve",        "curve",       "operation"),
    ("GeometryNodeFilletCurve",      "curve",       "operation"),
    ("GeometryNodeTrimCurve",        "curve",       "operation"),
    ("GeometryNodeReverseCurve",     "curve",       "operation"),
    ("GeometryNodeResampleCurve",    "curve",       "operation"),
    ("GeometryNodeSubdivideCurve",   "curve",       "operation"),
    ("GeometryNodeDeformCurvesOnSurface", "curve",  "operation"),
    ("GeometryNodeSampleCurve",      "curve",       "query"),
    ("GeometryNodeCurveToMesh",      "curve",       "conversion"),
    ("GeometryNodeCurveToPoints",    "curve",       "conversion"),

    # Point cloud
    ("GeometryNodeDistributePointsOnFaces", "pointcloud", "generation"),
    ("GeometryNodeDistributePointsInVolume", "pointcloud", "generation"),
    ("GeometryNodePoints",           "pointcloud",  "primitive"),
    ("GeometryNodePointsToVertices", "pointcloud",  "conversion"),
    ("GeometryNodePointsToVolume",   "pointcloud",  "conversion"),
    ("GeometryNodePointsToCurves",   "pointcloud",  "conversion"),

    # Volume
    ("GeometryNodeVolume",           "volume",      "primitive"),
    ("GeometryNodeSDFVolume",        "volume",      "primitive"),

    # Instances
    ("GeometryNodeInstance",         "instance",    "operation"),
    ("GeometryNodeRealizeInstances", "instance",    "operation"),
    ("GeometryNodeRotateInstances",  "instance",    "operation"),
    ("GeometryNodeScaleInstances",   "instance",    "operation"),
    ("GeometryNodeTranslateInstances","instance",   "operation"),

    # Grease Pencil
    ("GeometryNodeSetGrease",        "greasepencil","operation"),
    ("GeometryNodeInputGrease",      "greasepencil","input"),

    # Import nodes
    ("GeometryNodeImport",           "io",          "import"),

    # Camera / Image
    ("GeometryNodeCameraInfo",       "input",       "scene"),
    ("GeometryNodeImageTexture",     "input",       "texture"),

    # Bundle / Closure (internal plumbing for node groups)
    ("GeometryNodeCombineBundle",    "utility",     "bundle"),
    ("GeometryNodeSeparateBundle",   "utility",     "bundle"),
    ("GeometryNodeClosureInput",     "utility",     "closure"),
    ("GeometryNodeClosureOutput",    "utility",     "closure"),
    ("GeometryNodeEvaluateClosure",  "utility",     "closure"),

    # Simulation / Repeat zones
    ("GeometryNodeSimulation",       "simulation",  "zone"),
    ("GeometryNodeRepeat",           "repeat",      "zone"),
    ("GeometryNodeBake",             "bake",        "zone"),
    ("GeometryNodeForeachElement",   "foreach",     "zone"),
    ("GeometryNodeForeachGeometryElement", "foreach","zone"),

    # Gizmo
    ("GeometryNodeGizmo",            "gizmo",       "ui"),

    # Material
    ("GeometryNodeReplaceMaterial",  "material",    "operation"),
    ("GeometryNodeInputMaterial",    "material",    "input"),
    ("GeometryNodeSetMaterial",      "material",    "operation"),
    ("GeometryNodeMaterialSelection","material",    "query"),

    # UV / Texture
    ("GeometryNodeUVPack",           "uv",          "operation"),
    ("GeometryNodeUVUnwrap",         "uv",          "operation"),

    # Shader math utilities (used in geonodes too)
    ("ShaderNodeMath",               "math",        "operation"),
    ("ShaderNodeVectorMath",         "math",        "vector_operation"),
    ("ShaderNodeMapRange",           "math",        "mapping"),
    ("ShaderNodeClamp",              "math",        "mapping"),
    ("ShaderNodeMix",                "math",        "mixing"),
    ("ShaderNodeMixRGB",             "math",        "mixing"),
    ("ShaderNodeValToRGB",           "math",        "color_ramp"),
    ("ShaderNodeRGBCurve",           "math",        "curve_mapping"),
    ("ShaderNodeSeparateXYZ",        "math",        "decompose"),
    ("ShaderNodeCombineXYZ",         "math",        "compose"),
    ("ShaderNodeSeparateColor",      "math",        "decompose"),
    ("ShaderNodeCombineColor",       "math",        "compose"),

    # Function nodes
    ("FunctionNodeRotation",         "math",        "rotation"),
    ("FunctionNodeAxes",             "math",        "rotation"),
    ("FunctionNodeQuaternion",       "math",        "rotation"),
    ("FunctionNodeBoolean",          "math",        "logic"),
    ("FunctionNodeCompare",          "math",        "comparison"),
    ("FunctionNodeRandom",           "math",        "random"),
    ("FunctionNodeInput",            "input",       "constant"),
    ("FunctionNodeAlign",            "math",        "rotation"),
    ("FunctionNodeSlice",            "utility",     "string"),
    ("FunctionNodeReplace",          "utility",     "string"),
    ("FunctionNodeString",           "utility",     "string"),
]

# Name-based heuristics for nodes not caught by prefixes
NAME_KEYWORDS = {
    # Geometry-wide operations
    "Transform":           ("geometry",    "transform"),
    "Delete Geometry":     ("geometry",    "operation"),
    "Separate Geometry":   ("geometry",    "operation"),
    "Join Geometry":       ("geometry",    "operation"),
    "Merge by Distance":   ("geometry",    "operation"),
    "Duplicate Elements":  ("geometry",    "operation"),
    "Sort Elements":       ("geometry",    "operation"),
    "Convex Hull":         ("geometry",    "operation"),
    "Bounding Box":        ("geometry",    "query"),
    "Geometry Proximity":  ("geometry",    "query"),
    "Raycast":             ("geometry",    "query"),
    "Geometry to Instance":("geometry",    "conversion"),
    "Set ID":              ("attribute",   "operation"),
    "Set Position":        ("attribute",   "operation"),
    "Store Named Attribute": ("attribute", "operation"),
    "Remove Named Attribute": ("attribute","operation"),
    "Named Attribute":     ("attribute",   "input"),
    "Capture Attribute":   ("attribute",   "operation"),
    "Blur Attribute":      ("attribute",   "operation"),

    # Input nodes (field generators)
    "Index":               ("input",       "field"),
    "Position":            ("input",       "field"),
    "Normal":              ("input",       "field"),
    "ID":                  ("input",       "field"),
    "Is Viewport":         ("input",       "scene"),
    "Scene Time":          ("input",       "scene"),
    "Self Object":         ("input",       "scene"),
    "Collection Info":     ("input",       "scene"),
    "Object Info":         ("input",       "scene"),
    "Image Info":          ("input",       "scene"),
    "Is Face Planar":      ("input",       "mesh_field"),
    "Edge Angle":          ("input",       "mesh_field"),
    "Edge Vertices":       ("input",       "mesh_field"),
    "Face Area":           ("input",       "mesh_field"),
    "Face Neighbors":      ("input",       "mesh_field"),
    "Mesh Island":         ("input",       "mesh_field"),
    "Vertex Neighbors":    ("input",       "mesh_field"),
    "Shortest Edge Paths": ("input",       "mesh_field"),
    "Curve Tangent":       ("input",       "curve_field"),
    "Curve Tilt":          ("input",       "curve_field"),
    "Spline Length":       ("input",       "curve_field"),
    "Spline Parameter":    ("input",       "curve_field"),
    "Spline Resolution":   ("input",       "curve_field"),
    "Handle Positions":    ("input",       "curve_field"),
    "Handle Type Selection":("input",      "curve_field"),
    "Endpoint Selection":  ("input",       "curve_field"),

    # Accumulate / Evaluate / Sample
    "Accumulate Field":    ("field",       "accumulate"),
    "Evaluate at Index":   ("field",       "evaluate"),
    "Evaluate on Domain":  ("field",       "evaluate"),
    "Sample Index":        ("field",       "sample"),
    "Sample Nearest":      ("field",       "sample"),
    "Sample Nearest Surface": ("field",    "sample"),
    "Sample UV Surface":   ("field",       "sample"),

    # Selection
    "Selection":           ("selection",   "utility"),

    # Viewer
    "Viewer":              ("debug",       "output"),

    # Switch / Menu / Index Switch
    "Switch":              ("utility",     "flow_control"),
    "Menu Switch":         ("utility",     "flow_control"),
    "Index Switch":        ("utility",     "flow_control"),

    # Group
    "Group":               ("utility",     "group"),
}


def classify_node(type_id, node_info):
    """Classify a single node by domain and purpose."""
    name = node_info.get("name", "")

    # 1. Try prefix rules (most specific)
    for prefix, domain, purpose in PREFIX_RULES:
        if type_id.startswith(prefix):
            return domain, purpose

    # 2. Try name keyword matching
    for keyword, (domain, purpose) in NAME_KEYWORDS.items():
        if keyword.lower() in name.lower():
            return domain, purpose

    # 3. Fallback heuristics based on socket types
    inputs = node_info.get("inputs", [])
    outputs = node_info.get("outputs", [])
    in_types = {s["type"] for s in inputs}
    out_types = {s["type"] for s in outputs}

    has_geo_in = "GEOMETRY" in in_types
    has_geo_out = "GEOMETRY" in out_types

    # Set* nodes that modify geometry
    if name.startswith("Set ") and has_geo_in and has_geo_out:
        return "attribute", "operation"

    # Input* nodes that produce field values
    if type_id.startswith("GeometryNodeInput"):
        return "input", "field"

    # Purely numeric / math nodes
    if not has_geo_in and not has_geo_out:
        all_types = in_types | out_types
        numeric_types = {"VALUE", "INT", "BOOLEAN", "VECTOR", "RGBA", "ROTATION", "MATRIX"}
        if all_types and all_types <= numeric_types | {"STRING"}:
            return "math", "operation"

    # Geometry passthrough (geo in + geo out)
    if has_geo_in and has_geo_out:
        return "geometry", "operation"

    # Geometry generator (geo out only)
    if has_geo_out and not has_geo_in:
        return "geometry", "generation"

    # Geometry consumer (geo in only)
    if has_geo_in and not has_geo_out:
        return "geometry", "query"

    return "uncategorized", "unknown"


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    catalog = load_catalog(script_dir)

    print("=" * 60)
    print("Node Domain Classification")
    print("=" * 60)
    print(f"Classifying {len(catalog['nodes'])} nodes")
    print()

    classification = {
        "blender_version": catalog["blender_version"],
        "classification_date": datetime.now().isoformat(),
        "total_nodes": len(catalog["nodes"]),
        "domains": {},
        "nodes": {},
    }

    domain_counts = {}
    purpose_counts = {}

    for type_id, node_info in sorted(catalog["nodes"].items()):
        domain, purpose = classify_node(type_id, node_info)

        classification["nodes"][type_id] = {
            "name": node_info["name"],
            "domain": domain,
            "purpose": purpose,
        }

        # Track stats
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        purpose_counts[purpose] = purpose_counts.get(purpose, 0) + 1

        # Build domain grouping
        if domain not in classification["domains"]:
            classification["domains"][domain] = {
                "description": "",
                "node_count": 0,
                "by_purpose": {},
            }
        classification["domains"][domain]["node_count"] += 1

        if purpose not in classification["domains"][domain]["by_purpose"]:
            classification["domains"][domain]["by_purpose"][purpose] = []
        classification["domains"][domain]["by_purpose"][purpose].append({
            "type_id": type_id,
            "name": node_info["name"],
        })

    # Add domain descriptions
    domain_descriptions = {
        "mesh":         "Mesh geometry creation and manipulation",
        "curve":        "Curve/spline creation and manipulation",
        "pointcloud":   "Point cloud generation and conversion",
        "volume":       "Volume/SDF/OpenVDB operations",
        "instance":     "Geometry instancing and instance manipulation",
        "greasepencil": "Grease pencil stroke operations",
        "geometry":     "General geometry operations (transform, join, delete, etc.)",
        "attribute":    "Named attribute and per-element data operations",
        "field":        "Field evaluation, sampling, and accumulation",
        "input":        "Input values, field generators, scene info",
        "selection":    "Element selection utilities",
        "material":     "Material assignment and queries",
        "uv":           "UV unwrapping and packing",
        "math":         "Math, vector, color, and rotation operations",
        "utility":      "Flow control, string ops, general utilities",
        "io":           "File import nodes",
        "simulation":   "Simulation zone nodes",
        "repeat":       "Repeat zone nodes",
        "bake":         "Bake zone nodes",
        "foreach":      "For-each element zone nodes",
        "gizmo":        "Interactive gizmo nodes",
        "debug":        "Debugging and visualization",
        "uncategorized": "Nodes not yet classified",
    }
    for domain, desc in domain_descriptions.items():
        if domain in classification["domains"]:
            classification["domains"][domain]["description"] = desc

    # Print summary
    print("Domain breakdown:")
    print("-" * 40)
    for domain in sorted(domain_counts, key=lambda d: -domain_counts[d]):
        count = domain_counts[domain]
        desc = domain_descriptions.get(domain, "")
        print(f"  {domain:<16} {count:>3} nodes  {desc}")

    print()
    print(f"Uncategorized: {domain_counts.get('uncategorized', 0)} nodes")

    # Show uncategorized nodes for debugging
    if "uncategorized" in classification["domains"]:
        print("  Uncategorized nodes:")
        for purpose_group in classification["domains"]["uncategorized"]["by_purpose"].values():
            for node in purpose_group:
                print(f"    - {node['type_id']}: {node['name']}")

    # Write output
    output_path = os.path.join(script_dir, "node_classification.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(classification, f, indent=2, ensure_ascii=False)

    print()
    print(f"Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
