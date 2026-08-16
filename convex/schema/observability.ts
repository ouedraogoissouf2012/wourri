import { defineTable } from "convex/server";
import { v } from "convex/values";

// §28 / OBS-01 — Execution Trace. We store the execution PATH (steps, tools,
// sources, versions, guards, metrics), never a model's private chain-of-thought.
export const observabilityTables = {
  executionTraces: defineTable({
    organizationId: v.optional(v.string()),
    conversationContextId: v.optional(v.id("conversationContexts")),
    farmerId: v.optional(v.id("farmers")),
    channel: v.optional(v.string()),
    intent: v.optional(v.string()),
    language: v.optional(v.string()),
    originAlertId: v.optional(v.id("alerts")),
    modelConfigKey: v.optional(v.string()),
    modelConfigVersion: v.optional(v.number()),
    promptKey: v.optional(v.string()),
    promptVersion: v.optional(v.number()),
    policyKey: v.optional(v.string()),
    policyVersion: v.optional(v.number()),
    resultStatus: v.union(
      v.literal("running"),
      v.literal("succeeded"),
      v.literal("abstained"),
      v.literal("failed"),
    ),
    errorType: v.optional(v.string()),
    latencyMs: v.optional(v.number()),
    inputTokens: v.optional(v.number()),
    outputTokens: v.optional(v.number()),
    costMicros: v.optional(v.number()),
    externalTelemetryId: v.optional(v.string()),
    startedAt: v.number(),
    completedAt: v.optional(v.number()),
  })
    .index("by_organizationId_and_startedAt", ["organizationId", "startedAt"])
    .index("by_conversationContextId", ["conversationContextId"])
    .index("by_resultStatus_and_startedAt", ["resultStatus", "startedAt"]),
  executionTraceSteps: defineTable({
    traceId: v.id("executionTraces"),
    ordinal: v.number(),
    kind: v.union(
      v.literal("tool"),
      v.literal("retrieval"),
      v.literal("generation"),
      v.literal("guard"),
    ),
    name: v.string(),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
    status: v.union(v.literal("ok"), v.literal("error"), v.literal("skipped")),
    latencyMs: v.optional(v.number()),
    detail: v.optional(v.string()),
    createdAt: v.number(),
  }).index("by_traceId_and_ordinal", ["traceId", "ordinal"]),
  // OBS-04 / §29 — error taxonomy occurrences.
  errorReports: defineTable({
    organizationId: v.optional(v.string()),
    traceId: v.optional(v.id("executionTraces")),
    conversationContextId: v.optional(v.id("conversationContexts")),
    alertId: v.optional(v.id("alerts")),
    errorType: v.string(),
    message: v.string(),
    createdAt: v.number(),
  })
    .index("by_organizationId_and_createdAt", ["organizationId", "createdAt"])
    .index("by_errorType_and_createdAt", ["errorType", "createdAt"]),
  // OBS-03 / §30 — frozen inputs and context for staging replay.
  replaySnapshots: defineTable({
    organizationId: v.optional(v.string()),
    traceId: v.optional(v.id("executionTraces")),
    conversationContextId: v.optional(v.id("conversationContexts")),
    inputPayload: v.string(),
    contextPayload: v.string(),
    promptKey: v.optional(v.string()),
    promptVersion: v.optional(v.number()),
    policyKey: v.optional(v.string()),
    policyVersion: v.optional(v.number()),
    modelConfigKey: v.optional(v.string()),
    modelConfigVersion: v.optional(v.number()),
    capturedAt: v.number(),
  })
    .index("by_organizationId_and_capturedAt", ["organizationId", "capturedAt"])
    .index("by_traceId", ["traceId"]),
};
