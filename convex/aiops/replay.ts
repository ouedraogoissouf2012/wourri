import { v } from "convex/values";
import { mutation, query } from "../_generated/server";
import { authorize, authorizeMutation, CAPABILITIES } from "../authorization";
import { auditAiops, clampLimit } from "./shared";

// OBS-03 / §30 — freeze inputs and context so a run can be replayed in staging.
// Platform-scoped: requires aiopsReplay.

// Captures a frozen snapshot. inputPayload/contextPayload are serialized to
// JSON strings so the exact bytes replayed later are immutable.
export const captureReplaySnapshot = mutation({
  args: {
    organizationId: v.optional(v.string()),
    traceId: v.optional(v.id("executionTraces")),
    conversationContextId: v.optional(v.id("conversationContexts")),
    inputPayload: v.any(),
    contextPayload: v.any(),
    promptKey: v.optional(v.string()),
    promptVersion: v.optional(v.number()),
    policyKey: v.optional(v.string()),
    policyVersion: v.optional(v.number()),
    modelConfigKey: v.optional(v.string()),
    modelConfigVersion: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.aiopsReplay,
    });
    const now = Date.now();
    const id = await ctx.db.insert("replaySnapshots", {
      organizationId: args.organizationId,
      traceId: args.traceId,
      conversationContextId: args.conversationContextId,
      inputPayload: JSON.stringify(args.inputPayload),
      contextPayload: JSON.stringify(args.contextPayload),
      promptKey: args.promptKey,
      promptVersion: args.promptVersion,
      policyKey: args.policyKey,
      policyVersion: args.policyVersion,
      modelConfigKey: args.modelConfigKey,
      modelConfigVersion: args.modelConfigVersion,
      capturedAt: now,
    });
    await auditAiops(ctx, auth, now, {
      action: "aiops.replay.capture",
      resourceType: "replaySnapshots",
      resourceId: id,
      traceId: args.traceId,
      after: { promptKey: args.promptKey, promptVersion: args.promptVersion },
    });
    return id;
  },
});

// Recent snapshots, filterable by originating trace or by organization.
export const listReplaySnapshots = query({
  args: {
    organizationId: v.optional(v.string()),
    traceId: v.optional(v.id("executionTraces")),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsReplay });
    const limit = clampLimit(args.limit);
    if (args.traceId !== undefined) {
      const traceId = args.traceId;
      return ctx.db
        .query("replaySnapshots")
        .withIndex("by_traceId", (q) => q.eq("traceId", traceId))
        .order("desc")
        .take(limit);
    }
    return ctx.db
      .query("replaySnapshots")
      .withIndex("by_organizationId_and_capturedAt", (q) =>
        q.eq("organizationId", args.organizationId),
      )
      .order("desc")
      .take(limit);
  },
});

export const getReplaySnapshot = query({
  args: { snapshotId: v.id("replaySnapshots") },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsReplay });
    return ctx.db.get(args.snapshotId);
  },
});
