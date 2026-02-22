#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { readFileSync, existsSync, statSync } from "node:fs";
import { join } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PROJECT_DIR = process.env.PROJECT_DIR || "";
const BLENDER_PATH = process.env.BLENDER_PATH || "";

const DATA_PATHS = {
  kb: "knowledge/blender_geonodes_kb.json",
  nodeCatalog: "discovery/node_catalog.json",
  connectionMatrix: "discovery/connection_matrix.json",
  nodeClassification: "discovery/node_classification.json",
  patternCatalog: "patterns/pattern_catalog.json",
};

// ---------------------------------------------------------------------------
// Data loading helpers
// ---------------------------------------------------------------------------

/** @type {Map<string, {data: any, mtime: number}>} */
const dataCache = new Map();

function resolveDataPath(relPath) {
  if (!PROJECT_DIR) return null;
  return join(PROJECT_DIR, relPath);
}

function loadJsonFile(relPath) {
  const fullPath = resolveDataPath(relPath);
  if (!fullPath || !existsSync(fullPath)) return null;

  try {
    let mtime = 0;
    try { mtime = statSync(fullPath).mtimeMs; } catch { /* ignore */ }

    const cached = dataCache.get(relPath);
    if (cached && cached.mtime === mtime) return cached.data;

    const raw = readFileSync(fullPath, "utf-8");
    const data = JSON.parse(raw);
    dataCache.set(relPath, { data, mtime });
    return data;
  } catch (err) {
    log(`Failed to load ${relPath}: ${err.message}`);
    return null;
  }
}

function getKb() {
  return loadJsonFile(DATA_PATHS.kb);
}

function getNodeCatalog() {
  return loadJsonFile(DATA_PATHS.nodeCatalog);
}

function getConnectionMatrix() {
  return loadJsonFile(DATA_PATHS.connectionMatrix);
}

function getNodeClassification() {
  return loadJsonFile(DATA_PATHS.nodeClassification);
}

function getPatternCatalog() {
  return loadJsonFile(DATA_PATHS.patternCatalog);
}

// ---------------------------------------------------------------------------
// Logging (stderr so it doesn't interfere with stdio transport)
// ---------------------------------------------------------------------------

function log(msg) {
  process.stderr.write(`[blender-geonodes-ai] ${msg}\n`);
}

// ---------------------------------------------------------------------------
// Query logic (ported from knowledge/query.py & generator/context_builder.py)
// ---------------------------------------------------------------------------

// Term mapping for natural language → node search terms
const TERM_MAP = {
  scatter: ["distribute", "instance", "points"],
  distribute: ["distribute", "points"],
  deform: ["set position", "noise", "displacement"],
  smooth: ["smooth", "subdivision", "shade smooth"],
  subdivide: ["subdivide", "subdivision"],
  extrude: ["extrude"],
  bevel: ["fillet"],
  boolean: ["boolean", "intersect", "union", "difference"],
  merge: ["merge", "join"],
  join: ["merge", "join"],
  duplicate: ["duplicate", "instance"],
  array: ["instance", "grid", "line"],
  mirror: ["transform", "scale", "flip"],
  noise: ["noise", "random"],
  random: ["random", "noise"],
  color: ["color", "rgb", "material"],
  material: ["material", "set material"],
  animate: ["simulation", "frame", "scene time"],
  text: ["string to curves", "string"],
  curve: ["curve", "spline", "bezier"],
  mesh: ["mesh", "vertices", "faces", "edges"],
  volume: ["volume", "points to volume"],
  pointcloud: ["points", "point cloud"],
  uv: ["uv", "texture"],
  transform: ["transform", "translate", "rotate", "scale"],
  move: ["set position", "translate", "transform"],
  rotate: ["rotate", "rotation"],
  scale: ["scale", "transform"],
  delete: ["delete", "geometry"],
  separate: ["separate", "geometry"],
  attribute: ["attribute", "named", "store"],
  group: ["group", "input", "output"],
  math: ["math", "value", "operation"],
  compare: ["compare", "equal", "greater", "less"],
  switch: ["switch", "index"],
  raycast: ["raycast"],
  proximity: ["proximity", "nearest"],
  sample: ["sample", "transfer"],
  capture: ["capture", "attribute"],
  realize: ["realize", "instances"],
  triangulate: ["triangulate"],
  convex: ["convex hull"],
  fill: ["fill curve"],
  offset: ["offset"],
  trim: ["trim", "curve"],
  resample: ["resample", "curve"],
};

