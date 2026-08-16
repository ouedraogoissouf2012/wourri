import type { EmbeddingModelV2 } from "@ai-sdk/provider";

// KNO-04 — embedding model for the knowledge RAG. The pilot ships a deterministic
// local model so staging and tests need no external key and stay reproducible.
// Production swaps in a real provider via env; changing provider/dimension
// requires re-indexing the namespaces (documented in the runbook).

export const LOCAL_EMBEDDING_DIMENSION = 256;

const tokenize = (text: string): string[] =>
  text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length > 0);

// FNV-1a 32-bit hash — stable across runs and platforms.
const fnv1a = (input: string): number => {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
};

const embedText = (text: string, dimension: number): number[] => {
  const vector = new Array<number>(dimension).fill(0);
  for (const token of tokenize(text)) {
    const bucket = fnv1a(token) % dimension;
    const sign = (fnv1a(`s:${token}`) & 1) === 0 ? 1 : -1;
    vector[bucket] += sign;
  }
  let norm = 0;
  for (const value of vector) norm += value * value;
  norm = Math.sqrt(norm);
  if (norm === 0) return vector;
  return vector.map((value) => value / norm);
};

export const createLocalEmbeddingModel = (
  dimension: number = LOCAL_EMBEDDING_DIMENSION,
): EmbeddingModelV2<string> => ({
  specificationVersion: "v2",
  provider: "wouri-local",
  modelId: "wouri-hash-embedding",
  maxEmbeddingsPerCall: Infinity,
  supportsParallelCalls: true,
  async doEmbed({ values }) {
    return {
      embeddings: values.map((value) => embedText(value, dimension)),
      usage: { tokens: values.reduce((sum, value) => sum + value.length, 0) },
    };
  },
});
