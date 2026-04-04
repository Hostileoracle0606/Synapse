import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeAll, afterAll } from "vitest";

// ---------------------------------------------------------------------------
// Global browser API stubs needed by jsdom
// ---------------------------------------------------------------------------

// ResizeObserver is not implemented in jsdom
beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

// ---------------------------------------------------------------------------
// Mock d3-force
//
// The real d3 simulation runs asynchronously and relies on requestAnimationFrame
// which jsdom doesn't fully support. We replace it with a synchronous stub that:
//   - stores nodes/links
//   - fires the "tick" callback once immediately with alpha = 0 (settled)
//   - returns alpha = 0 so the label-on-hover gate (alphaRef.current < 0.1) passes
// ---------------------------------------------------------------------------

vi.mock("d3-force", () => {
  // Minimal chainable stub for forceLink
  const makeLinkForce = () => {
    const self = {
      _links: [],
      id: () => self,
      distance: () => self,
      links: (l) => {
        if (l !== undefined) self._links = l;
        return self;
      },
    };
    return self;
  };

  // Minimal chainable stub for forceSimulation
  const makeSimulation = (initialNodes = []) => {
    let _nodes = initialNodes;
    let _linkForce = makeLinkForce();
    let _tickCb = null;
    let _forces = { link: _linkForce };

    const sim = {
      nodes: (n) => {
        if (n !== undefined) {
          _nodes = n;
          return sim;
        }
        return _nodes;
      },
      force: (name, f) => {
        if (f !== undefined) {
          _forces[name] = f;
          return sim;
        }
        return _forces[name];
      },
      alphaDecay: () => sim,
      alpha: (v) => {
        if (v !== undefined) return sim;
        // Always report settled so the hover label guard passes
        return 0;
      },
      restart: () => {
        // Fire tick callback so liveNodeMapRef gets populated
        if (_tickCb) _tickCb();
        return sim;
      },
      on: (event, cb) => {
        if (event === "tick") {
          _tickCb = cb;
          // Fire immediately so the component renders with node positions
          cb();
        }
        return sim;
      },
      stop: () => sim,
    };

    return sim;
  };

  return {
    forceSimulation: (nodes) => makeSimulation(nodes),
    forceManyBody: () => ({ strength: () => ({ strength: () => ({}) }) }),
    forceLink: () => makeLinkForce(),
    forceCenter: () => ({}),
    forceCollide: () => ({ radius: () => ({}) }),
  };
});

// Mock NodePopover — it's a separate component not under test here
vi.mock("./NodePopover", () => ({
  default: () => null,
}));

// Mock lucide-react icons to avoid SVG rendering issues in jsdom
vi.mock("lucide-react", () => ({
  Crosshair: () => null,
  Minus: () => null,
  Plus: () => null,
  RotateCcw: () => null,
  Sparkles: () => null,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

import DocumentWeb from "./DocumentWeb";

function makeSource(overrides = {}) {
  return {
    id: "src-1",
    title: "Source One",
    summary: "A summary",
    content: "Some content",
    url: "https://example.com",
    source_type: "webpage",
    status: "ready",
    ...overrides,
  };
}

function makeEdge(overrides = {}) {
  return {
    source_a: "src-1",
    source_b: "src-2",
    similarity: 0.5,
    relationship: "related",
    ...overrides,
  };
}

const DEFAULT_PROPS = {
  sources: [],
  edges: [],
  selectedSource: null,
  onSelectSource: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DocumentWeb", () => {
  // -------------------------------------------------------------------------
  it("test_edge_renders_with_null_similarity: renders line without crashing when similarity is null", () => {
    const sources = [
      makeSource({ id: "src-1", title: "Source One" }),
      makeSource({ id: "src-2", title: "Source Two" }),
    ];
    const edges = [makeEdge({ similarity: null })];

    const { container } = render(
      <DocumentWeb {...DEFAULT_PROPS} sources={sources} edges={edges} />,
    );

    // Should render at least one <line> (the edge)
    // The line may not appear until liveNodeMap is populated via tick, but
    // crucially there should be no crash and no NaN stroke-width.
    const lines = container.querySelectorAll("line");
    for (const line of lines) {
      const sw = parseFloat(line.getAttribute("stroke-width"));
      expect(Number.isNaN(sw)).toBe(false);
    }
  });

  // -------------------------------------------------------------------------
  it("test_edge_renders_with_missing_source: no line rendered for edge with unknown source_a", () => {
    const sources = [makeSource({ id: "src-1", title: "Only Source" })];
    // source_a references a node that doesn't exist
    const edges = [makeEdge({ source_a: "nonexistent-id", source_b: "src-1" })];

    const { container } = render(
      <DocumentWeb {...DEFAULT_PROPS} sources={sources} edges={edges} />,
    );

    // The edge should be filtered out (source_a not in sourceIds), so no <line>
    const lines = container.querySelectorAll("line");
    expect(lines.length).toBe(0);
  });

  // -------------------------------------------------------------------------
  it("test_relationship_label_shows_on_hover: hovering an edge shows its relationship label", async () => {
    const sources = [
      makeSource({ id: "src-1", title: "Source One" }),
      makeSource({ id: "src-2", title: "Source Two" }),
    ];
    const edges = [makeEdge({ relationship: "shares methodology" })];

    const { container } = render(
      <DocumentWeb {...DEFAULT_PROPS} sources={sources} edges={edges} />,
    );

    const lines = container.querySelectorAll("line");
    expect(lines.length).toBeGreaterThan(0);

    // Simulate mouseenter on the first edge line
    fireEvent.mouseEnter(lines[0]);

    // The relationship label text should now appear
    const labelEl = await screen.findByText("shares methodology");
    expect(labelEl).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  it("test_relationship_label_truncated: long relationship label is truncated with ellipsis", async () => {
    const longRelationship = "This is a very long relationship label that exceeds forty chars";
    expect(longRelationship.length).toBeGreaterThan(40);

    const sources = [
      makeSource({ id: "src-1", title: "Source One" }),
      makeSource({ id: "src-2", title: "Source Two" }),
    ];
    const edges = [makeEdge({ relationship: longRelationship })];

    const { container } = render(
      <DocumentWeb {...DEFAULT_PROPS} sources={sources} edges={edges} />,
    );

    const lines = container.querySelectorAll("line");
    expect(lines.length).toBeGreaterThan(0);

    fireEvent.mouseEnter(lines[0]);

    // Find any text element that ends with the ellipsis character
    const textElements = container.querySelectorAll("text");
    const labelEl = Array.from(textElements).find((el) =>
      el.textContent.endsWith("…"),
    );

    expect(labelEl).toBeTruthy();
    // Total display length must be ≤ 41 (40 chars + ellipsis)
    expect(labelEl.textContent.length).toBeLessThanOrEqual(41);
  });

  // -------------------------------------------------------------------------
  it("test_no_crash_on_rerender_with_new_node: adding a third node via rerender does not throw", () => {
    const sources2 = [
      makeSource({ id: "src-1", title: "Source One" }),
      makeSource({ id: "src-2", title: "Source Two" }),
    ];
    const sources3 = [
      ...sources2,
      makeSource({ id: "src-3", title: "Source Three" }),
    ];

    const { rerender } = render(
      <DocumentWeb {...DEFAULT_PROPS} sources={sources2} edges={[]} />,
    );

    expect(() => {
      rerender(<DocumentWeb {...DEFAULT_PROPS} sources={sources3} edges={[]} />);
    }).not.toThrow();
  });
});
