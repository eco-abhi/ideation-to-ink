import { useMemo } from "react";
import { ReactFlow, Background, Controls, type Node, type Edge, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { FlowStatus, NodeStatus, TopologyNode } from "../api";

// Status palette + icon: color never carries status alone (dataviz skill, status
// palette rule) -- every node also gets a symbol and the label stays plain ink.
const STATUS_STYLE: Record<NodeStatus, { border: string; bg: string; icon: string }> = {
  pending: { border: "var(--gridline)", bg: "var(--surface-1)", icon: "" },
  completed: { border: "var(--status-good)", bg: "color-mix(in srgb, var(--status-good) 12%, var(--surface-1))", icon: "✓ " },
  failed: { border: "var(--status-critical)", bg: "color-mix(in srgb, var(--status-critical) 14%, var(--surface-1))", icon: "✕ " },
  paused: { border: "var(--status-warning)", bg: "color-mix(in srgb, var(--status-warning) 16%, var(--surface-1))", icon: "⏸ " },
};

// Excludes "cross-cutting" (error_gate) deliberately -- it's not a step in the
// pipeline, it's reachable from every node on failure. Rendering it as a normal
// column node left it floating with no edges, which read as broken rather than
// intentional; it's shown as a caption below the graph instead, and only
// promoted into the graph when it's actually the active/paused node.
const PHASE_ORDER = ["ideation", "experiments", "writing", "review"];
const COLUMN_WIDTH = 280;
const ROW_HEIGHT = 84;
const NODE_WIDTH = 220;

const LOOP_EDGE_KEY = "revision_router->section_drafters";

interface Props {
  flow: FlowStatus;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

export function FlowGraph({ flow, selectedNodeId, onSelectNode }: Props) {
  const statusById = useMemo(() => {
    const map = new Map<string, NodeStatus>();
    for (const s of flow.node_status) map.set(s.id, s.status);
    return map;
  }, [flow.node_status]);

  const errorGateActive = statusById.get("error_gate") !== "pending";
  const visibleNodes = useMemo(
    () => flow.nodes.filter((n) => n.phase !== "cross-cutting" || errorGateActive),
    [flow.nodes, errorGateActive],
  );

  // Align each phase column's first row with the previous phase's last row, so
  // the connecting edge between phases lands (close to) horizontal instead of a
  // long diagonal spanning the whole column height.
  const { position, phaseStartRow } = useMemo(() => {
    const byPhase = new Map<string, TopologyNode[]>();
    for (const n of visibleNodes) {
      if (!byPhase.has(n.phase)) byPhase.set(n.phase, []);
      byPhase.get(n.phase)!.push(n);
    }
    const startRow: Record<string, number> = {};
    let cursor = 0;
    for (const phase of PHASE_ORDER) {
      startRow[phase] = cursor;
      const count = byPhase.get(phase)?.length ?? 0;
      if (count > 0) cursor += count - 1;
    }
    startRow["cross-cutting"] = cursor + 3;

    const pos = new Map<string, { x: number; y: number }>();
    const rowInPhase = new Map<string, number>();
    for (const n of visibleNodes) {
      const columnIndex = n.phase === "cross-cutting" ? PHASE_ORDER.length : PHASE_ORDER.indexOf(n.phase);
      const row = rowInPhase.get(n.phase) ?? 0;
      rowInPhase.set(n.phase, row + 1);
      pos.set(n.id, { x: columnIndex * COLUMN_WIDTH, y: (startRow[n.phase] + row) * ROW_HEIGHT });
    }
    return { position: pos, phaseStartRow: startRow };
  }, [visibleNodes]);

  const nodes: Node[] = useMemo(() => {
    const columnHeaders: Node[] = PHASE_ORDER.map((phase, i) => ({
      id: `__header_${phase}`,
      data: { label: phase.toUpperCase() },
      position: { x: i * COLUMN_WIDTH, y: (phaseStartRow[phase] - 0.85) * ROW_HEIGHT },
      draggable: false,
      selectable: false,
      style: {
        background: "transparent",
        border: "none",
        color: "var(--text-muted)",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 1,
        width: NODE_WIDTH,
        pointerEvents: "none",
      },
    }));

    const dataNodes: Node[] = visibleNodes.map((n) => {
      const status = statusById.get(n.id) ?? "pending";
      const style = STATUS_STYLE[status];
      const isSelected = n.id === selectedNodeId;

      return {
        id: n.id,
        data: { label: `${style.icon}${n.label}` },
        position: position.get(n.id)!,
        style: {
          background: style.bg,
          border: `2px solid ${isSelected ? "var(--series-blue)" : style.border}`,
          borderRadius: n.kind === "gate" ? 20 : 8,
          borderStyle: n.kind === "plumbing" ? "dashed" : "solid",
          padding: "8px 10px",
          fontSize: 12,
          color: "var(--text-primary)",
          width: NODE_WIDTH,
          cursor: "pointer",
          boxShadow: isSelected ? "0 0 0 3px color-mix(in srgb, var(--series-blue) 25%, transparent)" : undefined,
        },
      };
    });

    return [...columnHeaders, ...dataNodes];
  }, [visibleNodes, position, phaseStartRow, statusById, selectedNodeId]);

  const edges: Edge[] = useMemo(
    () =>
      flow.edges
        .filter((e) => position.has(e.source) && position.has(e.target))
        .map((e, i) => {
          const isLoop = `${e.source}->${e.target}` === LOOP_EDGE_KEY;
          return {
            id: `${e.source}-${e.target}-${i}`,
            source: e.source,
            target: e.target,
            label: e.label ?? undefined,
            type: "smoothstep",
            animated: statusById.get(e.source) === "completed" && statusById.get(e.target) === "pending",
            markerEnd: { type: MarkerType.ArrowClosed, color: isLoop ? "var(--status-warning)" : "var(--text-muted)" },
            style: { stroke: isLoop ? "var(--status-warning)" : "var(--gridline)", strokeDasharray: isLoop ? "4 3" : undefined },
            labelStyle: { fontSize: 10, fill: "var(--text-secondary)" },
            labelBgStyle: { fill: "var(--surface-1)" },
          };
        }),
    [flow.edges, statusById, position],
  );

  return (
    <div>
      <div style={{ height: "68vh", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface-1)" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={(_, node) => !node.id.startsWith("__header_") && onSelectNode(node.id)}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="var(--gridline)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "6px 2px 0" }}>
        Any node above can fail and route to <code>error_gate</code> for human review
        {errorGateActive ? " — it's active now, shown in the graph." : " (not shown here while idle, to avoid clutter)."}
      </p>
    </div>
  );
}
