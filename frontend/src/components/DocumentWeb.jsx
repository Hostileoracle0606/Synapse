import { Crosshair, Minus, Plus, RotateCcw, Sparkles } from "lucide-react";
import * as d3 from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";

const SOURCE_COLORS = {
  seed: "#A142F4",      // purple
  webpage: "#4285F4",   // blue
  pdf: "#EA4335",       // red
  youtube: "#fa7b17",   // orange
  social: "#34a853",    // green
};

const SOURCE_TYPE_LABELS = {
  seed: "Seed",
  webpage: "Web",
  pdf: "PDF",
  youtube: "Video",
  social: "Social",
};

function sourceTone(status) {
  switch (status) {
    case "ready": return "#34a853";
    case "crawling":
    case "processing": return "#fbbc04";
    case "error": return "#ea4335";
    default: return "#c7c9cc";
  }
}

function useSize(ref) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const update = () => {
      const { width, height } = el.getBoundingClientRect();
      setSize({ width, height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return size;
}

export default function DocumentWeb({
  sources,
  edges,
  selectedSource,
  onSelectSource,
  initialNodePositions,
  citedSourceIds,
}) {
  const wrapRef = useRef(null);
  const simulationRef = useRef(null);
  const liveNodeMapRef = useRef(new Map());
  const alphaRef = useRef(1);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  const [tick, setTick] = useState(0);
  const [hoveredEdge, setHoveredEdge] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const size = useSize(wrapRef);

  // Drag-to-pan state
  const dragState = useRef(null); // { startX, startY, startTX, startTY }

  const { nodes, links } = useMemo(() => {
    // Errored sources are hidden everywhere in the UI. If we let them through
    // here they'd render as disconnected orphan dots in the graph.
    const visibleSources = sources.filter((s) => s.status !== "error");
    const graphNodes = visibleSources.map((source, index) => ({
      id: source.id,
      title: source.title?.startsWith("http") ? "Article header" : source.title,
      summary: source.summary,
      content: source.content,
      url: source.url,
      source_type: source.source_type,
      status: source.status,
      r: source.source_type === "seed" ? 28 : 16 + Math.min(source.title.length / 2.7, 12),
      order: index,
    }));
    const sourceIds = new Set(graphNodes.map((n) => n.id));
    const graphLinks = edges
      .filter((e) => sourceIds.has(e.source_a) && sourceIds.has(e.source_b))
      .map((e) => ({
        source: e.source_a,
        target: e.source_b,
        similarity: e.similarity,
        relationship: e.relationship,
      }));
    return { nodes: graphNodes, links: graphLinks };
  }, [sources, edges]);

  // Connected node ids for neighborhood highlighting
  const connectedNodeIds = useMemo(() => {
    if (!selectedSource) return null;
    const set = new Set();
    links.forEach((l) => {
      const srcId = typeof l.source === "object" ? l.source.id : l.source;
      const tgtId = typeof l.target === "object" ? l.target.id : l.target;
      if (srcId === selectedSource.id) set.add(tgtId);
      if (tgtId === selectedSource.id) set.add(srcId);
    });
    return set;
  }, [selectedSource, links]);

  // Set of cited source ids from the latest assistant chat response.
  // While this is populated, the graph dims non-cited nodes and lights up
  // cited ones with a soft halo — replacing the old "Cited sources" pill
  // list under each chat message. A user click on any node still wins
  // (selection takes precedence over citation highlight).
  const citedNodeIds = useMemo(() => {
    if (!citedSourceIds || citedSourceIds.length === 0) return null;
    return new Set(citedSourceIds);
  }, [citedSourceIds]);

  // Create simulation ONCE on mount
  useEffect(() => {
    const simulation = d3
      .forceSimulation([])
      .force("charge", d3.forceManyBody().strength(-260))
      .force(
        "link",
        d3.forceLink([]).id((d) => d.id).distance((d) => {
          const simVal = Math.min(1, Math.max(0, d.similarity ?? 0));
          return 160 - simVal * 70;
        })
      )
      .force("center", d3.forceCenter(400, 300))
      .force("collision", d3.forceCollide().radius((d) => d.r + 10))
      .alphaDecay(0.03);

    simulationRef.current = simulation;
    simulation.on("tick", () => {
      alphaRef.current = simulationRef.current.alpha();
      const map = new Map();
      simulationRef.current.nodes().forEach((n) => map.set(n.id, n));
      liveNodeMapRef.current = map;
      setTick((v) => v + 1);
    });
    return () => simulation.stop();
  }, []);

  // Update center force when size changes
  useEffect(() => {
    if (!simulationRef.current || !size.width || !size.height) return;
    simulationRef.current.force("center", d3.forceCenter(size.width / 2, size.height / 2));
  }, [size.width, size.height]);

  // Incrementally update nodes/links
  useEffect(() => {
    const simulation = simulationRef.current;
    if (!simulation) return;

    const currentSimNodes = simulation.nodes();
    const currentSimIds = new Set(currentSimNodes.map((n) => n.id));
    const newIds = new Set(nodes.map((n) => n.id));
    const addedNodes = nodes.filter((n) => !currentSimIds.has(n.id));
    const removedIds = new Set([...currentSimIds].filter((id) => !newIds.has(id)));
    const hasChanges = addedNodes.length > 0 || removedIds.size > 0;

    if (!hasChanges && nodes.length === currentSimNodes.length) {
      simulation.force("link").links(links);
      return;
    }

    const currentMap = new Map(currentSimNodes.map((n) => [n.id, n]));
    const cx = size.width / 2 || 400;
    const cy = size.height / 2 || 300;

    const positionedAdded = addedNodes.map((node) => {
      // Use initialNodePositions if available (coming from FormationScreen)
      if (initialNodePositions?.has(node.id)) {
        const pos = initialNodePositions.get(node.id);
        return { ...node, x: pos.x, y: pos.y, vx: 0, vy: 0 };
      }

      const neighborIds = links
        .filter((l) => {
          const srcId = typeof l.source === "object" ? l.source.id : l.source;
          const tgtId = typeof l.target === "object" ? l.target.id : l.target;
          return srcId === node.id || tgtId === node.id;
        })
        .map((l) => {
          const srcId = typeof l.source === "object" ? l.source.id : l.source;
          const tgtId = typeof l.target === "object" ? l.target.id : l.target;
          return srcId === node.id ? tgtId : srcId;
        });

      const existingNeighbors = neighborIds.map((id) => currentMap.get(id)).filter(Boolean);
      let x = cx, y = cy;
      if (existingNeighbors.length > 0) {
        x = existingNeighbors.reduce((sum, n) => sum + (n.x || cx), 0) / existingNeighbors.length;
        y = existingNeighbors.reduce((sum, n) => sum + (n.y || cy), 0) / existingNeighbors.length;
      }
      return { ...node, x: x + (Math.random() - 0.5) * 30, y: y + (Math.random() - 0.5) * 30 };
    });

    const survivingNodes = currentSimNodes.filter((n) => !removedIds.has(n.id));
    const updatedNodeList = [...survivingNodes, ...positionedAdded];
    simulation.nodes(updatedNodeList);
    simulation.force("link").links(links);

    // If we have pre-positioned nodes from formation, start frozen — but
    // populate liveNodeMap *now* since the simulation won't tick. Skipping
    // this step leaves the render loop with an empty map → no nodes drawn.
    if (initialNodePositions && addedNodes.every((n) => initialNodePositions.has(n.id))) {
      const liveMap = new Map();
      updatedNodeList.forEach((n) => liveMap.set(n.id, n));
      liveNodeMapRef.current = liveMap;
      simulation.alpha(0).stop();
      setTick((v) => v + 1);
    } else {
      simulation.alpha(0.3).restart();
    }
  }, [nodes, links, size.width, size.height, initialNodePositions]);

  const resetView = () => {
    transformRef.current = { x: 0, y: 0, k: 1 };
    setTick((v) => v + 1);
  };

  const reheat = () => {
    if (simulationRef.current) simulationRef.current.alpha(0.6).restart();
  };

  const adjustZoom = (delta, cursorX, cursorY) => {
    const t = transformRef.current;
    const newK = Math.min(2.6, Math.max(0.45, t.k * delta));
    if (cursorX !== undefined && cursorY !== undefined) {
      // Zoom-to-cursor: keep cursor point stationary
      const graphX = (cursorX - t.x) / t.k;
      const graphY = (cursorY - t.y) / t.k;
      transformRef.current = {
        k: newK,
        x: cursorX - graphX * newK,
        y: cursorY - graphY * newK,
      };
    } else {
      transformRef.current.k = newK;
    }
    setTick((v) => v + 1);
  };

  // Pointer-based drag-to-pan
  const handlePointerDown = (e) => {
    if (e.target.closest("[data-node]")) return; // let node clicks through
    e.currentTarget.setPointerCapture(e.pointerId);
    dragState.current = {
      startX: e.clientX,
      startY: e.clientY,
      startTX: transformRef.current.x,
      startTY: transformRef.current.y,
    };
  };

  const handlePointerMove = (e) => {
    if (!dragState.current) return;
    const dx = e.clientX - dragState.current.startX;
    const dy = e.clientY - dragState.current.startY;
    transformRef.current = {
      ...transformRef.current,
      x: dragState.current.startTX + dx,
      y: dragState.current.startTY + dy,
    };
    setTick((v) => v + 1);
  };

  const handlePointerUp = () => {
    dragState.current = null;
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cursorX = e.clientX - rect.left;
    const cursorY = e.clientY - rect.top;
    const delta = e.deltaY < 0 ? 1.1 : 0.91;
    adjustZoom(delta, cursorX, cursorY);
  };

  // Attach wheel listener with { passive: false } so we can preventDefault
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  });

  const handleNodeClick = (node) => onSelectSource?.(node);

  const empty = !sources.length;
  const liveNodeMap = liveNodeMapRef.current;

  return (
    <section className="relative min-h-[28rem] flex-1 overflow-hidden rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm">
      <div className="absolute left-6 top-6 z-10 rounded-full border border-[#e0e2e0] bg-white/80 px-4 py-1.5 shadow-sm backdrop-blur">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#1f1f1f]">
          <Sparkles className="h-4 w-4 text-[#0b57d0]" />
          Document web
        </h2>
      </div>

      {/* Node type legend — only shows colors actually present in this notebook. */}
      {(() => {
        const presentTypes = new Set(
          (sources || [])
            .filter((s) => s.status !== "error")
            .map((s) => s.source_type),
        );
        const items = Object.entries(SOURCE_COLORS).filter(([type]) =>
          presentTypes.has(type),
        );
        if (items.length === 0) return null;
        return (
          <div className="absolute bottom-6 left-6 z-10 flex items-center gap-3 rounded-full border border-[#e0e2e0] bg-white/80 px-4 py-1.5 shadow-sm backdrop-blur">
            {items.map(([type, color]) => (
              <span key={type} className="flex items-center gap-1.5 text-xs text-[#5f6368]">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                {SOURCE_TYPE_LABELS[type] || type}
              </span>
            ))}
          </div>
        );
      })()}

      <div
        ref={wrapRef}
        className="absolute inset-0 cursor-grab active:cursor-grabbing bg-[radial-gradient(circle_at_center,rgba(66,133,244,0.08),transparent_42%),linear-gradient(180deg,#fbfcfe_0%,#f7f9fc_100%)]"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {empty ? (
          <div className="flex h-full items-center justify-center p-8 text-center">
            <div className="max-w-sm rounded-[2rem] border border-dashed border-[#dfe3e8] bg-white/85 p-8 shadow-sm backdrop-blur">
              <p className="text-lg font-medium text-[#1f1f1f]">Your graph will appear here</p>
              <p className="mt-2 text-sm text-[#5f6368]">
                Create a notebook or wait for the discovered sources to finish processing.
              </p>
            </div>
          </div>
        ) : null}

        {!empty ? (
          <svg className="h-full w-full" viewBox={`0 0 ${Math.max(size.width, 1)} ${Math.max(size.height, 1)}`}>
            <defs>
              <filter id="dw-tooltip-shadow" x="-10%" y="-10%" width="120%" height="120%">
                <feDropShadow dx="0" dy="2" stdDeviation="4" floodOpacity="0.12" />
              </filter>
            </defs>
            <g transform={`translate(${transformRef.current.x}, ${transformRef.current.y}) scale(${transformRef.current.k})`}>
              {/* Edges */}
              {links.map((link, index) => {
                const srcId = typeof link.source === "object" ? link.source.id : link.source;
                const tgtId = typeof link.target === "object" ? link.target.id : link.target;
                const source = liveNodeMap.get(srcId);
                const target = liveNodeMap.get(tgtId);
                if (!source || !target) return null;

                const sim = Math.min(1, Math.max(0, link.similarity ?? 0));
                const isConnected = !connectedNodeIds ||
                  (connectedNodeIds.has(srcId) && connectedNodeIds.has(tgtId)) ||
                  srcId === selectedSource?.id ||
                  tgtId === selectedSource?.id;

                // Edge dimming logic, in priority order:
                //   1. user has selected a source → standard neighbourhood dim
                //   2. chat returned citations → only edges between cited
                //      nodes stay bright; everything else fades back
                //   3. otherwise → default opacity tied to similarity
                let edgeOpacity;
                if (connectedNodeIds) {
                  edgeOpacity = isConnected ? (0.22 + sim * 0.5) : 0.06;
                } else if (citedNodeIds) {
                  const bothCited = citedNodeIds.has(srcId) && citedNodeIds.has(tgtId);
                  edgeOpacity = bothCited ? (0.45 + sim * 0.4) : 0.06;
                } else {
                  edgeOpacity = (0.22 + sim * 0.5);
                }

                return (
                  <line
                    key={`${srcId}-${tgtId}-${index}`}
                    x1={source.x} y1={source.y} x2={target.x} y2={target.y}
                    stroke={`rgba(120, 134, 159, ${edgeOpacity})`}
                    strokeWidth={1 + sim * 2}
                    onMouseEnter={() => setHoveredEdge(link)}
                    onMouseLeave={() => setHoveredEdge(null)}
                  />
                );
              })}

              {/* Edge label — no alpha gate */}
              {hoveredEdge ? (() => {
                const srcId = typeof hoveredEdge.source === "object" ? hoveredEdge.source.id : hoveredEdge.source;
                const tgtId = typeof hoveredEdge.target === "object" ? hoveredEdge.target.id : hoveredEdge.target;
                const source = liveNodeMap.get(srcId);
                const target = liveNodeMap.get(tgtId);
                if (!source || !target) return null;
                const mx = (source.x + target.x) / 2;
                const my = (source.y + target.y) / 2;
                const rawLabel = hoveredEdge.relationship ?? "";
                const label = rawLabel.length > 40 ? `${rawLabel.slice(0, 40)}…` : rawLabel;
                return (
                  <g key="edge-label">
                    <rect
                      x={mx - label.length * 3.2} y={my - 12}
                      width={label.length * 6.4 + 8} height={18}
                      rx={4} fill="white" fillOpacity={0.92}
                      stroke="#e0e2e0" strokeWidth={1}
                    />
                    <text
                      x={mx} y={my} textAnchor="middle" dominantBaseline="middle"
                      fontSize="11" fill="#1f1f1f" style={{ pointerEvents: "none" }}
                    >
                      {label}
                    </text>
                  </g>
                );
              })() : null}

              {/* Nodes */}
              {Array.from(liveNodeMap.values()).map((node) => {
                const isSelected = selectedSource?.id === node.id;
                const isCited = citedNodeIds?.has(node.id) || false;
                const color = SOURCE_COLORS[node.source_type] || SOURCE_COLORS.webpage;
                const label = node.title.length > 24 ? `${node.title.slice(0, 22)}...` : node.title;

                // Node opacity, in the same priority order as edges:
                //   1. user-selected source — standard neighbourhood
                //   2. chat citation set — cited nodes bright, rest dim
                //   3. default — full opacity for ready / seed
                let nodeOpacity;
                if (connectedNodeIds) {
                  nodeOpacity = isSelected || connectedNodeIds.has(node.id) ? 0.96 : 0.18;
                } else if (citedNodeIds) {
                  nodeOpacity = isCited ? 1.0 : 0.22;
                } else {
                  nodeOpacity = node.status === "ready" || node.source_type === "seed" ? 0.96 : 0.58;
                }
                const isHovered = hoveredNode?.id === node.id && !isSelected;

                return (
                  <g
                    key={node.id}
                    data-node="true"
                    onClick={() => handleNodeClick(node)}
                    onMouseEnter={() => !isSelected && setHoveredNode(node)}
                    onMouseLeave={() => setHoveredNode(null)}
                    style={{ cursor: "pointer" }}
                  >
                    {/* Cited halo — soft pulsing ring rendered behind the
                        node. Only visible while a chat citation set is
                        active and the node is in it (and the user hasn't
                        explicitly selected something else). */}
                    {isCited && !isSelected && !connectedNodeIds && (
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.r + 8}
                        fill="none"
                        stroke={color}
                        strokeWidth={3}
                        strokeOpacity={0.55}
                        className="cited-halo"
                      />
                    )}
                    <circle
                      cx={node.x} cy={node.y} r={node.r}
                      fill={color}
                      fillOpacity={nodeOpacity}
                      stroke={isSelected ? "#1a73e8" : "#ffffff"}
                      strokeWidth={isSelected ? 4 : 2}
                    />
                    <circle
                      cx={node.x} cy={node.y} r={node.r + 6}
                      fill="none"
                      stroke={isSelected ? "rgba(26,115,232,0.18)" : "transparent"}
                      strokeWidth={2}
                    />
                    <text
                      x={node.x} y={node.y + node.r + 16}
                      textAnchor="middle" fontSize="11" fill="#1f1f1f"
                      style={{ pointerEvents: "none" }}
                    >
                      {label}
                    </text>

                    {/* Hover tooltip */}
                    {isHovered ? (() => {
                      const tx = node.x;
                      const ty = node.y - node.r - 12;
                      const titleText = node.title.length > 32 ? `${node.title.slice(0, 30)}…` : node.title;
                      const typeLabel = node.source_type || "webpage";
                      const dotColor = sourceTone(node.status);
                      const boxW = Math.min(200, Math.max(120, titleText.length * 6.5 + 20));
                      const boxH = 48;
                      return (
                        <g style={{ pointerEvents: "none" }}>
                          <rect
                            x={tx - boxW / 2} y={ty - boxH}
                            width={boxW} height={boxH}
                            rx={8} fill="white" fillOpacity={0.97}
                            filter="url(#dw-tooltip-shadow)"
                            stroke="#e0e2e0" strokeWidth={0.75}
                          />
                          <text x={tx} y={ty - boxH + 16} textAnchor="middle" fontSize="11.5" fill="#1f1f1f" fontWeight="500">
                            {titleText}
                          </text>
                          <circle cx={tx - 20} cy={ty - boxH + 32} r={3.5} fill={dotColor} />
                          <text x={tx - 12} y={ty - boxH + 36} fontSize="10" fill="#5f6368">
                            {typeLabel} · {node.status || "pending"}
                          </text>
                        </g>
                      );
                    })() : null}
                  </g>
                );
              })}
            </g>
          </svg>
        ) : null}

        {/* No popover — clicking a node bubbles up via onSelectSource and the
            sidebar's source card expands inline with the overview content. */}
      </div>

      {/* Zoom controls — bottom-right */}
      <div className="absolute bottom-6 right-6 z-10 flex overflow-hidden rounded-full border border-[#e0e2e0] bg-white p-1 shadow-sm">
        <button type="button" onClick={resetView} className="flex h-10 w-10 items-center justify-center rounded-full text-[#444746] transition-colors hover:bg-[#f0f4f9]">
          <Crosshair className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => adjustZoom(1.15)} className="flex h-10 w-10 items-center justify-center rounded-full text-[#444746] transition-colors hover:bg-[#f0f4f9]">
          <Plus className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => adjustZoom(0.87)} className="flex h-10 w-10 items-center justify-center rounded-full text-[#444746] transition-colors hover:bg-[#f0f4f9]">
          <Minus className="h-4 w-4" />
        </button>
        <button type="button" onClick={reheat} className="flex h-10 w-10 items-center justify-center rounded-full text-[#444746] transition-colors hover:bg-[#f0f4f9]">
          <RotateCcw className="h-4 w-4" />
        </button>
      </div>

      {/* Citation-halo pulse: gentle opacity wave that draws the eye to
          the cited nodes without strobing or being distracting. */}
      <style>{`
        @keyframes cited-halo-pulse {
          0%, 100% { stroke-opacity: 0.45; }
          50%      { stroke-opacity: 0.85; }
        }
        .cited-halo {
          animation: cited-halo-pulse 1.8s ease-in-out infinite;
        }
      `}</style>
    </section>
  );
}
