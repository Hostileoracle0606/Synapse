import { BookOpen, Sparkles, CheckCircle2, Loader2 } from "lucide-react";
import * as d3 from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";

const SOURCE_COLORS = {
  seed: "#A142F4",      // purple
  webpage: "#4285F4",   // blue
  pdf: "#EA4335",       // red
  youtube: "#fa7b17",   // orange
  social: "#34a853",    // green
};

// Friendly labels for the legend (capitalize / abbreviate types)
const SOURCE_TYPE_LABELS = {
  seed: "Seed",
  webpage: "Web",
  pdf: "PDF",
  youtube: "Video",
  social: "Social",
};

function getStageMetrics(sources, visibleIds = null) {
  const seedSource = sources.find((s) => s.source_type === "seed");
  // Errored sources are treated as if they don't exist — they don't appear
  // in the sidebar, the formation status line ignores them, and the stage
  // logic below treats them as "settled" so they don't block progression.
  const discoveredSources = sources.filter(
    (s) => s.source_type !== "seed" && s.status !== "error",
  );

  // visibleDiscoveredCount = how many discovered sources have actually
  // popped into the graph yet (the stagger animation reveals them one at
  // a time at 400ms intervals). Stage 2's progress bar follows this
  // *visual* count, not the raw data count, so the bar finishes filling
  // exactly when the last node lands on screen.
  const visibleDiscoveredCount = visibleIds
    ? discoveredSources.filter((s) => visibleIds.has(s.id)).length
    : discoveredSources.length;

  return {
    seedReady: seedSource?.status === "ready",
    discoveredCount: discoveredSources.length,
    visibleDiscoveredCount,
    discoveredReady: discoveredSources.filter((s) => s.status === "ready").length,
    hasDiscovered: discoveredSources.length > 0,
    allDiscoveredReady: discoveredSources.every((s) => s.status === "ready"),
    anyDiscoveredProcessing: discoveredSources.some((s) => s.status === "processing"),
    anyDiscoveredCrawling: discoveredSources.some((s) => s.status === "crawling"),
    // Counts (not just booleans) so the stage-progress helper can compute
    // a fractional fill for the vertical progress bars.
    anyDiscoveredCrawlingCount: discoveredSources.filter((s) => s.status === "crawling").length,
    anyDiscoveredProcessingCount: discoveredSources.filter((s) => s.status === "processing").length,
  };
}

export function computeStage(sources, _edges) {
  if (!sources.length) return 1;

  const {
    seedReady,
    hasDiscovered,
    anyDiscoveredProcessing,
    anyDiscoveredCrawling,
  } = getStageMetrics(sources);

  // Stage 1 — Seed still being processed.
  if (!seedReady) return 1;

  // Stage 4 — Analysing content (summarising). Edges are already computed
  // by the keyword-overlap pass during this stage, so there's no separate
  // "Building graph" stage anymore.
  if (anyDiscoveredProcessing && !anyDiscoveredCrawling) return 4;

  // Stage 3 — Pages being fetched (covers crawling+processing overlap too).
  if (anyDiscoveredCrawling) return 3;

  // Stage 2 — Discovering sources, or discovered sources queued.
  if (hasDiscovered) return 2;
  if (seedReady) return 2;

  return 1;
}

export function statusLine(stage, sources) {
  const { discoveredCount, discoveredReady, hasDiscovered } = getStageMetrics(sources);
  switch (stage) {
    case 1:
      return "Processing seed document…";
    case 2:
      return hasDiscovered
        ? `Found ${discoveredCount} related source${discoveredCount !== 1 ? "s" : ""}`
        : "Finding related sources…";
    case 3:
      return `Reading sources… ${discoveredReady} of ${discoveredCount} ready`;
    case 4:
      return `Analysing content… ${discoveredReady} of ${discoveredCount} ready`;
    default:
      return "";
  }
}