function extractSearchTerms(description) {
  const lower = description.toLowerCase();
  const terms = new Set();

  // Direct words from description
  const words = lower.split(/\s+/);
  for (const w of words) {
    if (w.length > 2) terms.add(w);
  }

  // Expand via term map
  for (const [key, expansions] of Object.entries(TERM_MAP)) {
    if (lower.includes(key)) {
      for (const exp of expansions) terms.add(exp);
    }
  }

  return [...terms];
}

function scoreNode(node, terms) {
  let score = 0;
  const name = (node.name || "").toLowerCase();
  const typeId = (node.type_id || "").toLowerCase();
  const domain = (node.domain || "").toLowerCase();
  const purpose = (node.purpose || "").toLowerCase();
  const desc = (node.bl_description || "").toLowerCase();

  for (const term of terms) {
    if (name.includes(term)) score += 3;
    if (typeId.includes(term)) score += 2;
    if (domain.includes(term)) score += 1;
    if (purpose.includes(term)) score += 1;
    if (desc.includes(term)) score += 1;
  }

  return score;
}

function searchNodes(query, domain, role, maxResults = 15) {
  const kb = getKb();
  const catalog = getNodeCatalog();

  // Prefer KB, fall back to raw catalog
  const nodeSource = kb?.nodes || catalog?.nodes;
  if (!nodeSource) {
    return { error: "No node data available. Run discovery first." };
  }

  const terms = extractSearchTerms(query);
  const results = [];

  for (const [nodeId, node] of Object.entries(nodeSource)) {
    // Apply filters
    if (domain && (node.domain || "").toLowerCase() !== domain.toLowerCase()) continue;
    if (role && (node.role || "").toLowerCase() !== role.toLowerCase()) continue;

    const s = scoreNode(node, terms);
    if (s > 0) {
      results.push({
        type_id: nodeId,
        name: node.name || node.bl_label || nodeId,
        domain: node.domain || "unknown",
        role: node.role || "unknown",
        purpose: node.purpose || "",
        score: s,
        input_count: (node.inputs || []).length,
        output_count: (node.outputs || []).length,
      });
    }
  }

  results.sort((a, b) => b.score - a.score);
  return results.slice(0, maxResults);
}

function getNodeDetails(nodeId) {
  const kb = getKb();
  const catalog = getNodeCatalog();

  // Try exact match first
  let node = kb?.nodes?.[nodeId] || catalog?.nodes?.[nodeId];

  // Try fuzzy match
  if (!node) {
    const lower = nodeId.toLowerCase();
    const nodeSource = kb?.nodes || catalog?.nodes || {};
    for (const [id, n] of Object.entries(nodeSource)) {
      if (
        id.toLowerCase() === lower ||
        (n.name || "").toLowerCase() === lower ||
        id.toLowerCase().includes(lower) ||
        (n.name || "").toLowerCase().includes(lower)
      ) {
        node = n;
        nodeId = id;
        break;
      }
    }
  }

  if (!node) {
    // Suggest similar nodes
    const nodeSource = kb?.nodes || catalog?.nodes || {};
    const suggestions = [];
    const lower = nodeId.toLowerCase();
    for (const [id, n] of Object.entries(nodeSource)) {
      if (id.toLowerCase().includes(lower) || (n.name || "").toLowerCase().includes(lower)) {
        suggestions.push(id);
      }
    }
    return {
      error: `Node "${nodeId}" not found.`,
      suggestions: suggestions.slice(0, 10),
    };
  }

  return { type_id: nodeId, ...node };
}

