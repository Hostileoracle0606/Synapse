import { describe, expect, it } from "vitest";

import { computeStage, statusLine } from "./FormationScreen";

function makeSource(overrides = {}) {
  return {
    id: "src-1",
    title: "Source",
    source_type: "webpage",
    status: "pending",
    ...overrides,
  };
}

describe("FormationScreen stage inference", () => {
  it("keeps the UI out of stage 1 once the seed document is ready", () => {
    const sources = [
      makeSource({ id: "seed-1", title: "Seed Document", source_type: "seed", status: "ready" }),
    ];

    expect(computeStage(sources, [])).toBe(2);
    expect(statusLine(2, sources, "discovering")).toBe("Finding related sources…");
  });

  it("does not count the seed document as a related source", () => {
    const sources = [
      makeSource({ id: "seed-1", title: "Seed Document", source_type: "seed", status: "ready" }),
      makeSource({ id: "a", status: "pending" }),
      makeSource({ id: "b", status: "pending" }),
    ];

    expect(statusLine(2, sources, "discovering")).toBe("Found 2 related sources");
  });

  it("only advances to analysing content for discovered sources", () => {
    const seedProcessingOnly = [
      makeSource({ id: "seed-1", title: "Seed Document", source_type: "seed", status: "processing" }),
    ];
    const discoveredProcessing = [
      makeSource({ id: "seed-1", title: "Seed Document", source_type: "seed", status: "ready" }),
      makeSource({ id: "a", status: "processing" }),
    ];

    expect(computeStage(seedProcessingOnly, [])).toBe(1);
    expect(computeStage(discoveredProcessing, [])).toBe(4);
  });
});
