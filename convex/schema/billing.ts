import { defineTable } from "convex/server";
import { v } from "convex/values";

// organizationEntitlements is the enforced surface today (see lib/entitlements).
// organizationSubscriptions and subscriptionEvents are reserved for the future
// billing-provider integration and are not written by any function yet.
export const billingTables = {
  organizationSubscriptions: defineTable({
    organizationId: v.string(),
    provider: v.string(),
    providerCustomerId: v.string(),
    providerSubscriptionId: v.string(),
    planKey: v.string(),
    status: v.union(
      v.literal("trialing"),
      v.literal("active"),
      v.literal("past_due"),
      v.literal("canceled"),
    ),
    currentPeriodEndsAt: v.number(),
  })
    .index("by_organizationId", ["organizationId"])
    .index("by_provider_and_providerSubscriptionId", [
      "provider",
      "providerSubscriptionId",
    ]),
  organizationEntitlements: defineTable({
    organizationId: v.string(),
    key: v.string(),
    enabled: v.boolean(),
    limit: v.optional(v.number()),
    validFrom: v.number(),
    validUntil: v.optional(v.number()),
    source: v.union(v.literal("subscription"), v.literal("manual")),
  }).index("by_organizationId_and_key", ["organizationId", "key"]),
  subscriptionEvents: defineTable({
    provider: v.string(),
    providerEventId: v.string(),
    organizationId: v.optional(v.string()),
    receivedAt: v.number(),
    processedAt: v.optional(v.number()),
  }).index("by_provider_and_providerEventId", ["provider", "providerEventId"]),
};