function checkConnection(fromType, toType) {
  const kb = getKb();
  const matrix = getConnectionMatrix();

  // Check KB connections first
  if (kb?.connections) {
    const conns = [...(kb.connections.valid_connections || []), ...(kb.connections.invalid_connections || [])];
    for (const conn of conns) {
      if (
        conn.from?.toUpperCase() === fromType.toUpperCase() &&
        conn.to?.toUpperCase() === toType.toUpperCase()
      ) {
        return {
          from_type: fromType.toUpperCase(),
          to_type: toType.toUpperCase(),
          valid: conn.valid !== false,
          connection_type: conn.valid !== false ? (conn.from === conn.to ? "DIRECT" : "CONVERT") : "INVALID",
          details: conn,
        };
      }
    }

    // Check type groups for implicit compatibility
    const typeGroups = kb.connections.type_groups || {};
    const fromUpper = fromType.toUpperCase();
    const toUpper = toType.toUpperCase();

    for (const [groupName, group] of Object.entries(typeGroups)) {
      const types = (group.types || []).map((t) => t.toUpperCase());
      if (types.includes(fromUpper) && types.includes(toUpper)) {
        return {
          from_type: fromUpper,
          to_type: toUpper,
          valid: true,
          connection_type: fromUpper === toUpper ? "DIRECT" : "CONVERT",
          group: groupName,
          note: group.note || `Both types belong to the ${groupName} group`,
        };
      }
    }
  }

  // Check raw connection matrix
  if (matrix?.quick_reference) {
    const key = `${fromType.toUpperCase()} -> ${toType.toUpperCase()}`;
    const result = matrix.quick_reference[key];
    if (result) {
      return {
        from_type: fromType.toUpperCase(),
        to_type: toType.toUpperCase(),
        valid: result !== "INVALID",
        connection_type: result,
      };
    }
  }

  // Same type is always valid
  if (fromType.toUpperCase() === toType.toUpperCase()) {
    return {
      from_type: fromType.toUpperCase(),
      to_type: toType.toUpperCase(),
      valid: true,
      connection_type: "DIRECT",
    };
  }

  return {
    from_type: fromType.toUpperCase(),
    to_type: toType.toUpperCase(),
    valid: false,
    connection_type: "UNKNOWN",
    note: "Connection not found in knowledge base. Run connection discovery to test.",
  };
}

function listPatterns(domain) {
  const kb = getKb();
  const patternCatalog = getPatternCatalog();
  const patterns = kb?.patterns || patternCatalog?.patterns || [];

  if (!patterns.length) {
    return { error: "No patterns available. Run pattern verification first." };
  }

  let filtered = patterns;
  if (domain) {
    const lower = domain.toLowerCase();
    filtered = patterns.filter((p) => {
      const desc = (p.description || "").toLowerCase();
      const name = (p.name || "").toLowerCase();
      const nodesUsed = (p.nodes_used || []).map((n) => (n.type || "").toLowerCase());
      return (
        desc.includes(lower) ||
        name.includes(lower) ||
        nodesUsed.some((n) => n.includes(lower))
      );
    });
  }

  return filtered.map((p, i) => ({
    index: i,
    name: p.name || `Pattern ${i + 1}`,
    description: p.description || "",
    node_count: (p.nodes_used || []).length,
    link_count: (p.links || []).length,
    blender_version: p.blender_version || "unknown",
  }));
}

function getPattern(patternName) {
  const kb = getKb();
  const patternCatalog = getPatternCatalog();
  const patterns = kb?.patterns || patternCatalog?.patterns || [];

  if (!patterns.length) {
    return { error: "No patterns available." };
  }

  const lower = patternName.toLowerCase();

  // Try exact name match
  let pattern = patterns.find((p) => (p.name || "").toLowerCase() === lower);

  // Try partial match
  if (!pattern) {
    pattern = patterns.find((p) => (p.name || "").toLowerCase().includes(lower));
  }

  // Try index
  if (!pattern) {
    const idx = parseInt(patternName, 10);
    if (!isNaN(idx) && idx >= 0 && idx < patterns.length) {
      pattern = patterns[idx];
    }
  }

  if (!pattern) {
    return {
      error: `Pattern "${patternName}" not found.`,
      available: patterns.map((p) => p.name || "unnamed"),
    };
  }

  return pattern;
}

function getKbStats() {
  const kb = getKb();
  const catalog = getNodeCatalog();
  const classification = getNodeClassification();
  const matrix = getConnectionMatrix();
  const patternCatalog = getPatternCatalog();

  const stats = {
    project_directory: PROJECT_DIR || "(not configured)",
    blender_path: BLENDER_PATH || "(not configured)",
    data_sources: {},
  };

  // KB stats
  if (kb) {
    stats.knowledge_base = {
      available: true,
      metadata: kb.metadata || {},
      stats: kb.stats || {},
      domains: Object.keys(kb.lookups?.nodes_by_domain || {}),
      roles: Object.keys(kb.lookups?.nodes_by_role || {}),
    };
    stats.data_sources.kb = "loaded";
  } else {
    stats.knowledge_base = { available: false };
    stats.data_sources.kb = "missing";
  }

  // Catalog stats
  if (catalog) {
    stats.node_catalog = {
      available: true,
      blender_version: catalog.blender_version || "unknown",
      total_nodes: catalog.total_nodes_cataloged || Object.keys(catalog.nodes || {}).length,
      socket_types: catalog.socket_types_found || [],
      errors: catalog.total_errors || 0,
    };
    stats.data_sources.node_catalog = "loaded";
  } else {
    stats.node_catalog = { available: false };
    stats.data_sources.node_catalog = "missing";
  }

  // Classification stats
  if (classification) {
    stats.node_classification = {
      available: true,
      total_nodes: classification.total_nodes || 0,
      domains: Object.keys(classification.domains || {}),
    };
    stats.data_sources.node_classification = "loaded";
  } else {
    stats.node_classification = { available: false };
    stats.data_sources.node_classification = "missing";
  }

  // Connection matrix stats
  if (matrix) {
    stats.connection_matrix = {
      available: true,
      quick_reference_entries: Object.keys(matrix.quick_reference || {}).length,
    };
    stats.data_sources.connection_matrix = "loaded";
  } else {
    stats.connection_matrix = { available: false };
    stats.data_sources.connection_matrix = "missing";
  }

  // Pattern stats
  if (patternCatalog) {
    const patterns = patternCatalog.patterns || [];
    stats.pattern_catalog = {
      available: true,
      total_patterns: patterns.length,
      pattern_names: patterns.map((p) => p.name || "unnamed"),
    };
    stats.data_sources.pattern_catalog = "loaded";
  } else {
    stats.pattern_catalog = { available: false };
    stats.data_sources.pattern_catalog = "missing";
  }

  return stats;
}

