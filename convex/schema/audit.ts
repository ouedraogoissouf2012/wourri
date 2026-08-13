import { defineTable } from "convex/server";
import { v } from "convex/values";

// §31 — audit log for sensitive operations. Never store secrets. before/after
// hold non-sensitive serialized snapshots only.
export const auditTables = {
  auditLogs: defineTable({
    organizationId: v.optional(v.string()),
    actorSubject: v.string(),
    actorMemberId: v.optional(v.string()),
    action: v.string(),
    resourceType: v.string(),
    resourceId: v.optional(v.string()),
    before: v.optional(v.string()),
    after: v.optional(v.string()),
    traceId: v.optional(v.id("executionTraces")),
    createdAt: v.number(),
  })
    .index("by_organizationId_and_createdAt", ["organizationId", "createdAt"])
    .index("by_resourceType_and_resourceId", ["resourceType", "resourceId"])
    .index("by_action_and_createdAt", ["action", "createdAt"]),
};
