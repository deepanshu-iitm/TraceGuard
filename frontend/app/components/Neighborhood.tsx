"use client";

import { useMemo } from "react";
import type { GraphEdge, GraphNode, GraphView } from "../lib/types";

const COLUMNS: { key: string; types: string[] }[] = [
  { key: "People", types: ["customer", "case"] },
  { key: "Instruments", types: ["card", "device", "email", "region"] },
  { key: "Transactions", types: ["txn"] },
  { key: "Prior cases", types: ["closed"] },
];

type Placed = GraphNode & { x: number; y: number; flagged: boolean };

export function Neighborhood({ graph, flaggedTxnId }: { graph: GraphView; flaggedTxnId?: string }) {
  const { placed, edges, columns } = useMemo(() => layout(graph, flaggedTxnId), [graph, flaggedTxnId]);
  const width = 860;
  const height = 340;

  return (
    <section className="panel">
      <h2>Neighborhood</h2>
      <svg className="neighborhood" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Case neighborhood">
        {columns.map((col) => (
          <text key={col.key} className="col-label" x={col.x} y="22">
            {col.key}
          </text>
        ))}
        {edges.map((edge) => (
          <path key={`${edge.from}-${edge.to}-${edge.type}`} className="edge" d={edge.d}>
            <title>{edge.type.replaceAll("_", " ")}</title>
          </path>
        ))}
        {placed.map((node) => (
          <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
            <rect
              className={`node-card ${node.type} ${node.flagged ? "flagged" : ""}`}
              x={0}
              y={0}
              width={168}
              height={44}
              rx={6}
            />
            <text className="node-kind" x={10} y={16}>
              {node.flagged ? "flagged txn" : node.type}
            </text>
            <text className="node-title" x={10} y={34}>
              {shortLabel(node.label || node.id)}
            </text>
            <title>{node.label || node.id}</title>
          </g>
        ))}
      </svg>
    </section>
  );
}

function layout(graph: GraphView, flaggedTxnId?: string) {
  const used = new Set<string>();
  const placed: Placed[] = [];
  const columns: { key: string; x: number }[] = [];
  const colWidth = 210;
  const startX = 24;

  COLUMNS.forEach((column, index) => {
    const nodes = (graph.nodes || []).filter((node) => column.types.includes(node.type) && !used.has(node.id));
    const limited = column.key === "Transactions" ? capTxns(nodes, flaggedTxnId) : nodes.slice(0, 5);
    const x = startX + index * colWidth;
    columns.push({ key: column.key, x });
    limited.forEach((node, row) => {
      used.add(node.id);
      placed.push({
        ...node,
        x,
        y: 42 + row * 56,
        flagged: node.type === "txn" && (node.id === flaggedTxnId || node.label.includes(flaggedTxnId || "___")),
      });
    });
  });

  const byId = Object.fromEntries(placed.map((node) => [node.id, node]));
  const edges = (graph.edges || [])
    .map((edge) => {
      const from = byId[edge.from];
      const to = byId[edge.to];
      if (!from || !to) return null;
      return { ...edge, d: curve(from, to) };
    })
    .filter((edge): edge is GraphEdge & { d: string } => Boolean(edge));

  return { placed, edges, columns };
}

function capTxns(nodes: GraphNode[], flaggedTxnId?: string) {
  const flagged = nodes.filter((node) => node.id === flaggedTxnId);
  const rest = nodes.filter((node) => node.id !== flaggedTxnId);
  return [...flagged, ...rest].slice(0, 5);
}

function curve(from: Placed, to: Placed) {
  const x1 = from.x + 168;
  const y1 = from.y + 22;
  const x2 = to.x;
  const y2 = to.y + 22;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

function shortLabel(value: string) {
  return value.length > 18 ? `${value.slice(0, 16)}…` : value;
}