// ---------------------------------------------------------------------------
// Script generation (simplified in-process version)
// ---------------------------------------------------------------------------

function generateScript(description, meshType = "cube") {
  const kb = getKb();
  if (!kb) {
    return {
      error: "Knowledge base not available. Run discovery and build_kb first.",
      hint: "Use the run_discovery tool with phase='build_kb' after running earlier phases.",
    };
  }

  // Build context (port of context_builder.py logic)
  const terms = extractSearchTerms(description);
  const matchedNodes = [];

  for (const [nodeId, node] of Object.entries(kb.nodes || {})) {
    const s = scoreNode(node, terms);
    if (s > 0) matchedNodes.push({ id: nodeId, node, score: s });
  }
  matchedNodes.sort((a, b) => b.score - a.score);
  const topNodes = matchedNodes.slice(0, 20);

  // Find matching patterns
  const matchedPatterns = [];
  for (const pattern of kb.patterns || []) {
    const pName = (pattern.name || "").toLowerCase();
    const pDesc = (pattern.description || "").toLowerCase();
    let pScore = 0;
    for (const term of terms) {
      if (pName.includes(term)) pScore += 3;
      if (pDesc.includes(term)) pScore += 2;
    }
    if (pScore > 0) matchedPatterns.push({ pattern, score: pScore });
  }
  matchedPatterns.sort((a, b) => b.score - a.score);

  // If we have a matching pattern, use pattern-based generation
  if (matchedPatterns.length > 0) {
    const bestPattern = matchedPatterns[0].pattern;
    return generateFromPattern(bestPattern, description, meshType);
  }

  // Compositional generation from matched nodes
  if (topNodes.length > 0) {
    return generateCompositional(topNodes, description, meshType, kb);
  }

  return {
    error: "Could not find relevant nodes for the given description.",
    search_terms: terms,
    hint: "Try being more specific, e.g., 'subdivide a mesh and smooth it' or 'scatter instances on a surface'.",
  };
}

