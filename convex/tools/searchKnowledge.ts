import { v } from "convex/values";
import { action } from "../_generated/server";
import { internal } from "../_generated/api";
import { CAPABILITIES } from "../authorization";
import { rag, GLOBAL_NAMESPACE, type KnowledgeFilters } from "../rag";
import { abstain, type ToolProvenance, type ToolResult } from "./types";

type Filter = { name: keyof KnowledgeFilters; value: string };

const provenanceFromEntry = (entry: {
  key?: string;
  title?: string;
  filterValues: Array<{ name: string; value: unknown }>;
}): ToolProvenance => {
  const get = (name: string) =>
    entry.filterValues.find((f) => f.name === name)?.value as
      | string
      | undefined;
  return {
    documentId: entry.key,
    title: entry.title,
    sourceId: get("sourceId"),
    sourceVersionId: get("sourceVersionId"),
    authority: get("authority"),
    version: get("version"),
  };
};

// §22 / KNO-04 — searchKnowledge. Searches only namespaces the caller's org may
// see (its own + global), filtered by zone/culture/language, and returns the
// passages used with provenance. No result above threshold yields abstention so
// the LLM is never handed an empty context to fill in (§23 / G07).
export const searchKnowledge = action({
  args: {
    query: v.string(),
    zone: v.optional(v.string()),
    culture: v.optional(v.string()),
    language: v.optional(v.string()),
    limit: v.optional(v.number()),
    scoreThreshold: v.optional(v.number()),
  },
  handler: async (ctx, args): Promise<ToolResult<{
    passages: Array<{ text: string; score: number; entryId: string }>;
  }>> => {
    const auth = await ctx.runQuery(
      internal.authz.checkAccess.requireCapability,
      { permission: CAPABILITIES.knowledgeRead },
    );
    const limit = Math.min(args.limit ?? 8, 20);
    const threshold = args.scoreThreshold ?? 0.1;

    const filters: Filter[] = [];
    if (args.zone) filters.push({ name: "zone", value: args.zone });
    if (args.culture) filters.push({ name: "culture", value: args.culture });
    if (args.language) filters.push({ name: "language", value: args.language });

    const searchNamespace = async (namespace: string) => {
      try {
        return await rag.search(ctx, { namespace, query: args.query, filters, limit });
      } catch (error) {
        // A namespace with no ingested content yet is a normal empty result. Any
        // other failure (embedding provider, dimension mismatch, index error) is
        // a real system fault and must NOT be masked as "no evidence" — rethrow
        // it so the trace records a genuine error instead of a false abstention.
        const message = error instanceof Error ? error.message.toLowerCase() : "";
        if (message.includes("namespace")) return { results: [], entries: [] };
        throw error;
      }
    };

    const [globalHits, orgHits] = await Promise.all([
      searchNamespace(GLOBAL_NAMESPACE),
      searchNamespace(auth.organizationId),
    ]);

    const results = [...globalHits.results, ...orgHits.results]
      .filter((result) => (result.score ?? 0) >= threshold)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .slice(0, limit);

    if (results.length === 0) {
      return abstain(`No knowledge passage above threshold for '${args.query}'`);
    }

    const entriesById = new Map<string, ToolProvenance>();
    for (const entry of [...globalHits.entries, ...orgHits.entries]) {
      entriesById.set(entry.entryId, provenanceFromEntry(entry));
    }

    const passages = results.map((result) => ({
      text: result.content.map((chunk) => chunk.text).join("\n"),
      score: result.score ?? 0,
      entryId: result.entryId,
    }));
    const provenance = [...new Set(results.map((r) => r.entryId))]
      .map((entryId) => entriesById.get(entryId))
      .filter((p): p is ToolProvenance => p !== undefined);

    return { status: "ok", data: { passages }, provenance };
  },
});
