import { defineTable } from "convex/server";
import { v } from "convex/values";

export const alertTables = {
  alerts: defineTable({
    organizationId: v.string(),
    creatorMemberId: v.string(),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
    message: v.string(),
    status: v.union(
      v.literal("draft"),
      v.literal("scheduled"),
      v.literal("sending"),
      v.literal("completed"),
      v.literal("canceled"),
    ),
    scheduledAt: v.optional(v.number()),
    createdAt: v.number(),
  })
    .index("by_organizationId_and_status", ["organizationId", "status"])
    .index("by_organizationId_and_scheduledAt", ["organizationId", "scheduledAt"]),
  alertAudienceRules: defineTable({
    alertId: v.id("alerts"),
    kind: v.union(
      v.literal("farmer"),
      v.literal("zone"),
      v.literal("crop"),
      v.literal("group"),
    ),
    targetKey: v.string(),
    snapshotAt: v.optional(v.number()),
  }).index("by_alertId", ["alertId"]),
  alertDeliveries: defineTable({
    organizationId: v.string(),
    alertId: v.id("alerts"),
    farmerId: v.id("farmers"),
    conversationContextId: v.optional(v.id("conversationContexts")),
    provider: v.string(),
    providerMessageId: v.optional(v.string()),
    state: v.union(
      v.literal("created"),
      v.literal("scheduled"),
      v.literal("sent"),
      v.literal("delivered"),
      v.literal("read"),
      v.literal("replied"),
      v.literal("failed"),
    ),
    attemptCount: v.number(),
    nextAttemptAt: v.optional(v.number()),
    createdAt: v.number(),
  })
    .index("by_organizationId_and_state_and_nextAttemptAt", [
      "organizationId",
      "state",
      "nextAttemptAt",
    ])
    .index("by_alertId_and_state", ["alertId", "state"])
    .index("by_alertId_and_farmerId", ["alertId", "farmerId"])
    .index("by_farmerId_and_state", ["farmerId", "state"])
    .index("by_provider_and_providerMessageId", [
      "provider",
      "providerMessageId",
    ]),
};