function generateFromPattern(pattern, description, meshType) {
  const lines = [];
  lines.push("import bpy");
  lines.push("");
  lines.push(`# Generated from pattern: ${pattern.name || "unnamed"}`);
  lines.push(`# Description: ${description}`);
  lines.push(`# Based on verified pattern: ${pattern.description || ""}`);
  lines.push("");
  lines.push("def cleanup():");
  lines.push("    \"\"\"Remove existing geometry node modifiers and trees.\"\"\"");
  lines.push("    for obj in bpy.data.objects:");
  lines.push("        for mod in list(obj.modifiers):");
  lines.push("            if mod.type == 'NODES':");
  lines.push("                obj.modifiers.remove(mod)");
  lines.push("    for tree in list(bpy.data.node_groups):");
  lines.push("        if tree.type == 'GeometryNodeTree':");
  lines.push("            bpy.data.node_groups.remove(tree)");
  lines.push("");
  lines.push("def create_node_tree():");
  lines.push(`    tree = bpy.data.node_groups.new(name="${pattern.name || "GeneratedTree"}", type='GeometryNodeTree')`);

  lines.push("");
  lines.push("    # Create interface sockets");
  lines.push("    tree.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')");
  lines.push("    tree.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')");
  lines.push("");
  lines.push("    # Get input/output nodes");
  lines.push("    input_node = tree.nodes.get('Group Input')");
  lines.push("    output_node = tree.nodes.get('Group Output')");
  lines.push("    input_node.location = (-400, 0)");
  lines.push("    output_node.location = (400, 0)");
  lines.push("");

  // Add nodes from pattern
  const nodesUsed = pattern.nodes_used || [];
  for (let i = 0; i < nodesUsed.length; i++) {
    const n = nodesUsed[i];
    const varName = `node_${i}`;
    const xPos = -200 + i * 200;
    lines.push(`    # ${n.name || n.type}`);
    lines.push(`    ${varName} = tree.nodes.new(type='${n.type}')`);
    lines.push(`    ${varName}.location = (${xPos}, 0)`);

    // Set input defaults
    if (n.input_defaults) {
      for (const [inputName, value] of Object.entries(n.input_defaults)) {
        if (typeof value === "string") {
          lines.push(`    ${varName}.inputs['${inputName}'].default_value = '${value}'`);
        } else if (Array.isArray(value)) {
          lines.push(`    ${varName}.inputs['${inputName}'].default_value = (${value.join(", ")})`);
        } else {
          lines.push(`    ${varName}.inputs['${inputName}'].default_value = ${value}`);
        }
      }
    }

    // Set properties
    if (n.properties) {
      for (const [propName, value] of Object.entries(n.properties)) {
        if (typeof value === "string") {
          lines.push(`    ${varName}.${propName} = '${value}'`);
        } else {
          lines.push(`    ${varName}.${propName} = ${value}`);
        }
      }
    }
    lines.push("");
  }

  // Add links from pattern
  lines.push("    # Create links");
  const links = pattern.links || [];
  for (const link of links) {
    // Map node names to variables
    const fromIdx = nodesUsed.findIndex(
      (n) => n.name === link.from_node || n.type === link.from_node
    );
    const toIdx = nodesUsed.findIndex(
      (n) => n.name === link.to_node || n.type === link.to_node
    );

    let fromVar = fromIdx >= 0 ? `node_${fromIdx}` : null;
    let toVar = toIdx >= 0 ? `node_${toIdx}` : null;

    // Handle Group Input/Output
    if (link.from_node === "Group Input") fromVar = "input_node";
    if (link.to_node === "Group Output") toVar = "output_node";

    if (fromVar && toVar) {
      lines.push(
        `    tree.links.new(${fromVar}.outputs['${link.from_socket}'], ${toVar}.inputs['${link.to_socket}'])`
      );
    }
  }

  lines.push("");
  lines.push("    return tree");
  lines.push("");
  lines.push("def main():");
  lines.push("    cleanup()");
  lines.push("    tree = create_node_tree()");
  lines.push("");

  // Create test mesh
  const meshOps = {
    cube: "bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))",
    sphere: "bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 0))",
    plane: "bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))",
    cylinder: "bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=2, location=(0, 0, 0))",
    monkey: "bpy.ops.mesh.primitive_monkey_add(size=2, location=(0, 0, 0))",
    grid: "bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=2, location=(0, 0, 0))",
  };
  const meshOp = meshOps[meshType] || meshOps.cube;

  lines.push(`    # Create test mesh`);
  lines.push(`    ${meshOp}`);
  lines.push("    obj = bpy.context.active_object");
  lines.push("    obj.name = 'GeoNodes_Test'");
  lines.push("");
  lines.push("    # Apply geometry nodes modifier");
  lines.push("    mod = obj.modifiers.new(name='GeometryNodes', type='NODES')");
  lines.push("    mod.node_group = tree");
  lines.push("");
  lines.push("    print(f'Applied geometry nodes tree: {tree.name}')");
  lines.push("    print(f'  Nodes: {len(tree.nodes)}')");
  lines.push("    print(f'  Links: {len(tree.links)}')");
  lines.push("");
  lines.push("if __name__ == '__main__':");
  lines.push("    main()");

  return {
    script: lines.join("\n"),
    method: "pattern-based",
    pattern_name: pattern.name || "unnamed",
    pattern_description: pattern.description || "",
    nodes_used: nodesUsed.map((n) => n.type || n.name),
    mesh_type: meshType,
  };
}

