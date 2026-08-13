import { v } from "convex/values";
import { mutation, query, internalQuery } from "../_generated/server";
import type { QueryCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import { authorize, authorizeMutation, CAPABILITIES } from "../authorization";
import { auditAiops, clampLimit } from "./shared";

// AI-06 / §27 — feature flag resolution and controlled mutation.

const environmentValidator = v.union(
  v.literal("staging"),
  v.literal("production"),
);
type Environment = "staging" | "production";

// Resolves a flag with org > environment-global priority; defaults to false
// (fail closed) when no flag exists. Exported so the pipeline can gate features
// directly without an authenticated session.
export async function isFeatureEnabled(
  ctx: QueryCtx,
  environment: Environment,
  key: string,
  organizationId?: string,
): Promise<boolean> {
  if (organizationId !== undefined) {
    const orgFlag = await ctx.db
      .query("featureFlags")
      .withIndex("by_environment_and_organizationId_and_key", (q) =>
        q
          .eq("environment", environment)
          .eq("organizationId", organizationId)
          .eq("key", key),
      )
      .unique();
    if (orgFlag) return orgFlag.enabled;
  }
  const globalFlag = await ctx.db
    .query("featureFlags")
    .withIndex("by_environment_and_organizationId_and_key", (q) =>
      q
        .eq("environment", environment)
        .eq("organizationId", undefined)
        .eq("key", key),
    )
    .unique();
  return globalFlag?.enabled ?? false;
}

// Internal wrapper for the pipeline's flag checks (no session required).
export const resolveFlag = internalQuery({
  args: {
    environment: environmentValidator,
    key: v.string(),
    organizationId: v.optional(v.string()),
  },
  returns: v.boolean(),
  handler: async (ctx, args) =>
    isFeatureEnabled(ctx, args.environment, args.key, args.organizationId),
});

// Upserts a flag. Platform-scoped: requires featureFlagsManage.
export const setFlag = mutation({
  args: {
    environment: environmentValidator,
    key: v.string(),
    organizationId: v.optional(v.string()),
    enabled: v.boolean(),
    description: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const existing = await ctx.db
      .query("featureFlags")
      .withIndex("by_environment_and_organizationId_and_key", (q) =>
        q
          .eq("environment", args.environment)
          .eq("organizationId", args.organizationId)
          .eq("key", args.key),
      )
      .unique();
    const fields = {
      enabled: args.enabled,
      description: args.description,
      updatedByMemberId: auth.memberId,
      updatedAt: now,
    };
    let flagId: Id<"featureFlags">;
    if (existing) {
      await ctx.db.patch(existing._id, fields);
      flagId = existing._id;
    } else {
      flagId = await ctx.db.insert("featureFlags", {
        key: args.key,
        environment: args.environment,
        organizationId: args.organizationId,
        ...fields,
      });
    }
    await auditAiops(ctx, auth, now, {
      action: "aiops.featureFlag.set",
      resourceType: "featureFlags",
      resourceId: flagId,
      before: existing
        ? { enabled: existing.enabled, description: existing.description }
        : undefined,
      after: { enabled: args.enabled, description: args.description },
    });
    return flagId;
  },
});

// Lists every flag configured for an environment (global and per-org).
export const listFlags = query({
  args: {
    environment: environmentValidator,
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.featureFlagsManage });
    return ctx.db
      .query("featureFlags")
      .withIndex("by_environment_and_key", (q) =>
        q.eq("environment", args.environment),
      )
      .take(clampLimit(args.limit));
  },
});
