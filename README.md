# Blender Geometry Nodes Discovery Engine

An automated system that discovers and catalogs Blender's geometry nodes through empirical exploration. Runs against a live Blender instance to build a structured knowledge base of nodes, socket types, valid connections, and working patterns.

The goal: build the foundation for an AI assistant that truly understands geometry nodes - not from stale documentation, but from what actually works in your specific Blender version.

## Why?

Blender's geometry nodes are powerful but:
- Poorly documented (especially edge cases and implicit behaviors)
- Deeply combinatorial (hundreds of nodes, typed sockets, field vs. value semantics)
- Version-volatile (new nodes, changed behaviors, deprecations every release)

AI models trained on bpy documentation produce code that may be wrong for your Blender version. This project discovers the truth empirically.

## Quick Start

### Prerequisites
- Blender 4.5 LTS or newer installed locally
- That's it. No Python packages needed - scripts run inside Blender's Python.

### Run Discovery

**Windows:**
```
scripts\run_discovery.bat "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
```

**Linux/macOS:**
```
chmod +x scripts/run_discovery.sh
./scripts/run_discovery.sh /path/to/blender
```

**Manual (any OS):**
```
# Phase 1: Enumerate all geometry nodes
blender --background --python discovery/discover_nodes.py

# Phase 2: Test connection compatibility (requires Phase 1 output)
blender --background --python discovery/test_connections.py
```

### Output

After running, check the `discovery/` folder:
- `node_catalog.json` - Every geometry node type with inputs, outputs, socket types, properties
- `connection_matrix.json` - Which socket types can connect to which, including implicit conversions

## Project Structure

```
blender-geonodes-ai/
├── discovery/           Phase 1-2: Automated node enumeration
│   ├── discover_nodes.py       Enumerate all geometry node types
│   ├── test_connections.py     Test socket type compatibility
│   ├── node_catalog.json       (generated) Node type catalog
│   └── connection_matrix.json  (generated) Connection compatibility
├── patterns/            Phase 3: Known-good node tree recipes
├── explorer/            Phase 4: Automated experimentation
│   └── results/
├── knowledge/           Phase 5: Assembled knowledge base
├── scripts/             Launcher scripts
│   ├── run_discovery.bat
│   └── run_discovery.sh
└── README.md
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Node Catalog | Ready | Enumerate all geometry node types and their sockets |
| 2. Connection Matrix | Ready | Discover which socket types connect to which |
| 3. Pattern Library | Planned | Collect and verify working node tree recipes |
| 4. Exploration Engine | Planned | Automated experimentation with novel combinations |
| 5. Knowledge Base | Planned | Unified queryable knowledge store |

## Version Portability

The whole point of empirical discovery: run against Blender 4.5, get a 4.5-accurate catalog. Run against 5.0, get a 5.0 catalog. No manual documentation maintenance needed.

## MCPB Desktop Extension

This project includes an MCP Bundle (Desktop Extension) that gives Claude for Desktop direct access to the knowledge base.

### Extension Setup

```bash
cd mcpb/
npm install
mcpb pack
# Open the .mcpb file with Claude for Desktop
```

### Extension Tools

| Tool | Description |
|------|-------------|
| `search_nodes` | Search the node catalog by keyword, domain, or role |
| `get_node_details` | Get complete details about a specific node (inputs, outputs, properties) |
| `check_connection` | Check if two socket types can connect (DIRECT/CONVERT/INVALID) |
| `list_patterns` | List all verified geometry node tree patterns |
| `get_pattern` | Get full details of a specific pattern |
| `generate_script` | Generate a Blender Python script from natural language |
| `get_kb_stats` | Overview statistics and data source status |
| `run_discovery` | Run discovery phases against your local Blender |

## License

MIT
