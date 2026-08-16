import { defineTable } from "convex/server";
import { v } from "convex/values";

export const knowledgeTables = {
  knowledgeSources: defineTable({
    organizationId: v.optional(v.string()),
    visibility: v.union(v.literal("global"), v.literal("organization")),
    authority: v.string(),
    license: v.string(),
    canonicalLocator: v.string(),
    status: v.union(v.literal("active"), v.literal("archived")),
  })
    .index("by_organizationId_and_visibility", ["organizationId", "visibility"])
    .index("by_canonicalLocator", ["canonicalLocator"]),
  knowledgeSourceVersions: defineTable({
    sourceId: v.id("knowledgeSources"),
    version: v.string(),
    contentHash: v.string(),
    acquiredAt: v.number(),
    acquisitionMethod: v.string(),
    publisherMetadata: v.optional(v.string()),
  }).index("by_sourceId_and_version", ["sourceId", "version"]),
  knowledgeDocuments: defineTable({
    sourceVersionId: v.id("knowledgeSourceVersions"),
    title: v.string(),
    locator: v.string(),
    language: v.string(),
    mimeType: v.string(),
    contentHash: v.string(),
    status: v.union(v.literal("ready"), v.literal("rejected")),
  }).index("by_sourceVersionId", ["sourceVersionId"]),
  // Searchable chunks live in the @convex-dev/rag component, keyed back to these
  // documents via the RAG entry filters (sourceId/sourceVersionId). We do not
  // keep a parallel hand-rolled chunk table.
};