// Returns 0-1, how far along a given stage is right now, derived from real
// source-status counts. Status counts only update when the polling hook
// brings fresh notebook state — so this signal is *discrete* (jumps when
// counts change, flat in between). The StageTracker combines this with a
// time-based baseline so the visible bar advances smoothly even when the
// real signal is stuck.
function stageProgress(stageNum, metrics) {
  switch (stageNum) {
    case 1:
      return metrics.seedReady ? 1 : 0;
    case 2:
      // Sync to visual state: the bar fills as discovered nodes pop into
      // the graph, not when the data first lands. Without this sync, the
      // bar would snap to 100% at t=0 of discovery while nodes are still
      // staggering in over the next 2-3 seconds. With the sync, bar fill
      // and node appearance animate together.
      if (!metrics.hasDiscovered) return 0;
      if (metrics.discoveredCount === 0) return 0;
      return Math.min(1, metrics.visibleDiscoveredCount / metrics.discoveredCount);
    case 3:
      if (metrics.discoveredCount === 0) return 0;
      return Math.min(
        1,
        (metrics.discoveredReady +
          metrics.anyDiscoveredCrawlingCount +
          metrics.anyDiscoveredProcessingCount) /
          metrics.discoveredCount,
      );
    case 4:
      if (metrics.discoveredCount === 0) return 0;
      return Math.min(1, metrics.discoveredReady / metrics.discoveredCount);
    default:
      return 0;
  }
}

// Expected duration per stage in ms — used by the time-based baseline so
// the bar always creeps even when status counts haven't ticked yet. These
// are calibrated to the typical wall-clock observed during testing; the
// bar just needs to feel-right, it doesn't have to be exact.
const STAGE_EXPECTED_MS = {
  1: 8000,    // seed crawl + summary ≈ 5–10s
  2: 18000,   // discovery: one big Gemini grounded call ≈ 12–20s
  3: 30000,   // reading: parallel crawls, dominated by slowest ≈ 20–40s
  4: 25000,   // analysing: parallel summaries ≈ 15–30s
};

// Cap time-based interpolation at 92% so it never pre-empts the moment
// when a stage actually completes. The "snap to 100%" transition is what
// makes completion feel definite.
const TIME_PROGRESS_CEILING = 0.92;

