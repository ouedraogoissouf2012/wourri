import { v } from "convex/values";
import { query } from "../_generated/server";
import { authorize, CAPABILITIES } from "../authorization";
import { clampLimit } from "./shared";

// §31 — read access to the audit trail. Platform-scoped: requires auditRead.

// Recent audit entries, filterable by action or by organization.
export const listAuditLogs = query({
  args: {
    organizationId: v.optional(v.string()),
    action: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.auditRead });
    const limit = clampLimit(args.limit);
    if (args.action !== undefined) {
      const action = args.action;
      return ctx.db
        .query("auditLogs")
        .withIndex("by_action_and_createdAt", (q) => q.eq("action", action))
        .order("desc")
        .take(limit);
    }
    return ctx.db
      .query("auditLogs")
      .withIndex("by_organizationId_and_createdAt", (q) =>
        q.eq("organizationId", args.organizationId),
      )
      .order("desc")
      .take(limit);
  },
});
