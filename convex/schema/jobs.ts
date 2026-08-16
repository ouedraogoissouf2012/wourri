import { defineTable } from "convex/server";
import { v } from "convex/values";

// §41 — Convex holds job STATE only. Heavy CPU work (ASR, FFmpeg, TTS) runs on
// the Dokploy worker, which reports progress and results back here.
export const jobTables = {
  jobRecords: defineTable({
    organizationId: v.optional(v.string()),
    kind: v.string(),
    status: v.union(
      v.literal("queued"),
      v.literal("running"),
      v.literal("succeeded"),
      v.literal("failed"),
    ),
    progress: v.optional(v.number()),
    inputRef: v.optional(v.string()),
    resultRef: v.optional(v.string()),
    fileStorageId: v.optional(v.id("_storage")),
    errorType: v.optional(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_organizationId_and_status", ["organizationId", "status"])
    .index("by_kind_and_status", ["kind", "status"]),
};