function generateCompositional(topNodes, description, meshType, kb) {
  // Select the best nodes for a simple chain
  const generators = topNodes.filter(
    (n) => n.node.role === "generator" || (!n.node.has_geometry_input && n.node.has_geometry_output)
  );
  const processors = topNodes.filter(
    (n) => n.node.role === "processor" || (n.node.has_geometry_input && n.node.has_geometry_output)
  );

  // Build a simple chain: Input → processor(s) → Output
  const chain = processors.slice(0, 5); // Max 5 processors in chain

  const lines = [];
  lines.push("import bpy");
  lines.push("");
  lines.push(`# Generated compositionally for: ${description}`);
  lines.push(`# Matched ${topNodes.length} relevant nodes, using ${chain.length} in chain`);
  lines.push("");
  lines.push("def cleanup():");
  lines.push("    for obj in bpy.data.objects:");
  lines.push("        for mod in list(obj.modifiers):");
  lines.push("            if mod.type == 'NODES':");
  lines.push("                obj.modifiers.remove(mod)");
  lines.push("    for tree in list(bpy.data.node_groups):");
  lines.push("        if tree.type == 'GeometryNodeTree':");
  lines.push("            bpy.data.node_groups.remove(tree)");
  lines.push("");
  lines.push("def create_node_tree():");
  lines.push("    tree = bpy.data.node_groups.new(name='GeneratedTree', type='GeometryNodeTree')");
  lines.push("");
  lines.push("    # Interface");
  lines.push("    tree.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')");
  lines.push("    tree.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')");
  lines.push("");
  lines.push("    input_node = tree.nodes.get('Group Input')");
  lines.push("    output_node = tree.nodes.get('Group Output')");
  lines.push("    input_node.location = (-400, 0)");
  lines.push(`    output_node.location = (${200 + chain.length * 200}, 0)`);
  lines.push("");

  // Add chain nodes
  for (let i = 0; i < chain.length; i++) {
    const n = chain[i];
    const xPos = i * 200;
    lines.push(`    # ${n.node.name || n.id} (score: ${n.score})`);
    lines.push(`    node_${i} = tree.nodes.new(type='${n.id}')`);
    lines.push(`    node_${i}.location = (${xPos}, 0)`);
    lines.push("");
  }

  // Link chain: Input → node_0 → node_1 → ... → Output
  lines.push("    # Link chain");
  if (chain.length > 0) {
    // Input → first node
    const firstNode = chain[0].node;
    const firstGeoInput = (firstNode.inputs || []).find((s) => s.type === "GEOMETRY");
    if (firstGeoInput) {
      lines.push(
        `    tree.links.new(input_node.outputs['Geometry'], node_0.inputs['${firstGeoInput.name}'])`
      );
    }

    // Chain nodes together
    for (let i = 0; i < chain.length - 1; i++) {
      const currNode = chain[i].node;
      const nextNode = chain[i + 1].node;
      const geoOutput = (currNode.outputs || []).find((s) => s.type === "GEOMETRY");
      const geoInput = (nextNode.inputs || []).find((s) => s.type === "GEOMETRY");
      if (geoOutput && geoInput) {
        lines.push(
          `    tree.links.new(node_${i}.outputs['${geoOutput.name}'], node_${i + 1}.inputs['${geoInput.name}'])`
        );
      }
    }

    // Last node → Output
    const lastNode = chain[chain.length - 1].node;
    const lastGeoOutput = (lastNode.outputs || []).find((s) => s.type === "GEOMETRY");
    if (lastGeoOutput) {
      lines.push(
        `    tree.links.new(node_${chain.length - 1}.outputs['${lastGeoOutput.name}'], output_node.inputs['Geometry'])`
      );
    }
  } else {
    // Direct passthrough
    lines.push("    tree.links.new(input_node.outputs['Geometry'], output_node.inputs['Geometry'])");
  }

  lines.push("");
  lines.push("    return tree");
  lines.push("");
  lines.push("def main():");
  lines.push("    cleanup()");
  lines.push("    tree = create_node_tree()");
  lines.push("");

  const meshOps = {
    cube: "bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))",
    sphere: "bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 0))",
    plane: "bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))",
    cylinder: "bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=2, location=(0, 0, 0))",
    monkey: "bpy.ops.mesh.primitive_monkey_add(size=2, location=(0, 0, 0))",
    grid: "bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=2, location=(0, 0, 0))",
  };
  const meshOp = meshOps[meshType] || meshOps.cube;

  lines.push(`    ${meshOp}`);
  lines.push("    obj = bpy.context.active_object");
  lines.push("    obj.name = 'GeoNodes_Test'");
  lines.push("");
  lines.push("    mod = obj.modifiers.new(name='GeometryNodes', type='NODES')");
  lines.push("    mod.node_group = tree");
  lines.push("");
  lines.push("    print(f'Applied geometry nodes tree: {tree.name}')");
  lines.push("    print(f'  Nodes: {len(tree.nodes)}')");
  lines.push("    print(f'  Links: {len(tree.links)}')");
  lines.push("");
  lines.push("if __name__ == '__main__':");
  lines.push("    main()");

  return {
    script: lines.join("\n"),
    method: "compositional",
    description,
    nodes_in_chain: chain.map((n) => ({
      type_id: n.id,
      name: n.node.name,
      score: n.score,
    })),
    all_matched_nodes: topNodes.slice(0, 10).map((n) => ({
      type_id: n.id,
      name: n.node.name,
      score: n.score,
    })),
    mesh_type: meshType,
  };
}

