import { BookOpen, Sparkles, CheckCircle2, Loader2 } from "lucide-react";
import * as d3 from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";

const SOURCE_COLORS = {
  seed: "#A142F4",
  webpage: "#4285F4",
  pdf: "#EA4335",
};

function getStageMetrics(sources) {
  const seedSource = sources.find((s) => s.source_type === "seed");
  const discoveredSources = sources.filter((s) => s.source_type !== "seed");

  return {
    seedReady: seedSource?.status === "ready",
    discoveredCount: discoveredSources.length,
    discoveredReady: discoveredSources.filter((s) => s.status === "ready").length,
    discoveredErrored: discoveredSources.filter((s) => s.status === "error").length,
    hasDiscovered: discoveredSources.length > 0,
    allDiscoveredDone: discoveredSources.every((s) => s.status === "ready" || s.status === "error"),
    anyDiscoveredProcessing: discoveredSources.some((s) => s.status === "processing"),
    anyDiscoveredCrawling: discoveredSources.some((s) => s.status === "crawling"),
  };
}

export function computeStage(sources, edges) {
  if (!sources.length) return 1;

  const {
    seedReady,
    hasDiscovered,
    allDiscoveredDone,
    anyDiscoveredProcessing,
    anyDiscoveredCrawling,
  } = getStageMetrics(sources);

  // Stage 1 — Seed still being processed.
  if (!seedReady) return 1;

  // Stage 5 — All discovered sources settled, graph edges pending.
  if (hasDiscovered && allDiscoveredDone && edges.length === 0) return 5;

  // Stage 4 — Crawling finished; now summarising + embedding.
  // Keep on stage 3 while any source is still being fetched (crawling overlaps
  // with processing for concurrently-finished sources).
  if (anyDiscoveredProcessing && !anyDiscoveredCrawling) return 4;

  // Stage 3 — Pages being fetched (covers the crawling+processing overlap too).
  if (anyDiscoveredCrawling) return 3;

  // Stage 2 — Discovering sources, or discovered sources are queued but not crawling yet.
  if (seedReady) return 2;

  return 1;
}

export function statusLine(stage, sources, notebookStatus) {
  const { discoveredCount, discoveredReady, discoveredErrored, hasDiscovered } = getStageMetrics(sources);
  const errorSuffix = discoveredErrored > 0 ? ` (${discoveredErrored} failed)` : "";

  if (notebookStatus === "error") {
    return `Completed with ${discoveredReady} of ${discoveredCount} related sources · ${discoveredErrored} could not be fetched`;
  }
  switch (stage) {
    case 1: return "Processing seed document…";
    case 2:
      return hasDiscovered
        ? `Found ${discoveredCount} related source${discoveredCount !== 1 ? "s" : ""}`
        : "Finding related sources…";
    case 3: return `Crawling pages… ${discoveredReady} of ${discoveredCount - discoveredErrored} sources fetched${errorSuffix}`;
    case 4: return `Analysing content… ${discoveredReady} of ${discoveredCount - discoveredErrored} sources ready${errorSuffix}`;
    case 5: return "Building knowledge connections…";
    default: return "";
  }
}

