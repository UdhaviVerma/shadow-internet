"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Background, BackgroundVariant, Controls, Handle, MiniMap, Position,
  ReactFlow, useEdgesState, useNodesState, type Node, type NodeProps,
} from "@xyflow/react";
import { Globe2, Layers3, Network, Server } from "lucide-react";
import type { Workspace } from "@/lib/types";

type InfraNode = Node<{ label: string; detail: string; kind: string; impacted: boolean; providerId?: string }, "infra">;

function InfrastructureNode({ data, selected }: NodeProps<InfraNode>) {
  const Icon = data.kind === "domain" ? Globe2 : data.kind === "provider" ? Layers3 : data.kind === "asn" ? Network : Server;
  return <div className={`infra-node ${data.kind} ${data.impacted ? "impacted" : ""} ${selected ? "selected" : ""}`}>
    <Handle type="target" position={Position.Left} />
    <span className="node-symbol"><Icon size={16} /></span>
    <div><strong>{data.label}</strong><small>{data.detail}</small></div>
    <Handle type="source" position={Position.Right} />
  </div>;
}

const nodeTypes = { infra: InfrastructureNode };

export function InfrastructureGraph({ graph, affectedIds, onProvider, onInspect }: {
  graph: Workspace["graph"]; affectedIds: string[]; onProvider: (id: string) => void; onInspect: (id: string) => void;
}) {
  const [detail, setDetail] = useState("Select a node or edge to inspect evidence");
  const initialNodes = useMemo(() => {
    const counts: Record<string, number> = {};
    return graph.nodes.map((node) => {
      const index = counts[node.kind] ?? 0;
      counts[node.kind] = index + 1;
      const columns = { domain: 10, provider: 410, ip: 810, asn: 1120 };
      return {
        id: node.id, type: "infra" as const,
        position: { x: columns[node.kind], y: index * 110 + (node.kind === "provider" ? 30 : 0) },
        data: { label: node.label, detail: node.detail, kind: node.kind, impacted: affectedIds.includes(node.id), providerId: node.provider_id },
      };
    });
  }, [graph.nodes, affectedIds]);
  const initialEdges = useMemo(() => graph.edges.map((edge) => ({
    ...edge, animated: true, type: "smoothstep",
    style: { stroke: affectedIds.includes(edge.source) && affectedIds.includes(edge.target) ? "#ff6977" : "#315c69", strokeWidth: 1.4 },
    label: undefined, data: { label: edge.label, confidence: edge.confidence, evidenceIds: edge.evidence_ids },
  })), [graph.edges, affectedIds]);
  const [nodes, setNodes, onNodesChange] = useNodesState<InfraNode>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  useEffect(() => setNodes(initialNodes), [initialNodes, setNodes]);
  useEffect(() => setEdges(initialEdges), [initialEdges, setEdges]);

  return <div className="graph-shell" data-testid="infrastructure-graph">
    <div className="graph-overlay"><span><i className="live-dot" /> OBSERVATION GRAPH</span><small>DRAG NODES / SCROLL TO ZOOM</small></div>
    <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.18 }} minZoom={0.25} maxZoom={2}
      colorMode="dark" proOptions={{ hideAttribution: false }}
      onNodeClick={(_, node) => {
        setDetail(`${node.data.label} - ${node.data.detail}`);
        if (node.data.providerId) onProvider(node.data.providerId);
        else onInspect(node.id);
      }}
      onEdgeClick={(_, edge) => setDetail(`${edge.data?.label} | ${edge.data?.confidence} | Evidence: ${edge.data?.evidenceIds.join(", ")}`)}>
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#21303d" />
      <Controls showInteractive={false} />
      <MiniMap nodeColor={(node) => node.data.impacted ? "#ff6977" : node.data.kind === "domain" ? "#42e3c2" : "#52798b"} maskColor="#080d13bb" pannable zoomable />
    </ReactFlow>
    <div className="graph-footnote" role="status">{detail}</div>
  </div>;
}