// ---------------------------------------------------------------------------
// Discovery runner
// ---------------------------------------------------------------------------

const DISCOVERY_PHASES = {
  catalog: {
    script: "discovery/discover_nodes.py",
    description: "Enumerate all geometry node types from Blender",
    requiresBlender: true,
  },
  connections: {
    script: "discovery/test_connections.py",
    description: "Test socket type connection compatibility",
    requiresBlender: true,
  },
  classify: {
    script: "discovery/classify_nodes.py",
    description: "Classify nodes by domain and purpose",
    requiresBlender: false,
  },
  patterns: {
    script: "patterns/verify_patterns.py",
    description: "Verify all pattern recipes in Blender",
    requiresBlender: true,
  },
  build_kb: {
    script: "knowledge/build_kb.py",
    description: "Assemble the unified knowledge base from all sources",
    requiresBlender: false,
  },
};

async function runDiscovery(phase) {
  if (!PROJECT_DIR) {
    return { error: "Project directory not configured. Set it in extension settings." };
  }

  const phaseConfig = DISCOVERY_PHASES[phase];
  if (!phaseConfig) {
    return {
      error: `Unknown phase: "${phase}"`,
      available_phases: Object.keys(DISCOVERY_PHASES).map((k) => ({
        phase: k,
        description: DISCOVERY_PHASES[k].description,
        requires_blender: DISCOVERY_PHASES[k].requiresBlender,
      })),
    };
  }

  const scriptPath = join(PROJECT_DIR, phaseConfig.script);
  if (!existsSync(scriptPath)) {
    return { error: `Script not found: ${scriptPath}` };
  }

  if (phaseConfig.requiresBlender) {
    if (!BLENDER_PATH) {
      return {
        error: "Blender path not configured. Set it in extension settings.",
        hint: "This phase requires running scripts inside Blender.",
      };
    }
    if (!existsSync(BLENDER_PATH)) {
      return { error: `Blender executable not found at: ${BLENDER_PATH}` };
    }
  }

  try {
    let result;
    const TIMEOUT_MS = 300_000; // 5 minutes

    if (phaseConfig.requiresBlender) {
      result = await execFileAsync(
        BLENDER_PATH,
        ["--background", "--python", scriptPath],
        { cwd: PROJECT_DIR, timeout: TIMEOUT_MS }
      );
    } else {
      result = await execFileAsync("python", [scriptPath], {
        cwd: PROJECT_DIR,
        timeout: TIMEOUT_MS,
      });
    }

    // Clear cache so next queries pick up fresh data
    dataCache.clear();

    return {
      phase,
      description: phaseConfig.description,
      status: "completed",
      stdout: (result.stdout || "").slice(-2000), // Last 2KB of output
      stderr: (result.stderr || "").slice(-1000),
    };
  } catch (err) {
    return {
      phase,
      description: phaseConfig.description,
      status: "error",
      error: err.message,
      stdout: (err.stdout || "").slice(-2000),
      stderr: (err.stderr || "").slice(-1000),
    };
  }
}

