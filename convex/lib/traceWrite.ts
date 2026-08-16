import { v } from "convex/values";
import { internalMutation } from "../_generated/server";
import {
  startTrace,
  appendTraceStep,
  finishTrace,
  recordError,
} from "./trace";
import { ALL_ERROR_TYPES, type ErrorType } from "./errors";

// Internal mutation bridges so actions and tools can persist Execution Trace
// records (actions have no ctx.db). §28 / OBS-01.

const errorTypeValidator = v.union(
  ...ALL_ERROR_TYPES.map((value) => v.literal(value)),
);

export const openTrace = internalMutation({
  args: {
    organizationId: v.optional(v.string()),
    conversationContextId: v.optional(v.id("conversationContexts")),
    farmerId: v.optional(v.id("farmers")),
    channel: v.optional(v.string()),
    intent: v.optional(v.string()),
    language: v.optional(v.string()),
    originAlertId: v.optional(v.id("alerts")),
    promptKey: v.optional(v.string()),
    promptVersion: v.optional(v.number()),
    policyKey: v.optional(v.string()),
    policyVersion: v.optional(v.number()),
    modelConfigKey: v.optional(v.string()),
    modelConfigVersion: v.optional(v.number()),
  },
  handler: async (ctx, args) => startTrace(ctx, args, Date.now()),
});

export const addTraceStep = internalMutation({
  args: {
    traceId: v.id("executionTraces"),
    kind: v.union(
      v.literal("tool"),
      v.literal("retrieval"),
      v.literal("generation"),
      v.literal("guard"),
    ),
    name: v.string(),
    status: v.union(v.literal("ok"), v.literal("error"), v.literal("skipped")),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
    latencyMs: v.optional(v.number()),
    detail: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const { traceId, ...step } = args;
    await appendTraceStep(ctx, traceId, step, Date.now());
  },
});

export const closeTrace = internalMutation({
  args: {
    traceId: v.id("executionTraces"),
    resultStatus: v.union(
      v.literal("succeeded"),
      v.literal("abstained"),
      v.literal("failed"),
    ),
    errorType: v.optional(errorTypeValidator),
    latencyMs: v.optional(v.number()),
    inputTokens: v.optional(v.number()),
    outputTokens: v.optional(v.number()),
    costMicros: v.optional(v.number()),
    externalTelemetryId: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const { traceId, ...outcome } = args;
    await finishTrace(
      ctx,
      traceId,
      outcome as typeof outcome & { errorType?: ErrorType },
      Date.now(),
    );
  },
});

export const logError = internalMutation({
  args: {
    organizationId: v.optional(v.string()),
    traceId: v.optional(v.id("executionTraces")),
    conversationContextId: v.optional(v.id("conversationContexts")),
    alertId: v.optional(v.id("alerts")),
    errorType: errorTypeValidator,
    message: v.string(),
  },
  handler: async (ctx, args) => recordError(ctx, args, Date.now()),
});
