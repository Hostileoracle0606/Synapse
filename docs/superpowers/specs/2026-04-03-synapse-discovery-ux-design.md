# Synapse Discovery UX & Graph Interaction Design

**Date:** 2026-04-03
**Scope:** Formation screen (ingestion flow polish) + Tier 1 graph interaction fixes
**Status:** Approved — ready for implementation planning

---

## Problem Statement

The current ingestion flow is abrupt across five distinct failure points:
1. The instant jump from `SeedInput` → main 3-panel layout (no transition)
2. Arriving at an empty graph immediately after clicking "Build knowledge base"
3. No sense of pipeline progress — status badge just says "processing"
4. Nodes and edges appear silently with no animation or acknowledgment
5. No "done" signal when the graph is ready to use

The core metaphor of Synapse is **knowledge discovery** — sources being found and connected organically. The UI must reinforce this. Everything that happens during ingestion should feel like watching something grow, not waiting for a page to load.

---

## Design Decisions (from visual exploration)

| Decision | Choice | Rationale |
|---|---|---|
| Formation experience structure | Dedicated fullscreen formation screen | Focused, no competing UI while the graph builds |
| Visual aesthetic | Light & minimal (matches existing app) | Consistent; not a departure from the design system |
| Transition to main app | Graph stays put, panels slide in from sides | Spatially coherent; graph continuity is preserved |
| Node entrance animation | Organic drift (translate + fade) | Feels like sources floating into position, not popping |
| Edge entrance animation | Draw on one at a time (stroke-dashoffset) | Reinforces the "connection forming" metaphor |

---

## Part 1 — Formation Screen

### Component: `FormationScreen`

A new full-viewport component shown whenever `notebookId` is set but `notebook.status !== "ready"`. Replaces the immediate render of the 3-panel layout.

**Routing logic in `App.jsx`:**
```
notebookId absent          → <SeedInput />
notebookId set, not ready  → <FormationScreen />
notebookId set, ready      → <main layout />
```

The transition from `FormationScreen` to the main layout is triggered by `notebook.status === "ready"` being observed by the polling hook.

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Synapse Notebook                      [title]       │  ← thin top bar, logo + notebook title
├──────────────────┬──────────────────────────────────┤
│                  │                                   │
│  Stage tracker   │      Force graph (growing)        │
│  (left, ~220px)  │      (center, fills remaining)    │
│                  │                                   │
│  ① Seed ✓        │          ●  (seed node)           │
│  ② Sources ✓     │        ↗   ↘                      │
│  ③ Crawling ●    │      ●       ●  (drift in…)       │
│  ④ Analysing     │                                   │
│  ⑤ Connections   │   Crawling pages… 4 of ~8 found   │  ← live status line
│                  │                                   │
└──────────────────┴──────────────────────────────────┘
```

- No `SourcesPanel`, no `ChatPanel`, no `Header` action buttons during formation
- Background: same radial-gradient as main app (`#f4f8fb → #eef3f8`)

### Stage Tracker

Five stages inferred entirely from existing poll data — **no backend changes required**.

| # | Label | Done when |
|---|---|---|
| 1 | Seed processed | seed source (`source_type === "seed"`) has `status === "ready"` |
| 2 | Sources found | `sources.length > 1` |
| 3 | Crawling pages | any source has `status === "crawling"` (or stage 2 done and stage 4 not yet) |
| 4 | Analysing content | any source has `status === "processing"` |
| 5 | Building connections | all sources are `"ready"` AND `edges.length === 0` |
| ✓ | Done | `notebook.status === "ready"` |

Stage 3 and 4 overlap in backend execution (concurrent crawl+process pipeline). The tracker shows the highest reached stage, not a strict sequential gate. Once a stage is marked done it stays done.

**Visual states per step:**
- `done`: green filled dot + strikethrough-style muted label
- `active`: blue pulsing dot + bold label + "…" suffix
- `pending`: grey empty dot + muted label

### Live Status Line

Single line of text below the graph, updated on each poll:

- Stage 1: _"Processing seed document…"_
- Stage 2: _"Found {n} related sources"_
- Stage 3: _"Crawling pages… {ready} of {total} sources fetched"_
- Stage 4: _"Analysing content… {ready} of {total} sources ready"_
- Stage 5: _"Building knowledge connections…"_

Derived from `sources` array in poll response. No new API fields needed.

### Graph During Formation

The formation screen embeds its own D3 force simulation (same setup as `DocumentWeb`). As the polling hook delivers new sources, nodes are added to the simulation incrementally — same logic as `DocumentWeb`'s existing incremental update effect.

**Node entrance animation — organic drift:**
- New nodes enter with CSS class `node-entering`
- Keyframe: `transform: translate(-15px, 8px) scale(0.4); opacity: 0` → `transform: translate(0,0) scale(1); opacity: 1`
- Duration: 600ms, `ease-out` easing
- Applied via a `enteringNodeIds` set that is cleared after the transition completes

**Edge entrance animation — draw on:**
- Edges use SVG `stroke-dasharray` / `stroke-dashoffset` technique
- Each new edge animates from `dashoffset = length` → `dashoffset = 0` over 500ms
- Edges are added one at a time with a 120ms stagger between each
- Triggered when `edges` array grows in the poll response

**Physics during formation:**
- Simulation runs normally throughout (force layout, collision, charge, link)
- `alphaDecay: 0.03` (unchanged) — nodes settle naturally between arrivals
- When new nodes/edges arrive, `simulation.alpha(0.3).restart()` as today

### "Done" Moment

When `notebook.status === "ready"` is first observed:

1. A brief overlay fades in over the settled graph (not blocking the graph, sits on top):
   ```
   ✦  Knowledge graph ready
      8 sources · 12 connections
   ```
   - Fade in: 300ms
   - Hold: 1500ms
   - Fade out: 300ms