// ---------------------------------------------------------------------------
// Tool definitions
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    name: "search_nodes",
    description:
      "Search the Blender geometry node catalog by keyword, domain, or role. Returns matching nodes ranked by relevance.",
    inputSchema: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description:
            "Search query — natural language or node name (e.g., 'subdivide mesh', 'scatter points', 'math')",
        },
        domain: {
          type: "string",
          description:
            "Filter by domain: mesh, curve, geometry, math, material, instance, pointcloud, volume, utility, etc.",
        },
        role: {
          type: "string",
          description:
            "Filter by role: generator (creates geometry), processor (modifies geometry), consumer (no geometry output), field (no geometry sockets)",
        },
        max_results: {
          type: "number",
          description: "Maximum results to return (default: 15)",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "get_node_details",
    description:
      "Get complete details about a specific geometry node: inputs, outputs, properties, domain, role, and observed behavior.",
    inputSchema: {
      type: "object",
      properties: {
        node_id: {
          type: "string",
          description:
            "Node type ID (e.g., 'GeometryNodeMeshCube') or partial name (e.g., 'mesh cube', 'subdivide')",
        },
      },
      required: ["node_id"],
    },
  },
  {
    name: "check_connection",
    description:
      "Check if two socket types can connect in Blender's geometry nodes. Reports DIRECT, CONVERT, or INVALID.",
    inputSchema: {
      type: "object",
      properties: {
        from_type: {
          type: "string",
          description:
            "Source socket type: GEOMETRY, VALUE, INT, BOOLEAN, VECTOR, ROTATION, MATRIX, RGBA, STRING, OBJECT, COLLECTION, IMAGE, MATERIAL",
        },
        to_type: {
          type: "string",
          description: "Target socket type (same options as from_type)",
        },
      },
      required: ["from_type", "to_type"],
    },
  },
  {
    name: "list_patterns",
    description:
      "List all verified geometry node tree patterns (known-good recipes that have been tested in Blender).",
    inputSchema: {
      type: "object",
      properties: {
        domain: {
          type: "string",
          description: "Optional filter by domain keyword (e.g., 'mesh', 'scatter', 'curve')",
        },
      },
    },
  },
  {
    name: "get_pattern",
    description:
      "Get the full details of a verified pattern including all nodes, properties, links, and result statistics.",
    inputSchema: {
      type: "object",
      properties: {
        pattern_name: {
          type: "string",
          description: "Pattern name (partial match supported) or numeric index from list_patterns",
        },
      },
      required: ["pattern_name"],
    },
  },
  {
    name: "generate_script",
    description:
      "Generate a complete Blender Python script that builds a geometry node tree from a natural language description. Uses pattern matching and compositional generation from the knowledge base.",
    inputSchema: {
      type: "object",
      properties: {
        description: {
          type: "string",
          description:
            "Natural language description of desired geometry node tree (e.g., 'subdivide a mesh and smooth it', 'scatter instances on a surface')",
        },
        mesh_type: {
          type: "string",
          description: "Test mesh type: cube, sphere, plane, cylinder, monkey, grid (default: cube)",
          enum: ["cube", "sphere", "plane", "cylinder", "monkey", "grid"],
        },
      },
      required: ["description"],
    },
  },
  {
    name: "get_kb_stats",
    description:
      "Get overview statistics of the knowledge base: node counts, available domains, roles, data source status, and Blender version info.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "run_discovery",
    description:
      "Run a discovery phase against the local Blender installation to build or update the knowledge base. Phases: catalog, connections, classify, patterns, build_kb.",
    inputSchema: {
      type: "object",
      properties: {
        phase: {
          type: "string",
          description:
            "Discovery phase to run: 'catalog' (enumerate nodes), 'connections' (test socket compatibility), 'classify' (domain classification), 'patterns' (verify recipes), 'build_kb' (assemble knowledge base)",
          enum: ["catalog", "connections", "classify", "patterns", "build_kb"],
        },
      },
      required: ["phase"],
    },
  },
];

// ---------------------------------------------------------------------------
// Tool dispatch
// ---------------------------------------------------------------------------

function handleToolCall(name, args) {
  switch (name) {
    case "search_nodes":
      return searchNodes(args.query, args.domain, args.role, args.max_results);
    case "get_node_details":
      return getNodeDetails(args.node_id);
    case "check_connection":
      return checkConnection(args.from_type, args.to_type);
    case "list_patterns":
      return listPatterns(args.domain);
    case "get_pattern":
      return getPattern(args.pattern_name);
    case "generate_script":
      return generateScript(args.description, args.mesh_type);
    case "get_kb_stats":
      return getKbStats();
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// ---------------------------------------------------------------------------
// MCP Server setup
// ---------------------------------------------------------------------------

const server = new Server(
  { name: "blender-geonodes-ai", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: TOOLS };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  log(`Tool call: ${name} ${JSON.stringify(args)}`);

  try {
    // run_discovery is async
    if (name === "run_discovery") {
      const result = await runDiscovery(args.phase);
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    }

    const result = handleToolCall(name, args || {});
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    log(`Error in ${name}: ${err.message}`);
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify({ error: err.message, tool: name }, null, 2),
        },
      ],
      isError: true,
    };
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

const transport = new StdioServerTransport();
server.connect(transport);

log("Blender Geometry Nodes AI MCP server running");
log(`  Project dir: ${PROJECT_DIR || "(not set)"}`);
log(`  Blender path: ${BLENDER_PATH || "(not set)"}`);
