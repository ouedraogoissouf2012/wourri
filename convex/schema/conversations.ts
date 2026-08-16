import { defineTable } from "convex/server";
import { v } from "convex/values";

// DAT-05 / §8 / §17 — WOURI business layer over the Agent component. The Agent
// component owns messages and conversational memory; this table maps an Agent
// thread to WHO speaks, FOR WHICH organization, IN WHICH context, and FROM WHICH
// alert. originAlertId is what lets "Et pour mon cacao ?" recover the alert.
export const conversationTables = {
  conversationContexts: defineTable({
    organizationId: v.string(),
    farmerId: v.id("farmers"),
    agentThreadId: v.string(),
    channel: v.string(),
    preferredLanguage: v.string(),
    originAlertId: v.optional(v.id("alerts")),
    status: v.union(v.literal("open"), v.literal("closed")),
    lastActivityAt: v.number(),
    createdAt: v.number(),
  })
    .index("by_agentThreadId", ["agentThreadId"])
    .index("by_organizationId_and_farmerId", ["organizationId", "farmerId"])
    .index("by_organizationId_and_originAlertId", [
      "organizationId",
      "originAlertId",
    ])
    .index("by_organizationId_and_channel_and_farmerId", [
      "organizationId",
      "channel",
      "farmerId",
    ]),
};
