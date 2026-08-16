import { describe, expect, it } from "vitest";
import { createLocalEmbeddingModel } from "./embeddingModel";

const dot = (a: number[], b: number[]) =>
  a.reduce((sum, value, index) => sum + value * b[index], 0);

// KNO-04 — the local embedding model must be deterministic (so staging/tests are
// reproducible) and discriminative (related text closer than unrelated text).
describe("local embedding model", () => {
  it("is deterministic and ranks related text above unrelated text", async () => {
    const model = createLocalEmbeddingModel();
    const { embeddings } = await model.doEmbed({
      values: [
        "cacao maladie pourriture brune",
        "cacao maladie pourriture brune",
        "prix du transport urbain a la ville",
      ],
    });
    const [v1, v1bis, v3] = embeddings;

    // Identical input yields an identical (unit) vector.
    expect(dot(v1, v1bis)).toBeCloseTo(1, 5);
    // Related text is more similar than unrelated text.
    expect(dot(v1, v1bis)).toBeGreaterThan(dot(v1, v3));
  });
});