function StageTracker({ currentStage, highestStage, metrics }) {
  const stages = [
    { title: "Processing seed", desc: "Parsing initial document" },
    { title: "Sources identified", desc: metrics.discoveredCount > 0 ? `Found ${metrics.discoveredCount} related sources` : "Searching web…" },
    { title: "Crawling pages", desc: metrics.discoveredReady > 0 ? `Crawled ${metrics.discoveredReady} pages` : "Pending" },
    { title: "Analysing content", desc: "Extracting concepts" },
    { title: "Building graph", desc: "Mapping relationships" },
  ];

  return (
    <div className="flex h-full flex-col">
      {stages.map((stage, i) => {
        const stageNum = i + 1;
        const active = stageNum === currentStage;
        const isDone = stageNum < currentStage;

        return (
          <div key={stageNum} className="relative flex flex-1">
            {/* The line connector */}
            {i !== stages.length - 1 && (
              <div className={`absolute left-[11px] top-[28px] bottom-0 w-[2px] ${isDone ? "bg-[#34a853]" : "bg-[#f0f4f9]"}`} />
            )}

            <div className="flex w-full items-start gap-4 pb-4">
              <div className="relative mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center bg-white">
                {isDone ? (
                  <CheckCircle2 className="h-5 w-5 text-[#34a853]" />
                ) : active ? (
                  <Loader2 className="h-5 w-5 animate-spin text-[#0b57d0]" />
                ) : (
                  <div className="h-3 w-3 rounded-full border-2 border-[#dadce0]" />
                )}
              </div>
              <div className="flex flex-col">
                <span className={`text-[15px] font-medium ${isDone || active ? "text-[#1f1f1f]" : "text-[#9aa0a6]"}`}>
                  {stage.title}
                </span>
                <span className={`text-[13px] ${active ? "text-[#0b57d0]" : "text-[#5f6368]"}`}>
                  {active ? "Active…" : isDone ? "Completed" : stage.desc}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
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

export default function FormationScreen({ notebook, sources, edges, onReady }) {
  const wrapRef = useRef(null);
  const simulationRef = useRef(null);
  const liveNodeMapRef = useRef(new Map());
  const enteringNodeIds = useRef(new Set());
  const edgeAnimStates = useRef(new Map()); // edgeKey -> { offset, animating }
  const [tick, setTick] = useState(0);
  const size = useSize(wrapRef);

  const [highestStage, setHighestStage] = useState(1);
  const [doneOverlay, setDoneOverlay] = useState(false);
  const [doneOverlayOpacity, setDoneOverlayOpacity] = useState(0);
  const readyFiredRef = useRef(false);

  const currentStage = useMemo(() => computeStage(sources, edges), [sources, edges]);
  const displayStage = Math.max(highestStage, currentStage);

  useEffect(() => {
    setHighestStage((prev) => Math.max(prev, currentStage));
  }, [currentStage]);

  // Trigger "done" moment
  useEffect(() => {
    if ((notebook?.status === "ready" || notebook?.status === "error") && !readyFiredRef.current) {
      readyFiredRef.current = true;
      const positions = new Map(
        Array.from(liveNodeMapRef.current.entries()).map(([id, n]) => [
          id,
          { x: n.x, y: n.y, vx: 0, vy: 0 },
        ])
      );
      onReady?.(positions);

      setDoneOverlay(true);
      requestAnimationFrame(() => setDoneOverlayOpacity(1));

      setTimeout(() => {
        setDoneOverlayOpacity(0);
      }, 1800);
      setTimeout(() => {
        setDoneOverlay(false);
      }, 2400);
    }
  }, [notebook?.status, onReady]);

  const [staggerVisibleIds, setStaggerVisibleIds] = useState(new Set());

  useEffect(() => {
    // Only queue up sources that have moved past 'pending' (or are seed)
    const newlyVisible = sources
      .filter((s) => s.status !== "pending" || s.source_type === "seed")
      .map((s) => s.id)
      .filter((id) => !staggerVisibleIds.has(id));

    if (newlyVisible.length > 0) {
      newlyVisible.forEach((id, index) => {
        setTimeout(() => {
          setStaggerVisibleIds((prev) => {
            const next = new Set(prev);
            next.add(id);
            return next;
          });
        }, index * 400); // 400ms stagger
      });
    }
  }, [sources, staggerVisibleIds]);

  const { nodes, links } = useMemo(() => {
    const visibleSources = sources.filter(
      (s) => staggerVisibleIds.has(s.id)
    );
    const graphNodes = visibleSources.map((source, index) => ({
      id: source.id,
      title: source.title?.startsWith("http") ? "Article header" : source.title,
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
  }, [sources, edges, staggerVisibleIds]);

  // Create simulation once
  useEffect(() => {
    const simulation = d3
      .forceSimulation([])
      .force("charge", d3.forceManyBody().strength(-260))
      .force(
        "link",
        d3.forceLink([]).id((d) => d.id).distance((d) => {
          const sim = Math.min(1, Math.max(0, d.similarity ?? 0));
          return 160 - sim * 70;
        })
      )
      .force("center", d3.forceCenter(400, 300))
      .force("collision", d3.forceCollide().radius((d) => d.r + 10))
      .alphaDecay(0.03);

    simulationRef.current = simulation;
    simulation.on("tick", () => {
      const map = new Map();
      simulation.nodes().forEach((n) => map.set(n.id, n));
      liveNodeMapRef.current = map;
      setTick((v) => v + 1);
    });
    return () => simulation.stop();
  }, []);

  // Update center when size changes
  useEffect(() => {
    if (!simulationRef.current || !size.width || !size.height) return;
    simulationRef.current.force("center", d3.forceCenter(size.width / 2, size.height / 2));
  }, [size.width, size.height]);

  // Incrementally add nodes — same logic as DocumentWeb
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

      enteringNodeIds.current.add(node.id);
      setTimeout(() => {
        enteringNodeIds.current.delete(node.id);
        setTick((v) => v + 1);
      }, 620);

      return { ...node, x: x + (Math.random() - 0.5) * 30, y: y + (Math.random() - 0.5) * 30 };
    });

    const survivingNodes = currentSimNodes.filter((n) => !removedIds.has(n.id));
    simulation.nodes([...survivingNodes, ...positionedAdded]);
    simulation.force("link").links(links);
    simulation.alpha(0.3).restart();
  }, [nodes, links, size.width, size.height]);

  // Animate new edges with stroke-dashoffset stagger
  useEffect(() => {
    const liveNodeMap = liveNodeMapRef.current;
    links.forEach((link, i) => {
      const srcId = typeof link.source === "object" ? link.source.id : link.source;
      const tgtId = typeof link.target === "object" ? link.target.id : link.target;
      const key = `${srcId}-${tgtId}`;
      if (!edgeAnimStates.current.has(key)) {
        const src = liveNodeMap.get(srcId);
        const tgt = liveNodeMap.get(tgtId);
        const length = src && tgt
          ? Math.hypot((tgt.x || 0) - (src.x || 0), (tgt.y || 0) - (src.y || 0))
          : 200;
        edgeAnimStates.current.set(key, { offset: length, length, animating: true });

        setTimeout(() => {
          // Step 1: enable the transition while keeping the offset unchanged so
          // the browser paints one frame with transition enabled but edge still hidden.
          edgeAnimStates.current.set(key, { offset: length, length, animating: false });
          setTick((v) => v + 1);
          // Step 2: one frame later change the offset — the transition now fires.
          requestAnimationFrame(() => {
            edgeAnimStates.current.set(key, { offset: 0, length, animating: false });
            setTick((v) => v + 1);
          });
        }, i * 120 + 500);
      }
    });
  }, [links]);

  const liveNodeMap = liveNodeMapRef.current;
  const totalSources = sources.length;
  const totalEdges = edges.length;

  // Ghost edges: nearest-neighbour connections between ready nodes, rendered as
  // animated dashed lines to suggest computation before real edges arrive at t=17s.
  const ghostLinks = useMemo(() => {
    if (edges.length > 0) return [];
    const nodeArr = Array.from(liveNodeMapRef.current.values()).filter(
      (n) => n.status === "ready" || n.source_type === "seed"
    );
    if (nodeArr.length < 2) return [];
    const pairs = [];
    for (let i = 0; i < nodeArr.length; i++) {
      for (let j = i + 1; j < nodeArr.length; j++) {
        const a = nodeArr[i], b = nodeArr[j];
        pairs.push({
          key: `ghost-${a.id}-${b.id}`,
          ax: a.x || 0, ay: a.y || 0,
          bx: b.x || 0, by: b.y || 0,
          dist: Math.hypot((b.x || 0) - (a.x || 0), (b.y || 0) - (a.y || 0)),
        });
      }
    }
    pairs.sort((a, b) => a.dist - b.dist);
    return pairs.slice(0, Math.min(nodeArr.length + 3, 12));
  }, [edges.length, tick]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[radial-gradient(circle_at_top,rgba(66,133,244,0.08),transparent_40%),linear-gradient(180deg,#f4f8fb_0%,#eef3f8_100%)]">
      {/* Top bar */}
      <div className="flex shrink-0 items-center justify-between px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-[#e0e2e0]">
            <BookOpen className="h-[22px] w-[22px] text-[#0b57d0]" />
          </div>
          <div>
            <h1 className="text-xl font-medium tracking-tight text-[#1f1f1f]">
              {notebook?.title || "Synapse Notebook"}
            </h1>
            <p className="text-xs text-[#5f6368]">Building Knowledge Graph</p>
          </div>
        </div>
      </div>

      {/* Main area */}
      <main className="flex flex-1 flex-col gap-4 px-4 pb-4 lg:flex-row min-h-0 overflow-hidden">
        {/* Stage tracker Panel */}
        <div className="flex w-full flex-col rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm lg:w-[340px] shrink-0 px-8 py-7">
          <p className="mb-8 flex items-center gap-2 text-base font-medium text-[#1f1f1f]">
            <Sparkles className="h-5 w-5 text-[#0b57d0]" />
            Discovery Process
          </p>
          <div className="flex-1 overflow-y-auto no-scrollbar min-h-0">
            <StageTracker currentStage={displayStage} highestStage={highestStage} metrics={getStageMetrics(sources)} />
          </div>
        </div>

        {/* Graph area Panel */}
        <div ref={wrapRef} className="relative flex-1 rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm overflow-hidden">
          {size.width > 0 && (
            <svg className="h-full w-full">
              <defs>
                <filter id="formation-shadow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.12" />
                </filter>
              </defs>
              <g>
                {/* Ghost edges — animated dashed lines between ready nodes before real edges exist */}
                {ghostLinks.map(({ key, ax, ay, bx, by }) => (
                  <line
                    key={key}
                    x1={ax} y1={ay} x2={bx} y2={by}
                    stroke="rgba(66,133,244,0.18)"
                    strokeWidth={1}
                    strokeDasharray="8 5"
                    className="ghost-edge"
                  />
                ))}

                {links.map((link) => {
                  const srcId = typeof link.source === "object" ? link.source.id : link.source;
                  const tgtId = typeof link.target === "object" ? link.target.id : link.target;
                  const src = liveNodeMap.get(srcId);
                  const tgt = liveNodeMap.get(tgtId);
                  if (!src || !tgt) return null;
                  const key = `${srcId}-${tgtId}`;
                  const anim = edgeAnimStates.current.get(key);
                  const sim = Math.min(1, Math.max(0, link.similarity ?? 0));
                  const len = anim?.length ?? Math.hypot(tgt.x - src.x, tgt.y - src.y);
                  const dashOffset = anim?.offset ?? 0;

                  return (
                    <line
                      key={key}
                      x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                      stroke={`rgba(120,134,159,${0.22 + sim * 0.5})`}
                      strokeWidth={1 + sim * 2}
                      strokeDasharray={len}
                      strokeDashoffset={dashOffset}
                      style={{ transition: anim?.animating ? "none" : "stroke-dashoffset 500ms ease-out" }}
                    />
                  );
                })}

                {Array.from(liveNodeMap.values()).map((node) => {
                  const color = SOURCE_COLORS[node.source_type] || SOURCE_COLORS.webpage;
                  const isEntering = enteringNodeIds.current.has(node.id);

                  return (
                    <g
                      key={node.id}
                      className={isEntering ? "node-entering" : ""}
                      style={{ transformOrigin: `${node.x}px ${node.y}px` }}
                    >
                      <circle
                        cx={node.x} cy={node.y} r={node.r}
                        fill={color}
                        fillOpacity={node.status === "ready" || node.source_type === "seed" ? 0.96 : 0.58}
                        stroke="#ffffff"
                        strokeWidth={2}
                        filter="url(#formation-shadow)"
                      />
                      <text
                        x={node.x} y={node.y + node.r + 16}
                        textAnchor="middle" fontSize="11" fill="#1f1f1f"
                        style={{ pointerEvents: "none" }}
                      >
                        {node.title.length > 24 ? `${node.title.slice(0, 22)}…` : node.title}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}

          {/* Color legend */}
          <div className="absolute bottom-6 left-6 flex items-center gap-4">
            {Object.entries(SOURCE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1.5">
                <div className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs capitalize text-[#5f6368]">{type}</span>
              </div>
            ))}
          </div>

          {/* Live status line */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 text-sm text-[#5f6368]">
            {statusLine(displayStage, sources, notebook?.status)}
          </div>

          <style>{`
            @keyframes ghost-march { to { stroke-dashoffset: -26; } }
            .ghost-edge { animation: ghost-march 1.4s linear infinite; }
          `}</style>

          {/* "Done" overlay */}
          {doneOverlay && (
            <div
              className="pointer-events-none absolute inset-0 flex items-center justify-center"
              style={{ opacity: doneOverlayOpacity, transition: "opacity 300ms ease" }}
            >
              <div className="rounded-[2rem] border border-[#e0e2e0] bg-white/90 px-10 py-7 text-center shadow-lg backdrop-blur">
                <div className="mb-2 flex items-center justify-center gap-2 text-[#0b57d0]">
                  <Sparkles className="h-5 w-5" />
                  <span className="text-lg font-medium text-[#1f1f1f]">
                    {notebook?.status === "error" ? "Ready with partial sources" : "Knowledge graph ready"}
                  </span>
                </div>
                <p className="text-sm text-[#5f6368]">
                  {sources.filter(s => s.status === "ready").length} source{totalSources !== 1 ? "s" : ""} ready
                  {notebook?.status === "error" && sources.some(s => s.status === "error")
                    ? ` · ${sources.filter(s => s.status === "error").length} failed`
                    : totalEdges > 0 ? ` · ${totalEdges} connection${totalEdges !== 1 ? "s" : ""}` : ""}
                </p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
