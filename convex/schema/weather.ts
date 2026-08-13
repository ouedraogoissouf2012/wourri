import { defineTable } from "convex/server";
import { v } from "convex/values";

// §19 / KNO-02 — structured SODEXAM weather. Queried by the getWeather tool, NOT
// put through RAG. dataOrigin keeps staging fixtures distinguishable from live
// data so a fixture can never be presented as a real production observation.
export const weatherTables = {
  weatherObservations: defineTable({
    sourceVersionId: v.id("knowledgeSourceVersions"),
    zoneId: v.string(),
    issuedAt: v.number(),
    validFrom: v.number(),
    validUntil: v.number(),
    variables: v.string(),
    confidence: v.optional(v.number()),
    dataOrigin: v.union(v.literal("live"), v.literal("staging_fixture")),
  })
    .index("by_zoneId_and_validFrom", ["zoneId", "validFrom"])
    .index("by_sourceVersionId", ["sourceVersionId"]),
};
