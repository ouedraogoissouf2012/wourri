import { v } from "convex/values";
import { internalQuery } from "../_generated/server";
import { authorize } from "./authorize";

// Actions have no ctx.db, so they authorize through this internal query. It
// derives the organization from the session (never from an argument) and returns
// the authorization context, or throws fail-closed.
export const requireCapability = internalQuery({
  args: {
    permission: v.string(),
    scopeType: v.optional(
      v.union(v.literal("zone"), v.literal("crop"), v.literal("group")),
    ),
    scopeKey: v.optional(v.string()),
    entitlement: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const scope =
      args.scopeType && args.scopeKey
        ? { type: args.scopeType, key: args.scopeKey }
        : undefined;
    return authorize(ctx, {
      permission: args.permission,
      scope,
      entitlement: args.entitlement,
    });
  },
});