function StageTracker({ currentStage, highestStage, metrics }) {
  // Track the wall-clock moment each stage first becomes active. Used to
  // compute time-based progress (the baseline that creeps the bar between
  // status updates so it feels real-time instead of jumping in chunks).
  const stageStartRef = useRef({});
  const [now, setNow] = useState(() => Date.now());

  // Tick at 10Hz to redraw the bar smoothly while waiting on backend events.
  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(interval);
  }, []);

  // Mark stage start time the first time we see a stage become active.
  useEffect(() => {
    if (currentStage && !stageStartRef.current[currentStage]) {
      stageStartRef.current[currentStage] = Date.now();
    }
  }, [currentStage]);

  // Time-based progress for a stage: 0 if the stage hasn't started, capped
  // at TIME_PROGRESS_CEILING (92%) regardless of elapsed time so the bar
  // can't pretend to be done before it actually is.
  const timeProgress = (stageNum) => {
    const startTime = stageStartRef.current[stageNum];
    if (!startTime) return 0;
    const expected = STAGE_EXPECTED_MS[stageNum] || 10000;
    const elapsed = now - startTime;
    return Math.min(TIME_PROGRESS_CEILING, elapsed / expected);
  };

  // Combined progress: real status-derived progress wins when it leads;
  // time-based baseline keeps the bar moving when status hasn't ticked.
  const combinedProgress = (stageNum) => {
    const real = stageProgress(stageNum, metrics);
    const timed = timeProgress(stageNum);
    // If the real signal has hit 100%, snap immediately — that's the
    // definitive completion moment. Otherwise pick whichever is higher.
    if (real >= 1) return 1;
    return Math.max(real, timed);
  };

  // Four stages, no "Building graph" — keyword-overlap edges land alongside
  // the analysis pass, so a separate graph-building step would just flash on
  // screen for milliseconds.
  const stages = [
    { title: "Processing seed", desc: "Parsing initial document" },
    {
      title: "Sources identified",
      desc:
        metrics.discoveredCount > 0
          ? `Found ${metrics.discoveredCount} related sources`
          : "Searching web…",
    },
    {
      title: "Reading sources",
      desc:
        metrics.discoveredReady > 0
          ? `Read ${metrics.discoveredReady} of ${metrics.discoveredCount}`
          : "Pending",
    },
    { title: "Analysing content", desc: "Extracting concepts and relationships" },
  ];

  return (
    <div className="flex h-full flex-col">
      {stages.map((stage, i) => {
        const stageNum = i + 1;
        const active = stageNum === currentStage;
        const isDone = stageNum < currentStage;

        // Progress that fills the connector AFTER this stage's bullet.
        // Past stages = 100%, future = 0%, active = live (combinedProgress
        // blends real status-derived progress with a time-based baseline so
        // the bar advances smoothly even when no source statuses change).
        let connectorProgress = 0;
        if (isDone) connectorProgress = 1;
        else if (active) connectorProgress = combinedProgress(stageNum);

        return (
          <div key={stageNum} className="relative flex flex-1">
            {/* Vertical connector — now a real progress bar. The grey track
                is full-height; the green fill grows from the top down as
                the active stage advances. */}
            {i !== stages.length - 1 && (
              <div className="absolute left-[11px] top-[28px] bottom-0 w-[2px] overflow-hidden rounded-full bg-[#f0f4f9]">
                <div
                  className="absolute left-0 right-0 top-0 bg-[#34a853]"
                  style={{
                    height: `${connectorProgress * 100}%`,
                    transition: "height 600ms cubic-bezier(0.22, 1, 0.36, 1)",
                  }}
                />
              </div>
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
  // Track whether we're at the lg+ breakpoint so the stage-tracker
  // closing animation can pick the right axis (width on desktop, height
  // on mobile where the layout stacks).
  const [isLargeViewport, setIsLargeViewport] = useState(
    typeof window !== "undefined" && window.innerWidth >= 1024,
  );
  useEffect(() => {
    const update = () => setIsLargeViewport(window.innerWidth >= 1024);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  const simulationRef = useRef(null);
  const liveNodeMapRef = useRef(new Map());
  const enteringNodeIds = useRef(new Set());
  const edgeAnimStates = useRef(new Map()); // edgeKey -> { offset, animating }
  const [tick, setTick] = useState(0);
  const size = useSize(wrapRef);

  const [highestStage, setHighestStage] = useState(1);
  // isCompleting is set to true when the notebook hits ready/error. It
  // triggers the closing choreography (sweeps fade out, edges pulse, the
  // ready strip slides up from the bottom). The strip remains visible
  // until App.jsx swaps to the main view, so we don't auto-clear it.
  const [isCompleting, setIsCompleting] = useState(false);
  const [readyStripVisible, setReadyStripVisible] = useState(false);
  const readyFiredRef = useRef(false);

  const currentStage = useMemo(() => computeStage(sources, edges), [sources, edges]);
  const displayStage = Math.max(highestStage, currentStage);

  useEffect(() => {
    setHighestStage((prev) => Math.max(prev, currentStage));
  }, [currentStage]);

  // Closing choreography. Triggered exactly once when the notebook flips
  // to ready/error.
  //
  //   t=0      sweeps start fading out, simulation cools, edges thicken
  //   t=400    ready strip mounts; one frame later we toggle visibility
  //            so the slide-up + fade-in transition fires
  //   App.jsx waits 1.8s before unmounting FormationScreen, so the strip
  //   gets ~1.4s of "look at me" time before the main view appears.
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

      // Cool the d3 simulation — let nodes settle into final positions.
      if (simulationRef.current) {
        try {
          simulationRef.current.alphaTarget(0).alpha(0).stop();
        } catch {
          // simulation may already be stopped; ignore
        }
      }

      setIsCompleting(true);
      window.setTimeout(() => {
        setReadyStripVisible(true);
      }, 400);
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
      // Cap the *total* stagger window at ~2s regardless of how many
      // nodes are entering. With 12 sources the old 400ms-each stagger
      // pushed the last node 4.8s into the future, leaving Stage 2's
      // (now visual-state-synced) progress bar dragging far behind the
      // actual discovery moment. 2s feels like the goldilocks zone:
      // long enough to read as "they're coming in one at a time," short
      // enough that the bar reaches 100% while discovery still feels
      // recent.
      const TOTAL_STAGGER_MS = 2000;
      const perItemMs = Math.min(400, TOTAL_STAGGER_MS / newlyVisible.length);
      newlyVisible.forEach((id, index) => {
        setTimeout(() => {
          setStaggerVisibleIds((prev) => {
            const next = new Set(prev);
            next.add(id);
            return next;
          });
        }, index * perItemMs);
      });
    }
  }, [sources, staggerVisibleIds]);

  const { nodes, links } = useMemo(() => {
    const visibleSources = sources.filter(
      // Hide errored sources completely — never let them render as orphan
      // dots in the graph. Matches the same filter in DocumentWeb / SourcesPanel.
      (s) => staggerVisibleIds.has(s.id) && s.status !== "error",
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

  // Auto-fit viewBox: compute the bounding box of currently-rendered nodes
  // and animate the SVG's user-coordinate window to wrap them with padding.
  // The simulation runs in raw pixel coords centred near (size.width/2,
  // size.height/2); without this, nodes that the force layout pushes outside
  // that window get clipped by the SVG viewport.
  const VIEWBOX_PADDING = 60;
  const VIEWBOX_LABEL_PAD = 30; // for the text label below each node
  const VIEWBOX_MIN_SIZE = 480;
  const VIEWBOX_LERP = 0.18; // 0=no movement, 1=instant snap

  const [viewBox, setViewBox] = useState(null);

  useEffect(() => {
    if (!size.width || !size.height) return;
    const nodeArr = Array.from(liveNodeMapRef.current.values());
    if (!nodeArr.length) {
      // No nodes yet — match the container's pixel size as the initial frame.
      setViewBox((prev) => prev || { x: 0, y: 0, w: size.width, h: size.height });
      return;
    }

    // Tight bbox around all nodes (radius + label space included).
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodeArr) {
      const x = n.x ?? size.width / 2;
      const y = n.y ?? size.height / 2;
      minX = Math.min(minX, x - n.r - 8);
      maxX = Math.max(maxX, x + n.r + 8);
      minY = Math.min(minY, y - n.r - 8);
      maxY = Math.max(maxY, y + n.r + VIEWBOX_LABEL_PAD);
    }

    let contentW = (maxX - minX) + VIEWBOX_PADDING * 2;
    let contentH = (maxY - minY) + VIEWBOX_PADDING * 2;
    contentW = Math.max(contentW, VIEWBOX_MIN_SIZE);
    contentH = Math.max(contentH, VIEWBOX_MIN_SIZE);

    // Maintain the container's aspect ratio so SVG doesn't squash content.
    const containerAspect = size.width / size.height;
    const contentAspect = contentW / contentH;
    if (contentAspect > containerAspect) {
      contentH = contentW / containerAspect;
    } else {
      contentW = contentH * containerAspect;
    }

    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const target = {
      x: cx - contentW / 2,
      y: cy - contentH / 2,
      w: contentW,
      h: contentH,
    };

    setViewBox((prev) => {
      if (!prev) return target;
      // Damped lerp toward target — produces a smooth zoom-out as new nodes
      // appear at the periphery.
      return {
        x: prev.x + (target.x - prev.x) * VIEWBOX_LERP,
        y: prev.y + (target.y - prev.y) * VIEWBOX_LERP,
        w: prev.w + (target.w - prev.w) * VIEWBOX_LERP,
        h: prev.h + (target.h - prev.h) * VIEWBOX_LERP,
      };
    });
  }, [tick, size.width, size.height]);

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
        {/* Stage tracker Panel — recedes leftward (width → 0) once the
            notebook hits ready, so the graph panel can grow to fill the
            row before the App swaps to the main view. */}
        <div
          className="flex w-full flex-col overflow-hidden rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm shrink-0 px-8 py-7 lg:w-[340px]"
          style={{
            // While completing, animate width → 0 (lg+) or maxHeight → 0
            // (mobile). When not completing, leave inline width undefined
            // so the Tailwind `lg:w-[340px]` / `w-full` classes take over.
            width: isCompleting && isLargeViewport ? 0 : undefined,
            maxHeight: isCompleting && !isLargeViewport ? 0 : undefined,
            paddingLeft: isCompleting ? 0 : undefined,
            paddingRight: isCompleting ? 0 : undefined,
            paddingTop: isCompleting ? 0 : undefined,
            paddingBottom: isCompleting ? 0 : undefined,
            opacity: isCompleting ? 0 : 1,
            transition:
              "width 600ms cubic-bezier(0.22, 1, 0.36, 1), max-height 600ms cubic-bezier(0.22, 1, 0.36, 1), padding 600ms cubic-bezier(0.22, 1, 0.36, 1), opacity 400ms ease-out",
          }}
        >
          <p className="mb-8 flex items-center gap-2 text-base font-medium text-[#1f1f1f] whitespace-nowrap">
            <Sparkles className="h-5 w-5 text-[#0b57d0] shrink-0" />
            Discovery Process
          </p>
          <div className="flex-1 overflow-y-auto no-scrollbar min-h-0">
            <StageTracker
              currentStage={displayStage}
              highestStage={highestStage}
              metrics={getStageMetrics(sources, staggerVisibleIds)}
            />
          </div>
        </div>

        {/* Graph area Panel */}
        <div ref={wrapRef} className="relative flex-1 rounded-[2rem] border border-[#e0e2e0] bg-white shadow-sm overflow-hidden">
          {size.width > 0 && (
            <svg
              className="h-full w-full"
              viewBox={
                viewBox
                  ? `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`
                  : `0 0 ${size.width} ${size.height}`
              }
              preserveAspectRatio="xMidYMid meet"
            >
              <defs>
                <filter id="formation-shadow" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.12" />
                </filter>
              </defs>
              <g className={isCompleting ? "graph-completing" : ""}>
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
                  const isSeed = node.source_type === "seed";
                  const isReady = node.status === "ready" || isSeed;
                  const isAnalyzing = node.status === "processing";
                  const isFetching = node.status === "crawling";

                  // The buffering circle is now drawn around EVERY non-seed
                  // node throughout the formation, not just the one being
                  // fetched right now. Speed and opacity vary slightly by
                  // status so the eye still picks out which one is "active":
                  //   crawling/processing → faster, higher contrast sweep
                  //   pending or ready    → slower, fainter ambient sweep
                  // Once the whole notebook is ready (notebook.status flips),
                  // the formation screen unmounts and the sweeps go away.
                  const showSweep = !isSeed;
                  const sweepIsActive = isFetching || isAnalyzing;

                  // Node visual state classes:
                  //   .node-entering — pop-in scale animation when first added
                  //   .node-fetching — slow pulse while content is being fetched
                  //   .node-analyzing — faster pulse + halo while summarising
                  const cls = [
                    isEntering ? "node-entering" : "",
                    isFetching ? "node-fetching" : "",
                    isAnalyzing ? "node-analyzing" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");

                  // Reading sweep: a 90° arc that rotates around the node.
                  // Built from a stroke-dasharray pattern (short visible
                  // segment, long invisible gap) on a circle slightly larger
                  // than the node. transform-box: fill-box pivots the
                  // rotation around the circle's own center.
                  const sweepRadius = node.r + 5;
                  const sweepCircumference = 2 * Math.PI * sweepRadius;
                  const sweepArcLength = sweepCircumference * 0.22;

                  return (
                    <g
                      key={node.id}
                      className={cls}
                      style={{ transformOrigin: `${node.x}px ${node.y}px` }}
                    >
                      {/* Buffering sweep — visible on every non-seed node
                          while the formation is in progress. Active sources
                          get a brighter, faster sweep; pending and ready
                          sources still get an ambient slow sweep so the
                          whole graph reads as "still forming". */}
                      {showSweep && (
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={sweepRadius}
                          fill="none"
                          stroke={color}
                          strokeWidth={sweepIsActive ? 2.5 : 2}
                          strokeOpacity={sweepIsActive ? 0.9 : 0.45}
                          strokeLinecap="round"
                          strokeDasharray={`${sweepArcLength} ${sweepCircumference - sweepArcLength}`}
                          className={sweepIsActive ? "reading-sweep reading-sweep-fast" : "reading-sweep reading-sweep-slow"}
                          style={{
                            transformBox: "fill-box",
                            transformOrigin: "center",
                          }}
                        />
                      )}

                      {/* Halo: rendered behind the main circle, only visible
                          while a node is in the analyzing state. Soft pulse
                          to draw the eye to active processing. */}
                      {isAnalyzing && (
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={node.r + 6}
                          fill={color}
                          fillOpacity={0.18}
                          className="node-halo"
                        />
                      )}
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.r}
                        fill={color}
                        fillOpacity={isReady ? 0.96 : 0.58}
                        stroke="#ffffff"
                        strokeWidth={2}
                        filter="url(#formation-shadow)"
                      />
                      <text
                        x={node.x}
                        y={node.y + node.r + 16}
                        textAnchor="middle"
                        fontSize="11"
                        fill="#1f1f1f"
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

          {/* Color legend — pill-shaped overlay so it pops against the
              white panel. Only renders types actually present in this
              notebook so it doesn't get crowded. */}
          {(() => {
            const presentTypes = new Set(
              sources.filter((s) => s.status !== "error").map((s) => s.source_type),
            );
            const items = Object.entries(SOURCE_COLORS).filter(([type]) =>
              presentTypes.has(type),
            );
            if (items.length === 0) return null;
            return (
              <div className="absolute bottom-6 left-6 z-10 flex items-center gap-3 rounded-full border border-[#e0e2e0] bg-white/85 px-4 py-1.5 shadow-sm backdrop-blur">
                {items.map(([type, color]) => (
                  <span
                    key={type}
                    className="flex items-center gap-1.5 text-xs text-[#5f6368]"
                  >
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    {SOURCE_TYPE_LABELS[type] || type}
                  </span>
                ))}
              </div>
            );
          })()}

          <style>{`
            @keyframes ghost-march { to { stroke-dashoffset: -26; } }
            .ghost-edge { animation: ghost-march 1.4s linear infinite; }

            /* Reading-sweep: a partial arc rotates around each non-seed
               node, suggesting "still being read / connected". Two speeds:
               a brisk active sweep for sources currently being fetched or
               analysed, and a slower ambient sweep for everything else
               (pending or ready). transform-box: fill-box anchors the
               rotation to the circle's own center. */
            @keyframes reading-sweep {
              to { transform: rotate(360deg); }
            }
            .reading-sweep-fast {
              animation: reading-sweep 1.4s linear infinite;
            }
            .reading-sweep-slow {
              animation: reading-sweep 3.4s linear infinite;
            }

            /* Subtle dim on the main circle while fetching, so the bright
               arc above it stands out — but kept gentler than before so
               it doesn't compete with the sweep. */
            @keyframes node-fetch-pulse {
              0%, 100% { opacity: 0.62; }
              50%      { opacity: 0.82; }
            }
            .node-fetching > circle:not(.reading-sweep) {
              animation: node-fetch-pulse 1.6s ease-in-out infinite;
            }

            @keyframes node-analyze-pulse {
              0%, 100% { opacity: 0.62; }
              50%      { opacity: 0.95; }
            }
            .node-analyzing > circle:not(.node-halo) { animation: node-analyze-pulse 1.0s ease-in-out infinite; }

            @keyframes node-halo-grow {
              0%, 100% { opacity: 0.05; transform-origin: center; }
              50%      { opacity: 0.32; }
            }
            .node-halo { animation: node-halo-grow 1.4s ease-in-out infinite; }

            /* Closing choreography. When .graph-completing is on the root
               group:
                 - all reading-sweep arcs fade out over 600ms
                 - all halos retract
                 - edge lines briefly thicken (a "the connections are now
                   meaningful" pulse) then settle. */
            .graph-completing .reading-sweep-fast,
            .graph-completing .reading-sweep-slow {
              animation-play-state: paused;
              opacity: 0;
              transition: opacity 600ms ease-out;
            }
            .graph-completing .node-halo {
              animation-play-state: paused;
              opacity: 0;
              transition: opacity 600ms ease-out;
            }
            @keyframes graph-edge-pulse {
              0%   { stroke-width: 1; }
              50%  { stroke-width: 2.6; }
              100% { stroke-width: 1; }
            }
            .graph-completing line:not(.ghost-edge) {
              animation: graph-edge-pulse 700ms ease-in-out 1;
            }
          `}</style>

          {/* Ready strip — anchored to the bottom of the graph panel
              (rather than the previous centered overlay that covered the
              nodes). The gradient above it fades node labels softly into
              the strip's background instead of clipping them. */}
          {isCompleting && (
            <>
              {/* Soft fade above the strip so node labels near the bottom
                  of the canvas don't visually cut through the edge of the
                  ready card. */}
              <div
                className="pointer-events-none absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-white via-white/85 to-transparent"
                style={{
                  opacity: readyStripVisible ? 1 : 0,
                  transition: "opacity 400ms ease-out",
                }}
              />
              <div
                className="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2 transform"
                style={{
                  transform: readyStripVisible
                    ? "translate(-50%, 0)"
                    : "translate(-50%, 16px)",
                  opacity: readyStripVisible ? 1 : 0,
                  transition: "transform 460ms cubic-bezier(0.22, 1, 0.36, 1), opacity 400ms ease-out",
                }}
              >
                <div className="flex items-center gap-3 rounded-full border border-[#e0e2e0] bg-white px-5 py-2.5 shadow-md">
                  <Sparkles className="h-4 w-4 text-[#0b57d0]" />
                  <span className="text-sm font-medium text-[#1f1f1f]">
                    Knowledge graph ready
                  </span>
                  <span className="text-sm text-[#5f6368]">
                    · {sources.filter((s) => s.status === "ready").length} source
                    {sources.filter((s) => s.status === "ready").length !== 1 ? "s" : ""}
                    {totalEdges > 0
                      ? ` · ${totalEdges} connection${totalEdges !== 1 ? "s" : ""}`
                      : ""}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
