import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { FlowStatus, NodeStatus } from "../api";

const STATUS_COLOR: Record<NodeStatus, { bg: string; border: string }> = {
  pending: { bg: "#f1f5f9", border: "#94a3b8" },
  completed: { bg: "#dcfce7", border: "#22c55e" },
  failed: { bg: "#fee2e2", border: "#ef4444" },
  paused: { bg: "#fef3c7", border: "#f59e0b" },
};

const PHASE_ORDER = ["ideation", "experiments", "writing", "review", "cross-cutting"];
const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 90;

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

  const nodes: Node[] = useMemo(() => {
    const perPhaseIndex = new Map<string, number>();
    return flow.nodes.map((n) => {
      const columnIndex = PHASE_ORDER.indexOf(n.phase);
      const rowIndex = perPhaseIndex.get(n.phase) ?? 0;
      perPhaseIndex.set(n.phase, rowIndex + 1);

      const status = statusById.get(n.id) ?? "pending";
      const colors = STATUS_COLOR[status];
      const isSelected = n.id === selectedNodeId;

      return {
        id: n.id,
        data: { label: n.label },
        position: {
          x: columnIndex * COLUMN_WIDTH,
          y: rowIndex * ROW_HEIGHT + (n.phase === "cross-cutting" ? 300 : 0),
        },
        style: {
          background: colors.bg,
          border: `2px solid ${isSelected ? "#2563eb" : colors.border}`,
          borderRadius: n.kind === "gate" ? 20 : 6,
          borderStyle: n.kind === "plumbing" ? "dashed" : "solid",
          padding: 8,
          fontSize: 12,
          width: 200,
          cursor: "pointer",
        },
      };
    });
  }, [flow.nodes, statusById, selectedNodeId]);

  const edges: Edge[] = useMemo(
    () =>
      flow.edges.map((e, i) => ({
        id: `${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        label: e.label ?? undefined,
        animated: statusById.get(e.source) === "completed" && statusById.get(e.target) === "pending",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#94a3b8" },
        labelStyle: { fontSize: 10 },
      })),
    [flow.edges, statusById],
  );

  return (
    <div style={{ height: "70vh", border: "1px solid #e2e8f0", borderRadius: 8 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}
