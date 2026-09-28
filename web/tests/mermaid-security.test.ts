import mermaid from "mermaid";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const prototypeMarker = "mermaidPrototypePollutionMarker";

beforeEach(() => {
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
  });
  delete (Object.prototype as Record<string, unknown>)[prototypeMarker];
});

afterEach(() => {
  delete (Object.prototype as Record<string, unknown>)[prototypeMarker];
});

describe("Mermaid security regressions", () => {
  it("bounds an XY chart whose axis range has no progress", async () => {
    const diagram = await mermaid.mermaidAPI.getDiagramFromText(`xychart
  x-axis 1 --> 1
  line [1, 2]`);
    const db = diagram.db as unknown as { getDrawableElem: () => unknown[] };

    const drawableElements = db.getDrawableElem();

    expect(drawableElements.length).toBeLessThan(200);
  });

  it("caps an adversarial radar tick count", async () => {
    const diagram = await mermaid.mermaidAPI.getDiagramFromText(`radar-beta
  axis a, b
  curve c {1, 1}
  ticks 1000000000`);
    const db = diagram.db as unknown as { getOptions: () => { ticks: number } };

    expect(db.getOptions().ticks).toBeLessThanOrEqual(32);
  });

  it("does not allow an architecture group to pollute Object.prototype", async () => {
    await expect(
      mermaid.mermaidAPI.getDiagramFromText(`architecture-beta
      group mermaidPrototypePollutionMarker(cloud)[Marker]
      service a(server)[A] in __proto__
      service b(server)[B] in mermaidPrototypePollutionMarker
      a:R -- L:b`),
    ).rejects.toThrow("parent does not exist");

    expect(({} as Record<string, unknown>)[prototypeMarker]).toBeUndefined();
  });
});
