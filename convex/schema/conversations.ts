import { defineTable } from "convex/server";
import { v } from "convex/values";

export const conversationTables = {
  threads: defineTable({
    organizationId: v.string(),
    farmerId: v.id("farmers"),
    channel: v.string(),
    externalThreadKey: v.string(),
    originAlertId: v.optional(v.id("alerts")),
    status: v.union(v.literal("open"), v.literal("closed")),
    retentionExpiresAt: v.optional(v.number()),
  })
    .index("by_organizationId_and_farmerId", ["organizationId", "farmerId"])
    .index("by_organizationId_and_originAlertId", [
      "organizationId",
      "originAlertId",
    ])
    .index("by_organizationId_and_channel_and_externalThreadKey", [
      "organizationId",
      "channel",
      "externalThreadKey",
    ]),
  threadMessages: defineTable({
    organizationId: v.string(),
    threadId: v.id("threads"),
    direction: v.union(v.literal("inbound"), v.literal("outbound")),
    providerMessageId: v.optional(v.string()),
    content: v.optional(v.string()),
    fileStorageId: v.optional(v.id("_storage")),
    retentionExpiresAt: v.optional(v.number()),
    createdAt: v.number(),
  })
    .index("by_threadId_and_createdAt", ["threadId", "createdAt"])
    .index("by_organizationId_and_providerMessageId", [
      "organizationId",
      "providerMessageId",
    ]),
  threadMemories: defineTable({
    organizationId: v.string(),
    threadId: v.id("threads"),
    kind: v.union(v.literal("summary"), v.literal("fact")),
    content: v.string(),
    expiresAt: v.optional(v.number()),
    updatedAt: v.number(),
  }).index("by_threadId_and_updatedAt", ["threadId", "updatedAt"]),
};