2. During the fade-out, begin the transition to the main layout.

No button required. The user is watching — let it flow automatically.

### Transition to Main Layout

**Node position continuity:**

`FormationScreen` accepts an `onReady(positions)` callback prop. When `notebook.status === "ready"` is first observed, it captures `liveNodeMapRef.current` (the settled D3 node positions) and calls `onReady(positions)` before beginning the "done" overlay. `App` stores this as `initialNodePositions: Map<id, {x, y, vx, vy}>` in state and passes it to `DocumentWeb`. `DocumentWeb` accepts this as a prop and seeds the simulation with pre-positioned nodes at `alpha(0)` (frozen). The graph appears settled immediately without re-animating.

**Panel reveal animation:**

When the main layout mounts:
- `SourcesPanel`: starts at `width: 0; opacity: 0` → `width: 20rem; opacity: 1` — 400ms `ease-out`
- `ChatPanel`: starts at `width: 0; opacity: 0` → `width: 380px; opacity: 1` — 400ms `ease-out`, 80ms delay
- `DocumentWeb`: no animation — just appears in the now-smaller center column
- Overall layout: 300ms crossfade from formation screen

The CSS transitions use `overflow: hidden` on the panels during reveal to prevent content bleed.

**Implementation note:** This requires `SourcesPanel` and `ChatPanel` to accept a `revealing` prop that applies the initial collapsed styles, controlled by a `layoutRevealing` boolean in `App` state that is set to `false` after the transition completes (via `setTimeout` or `onTransitionEnd`).

---

## Part 2 — Tier 1 Graph Interaction Fixes

All changes confined to `DocumentWeb.jsx` unless noted.

### 1. Drag-to-Pan + Scroll-to-Zoom

Add pointer event handlers directly to the SVG element (not the inner `<g>`):

```
onPointerDown → record start position, setPointerCapture
onPointerMove → if dragging, delta transform ref {x, y}, trigger re-render
onPointerUp/Cancel → clear drag state
onWheel → adjust transform ref {k}, same min/max bounds as existing buttons (0.45–2.6)
```

`transformRef.current` already holds `{x, y, k}` — the drag handler just updates `x` and `y`. Scroll updates `k`. Both call `setTick` to re-render.

Zoom-to-cursor for scroll: compute the cursor position in graph space before and after scaling, adjust `x`/`y` to keep the cursor point stationary.

The existing zoom buttons (`+`, `-`, reset) continue to work unchanged.

### 2. Node Neighborhood Highlighting

When `selectedSource` is non-null, compute:
```
connectedNodeIds = Set of node IDs directly connected to selectedSource via any edge
```

Apply during render:
- **Selected node**: full opacity, existing selection ring
- **Connected nodes**: full opacity (`0.96`)
- **Unconnected nodes**: `opacity: 0.18`
- **Connected edges**: full stroke opacity (`0.22 + sim * 0.5`, unchanged)
- **Unconnected edges**: `opacity: 0.06`

When `selectedSource` is null, all nodes and edges render at full opacity (current behavior).

`connectedNodeIds` is computed with `useMemo` depending on `[selectedSource, links]`.

### 3. Edge Labels Without Alpha Gate

Remove the `alphaRef.current < 0.1` condition from the edge label render block.

Labels show whenever `hoveredEdge` is non-null. If the graph is still settling when the user hovers, the label moves with the midpoint — this is acceptable and feels alive rather than broken.

### 4. Node Hover Tooltip

Add `hoveredNode` state (`null | node`).

On each node `<g>`:
- `onMouseEnter` → `setHoveredNode(node)`
- `onMouseLeave` → `setHoveredNode(null)`

Render a tooltip `<g>` when `hoveredNode` is set, positioned at `{x: node.x, y: node.y - node.r - 12}` (just above the node) in SVG space (inside the transform group, so zoom/pan apply automatically):

```
┌─────────────────────────┐
│  Full title here        │
│  webpage  ● ready       │
└─────────────────────────┘
```

- White background rect with `rx=8`, subtle shadow via SVG `filter` (or CSS `drop-shadow`)
- Max width: 200px — title wraps to two lines if needed
- Source type badge using the existing `SOURCE_COLORS` palette
- Status dot matching `sourceTone` colors

Do not show tooltip for the currently selected node (popover already covers it).

### 5. Node Type Legend

Add a small legend element to `DocumentWeb`, positioned bottom-left (opposite the zoom controls, bottom-right):

```
● Seed   ● Webpage   ● PDF
```

- Pill-shaped container, same styling as the "Document web" label (top-left): `bg-white/80 border border-[#e0e2e0] rounded-full px-4 py-1.5 backdrop-blur shadow-sm`
- Three inline items: colored dot + label text, `text-xs text-[#5f6368]`
- Always visible, no interaction

---

## Out of Scope

- No backend changes
- No changes to `Header`, `SourceComposer`, `SeedInput`
- No mobile layout changes
- No dark mode
- No minimap, search, or layout switching (Tier 2+)

---

## Files Affected

| File | Change |
|---|---|
| `src/App.jsx` | Add `FormationScreen` routing, `initialNodePositions` state, `layoutRevealing` state |
| `src/components/FormationScreen.jsx` | New component |
| `src/components/DocumentWeb.jsx` | Tier 1 fixes: pan/zoom, highlight, tooltip, legend, edge label gate removal; accept `initialNodePositions` prop |
| `src/components/SourcesPanel.jsx` | Accept `revealing` prop for slide-in animation |
| `src/components/ChatPanel.jsx` | Accept `revealing` prop for slide-in animation |
| `src/index.css` | Add `node-entering` keyframe animation |
