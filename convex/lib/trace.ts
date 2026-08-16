import type { MutationCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import type { ErrorType } from "./errors";

// §28 / OBS-01 — Execution Trace helpers. We record the execution PATH: steps,
// tools, source references, versions, guard outcomes and metrics. We never store
// a model's private chain-of-thought.

export type TraceInit = {
  organizationId?: string;
  conversationContextId?: Id<"conversationContexts">;
  farmerId?: Id<"farmers">;
  channel?: string;
  intent?: string;
  language?: string;
  originAlertId?: Id<"alerts">;
  promptKey?: string;
  promptVersion?: number;
  policyKey?: string;
  policyVersion?: number;
  modelConfigKey?: string;
  modelConfigVersion?: number;
};

export const startTrace = async (
  ctx: MutationCtx,
  init: TraceInit,
  now: number,
): Promise<Id<"executionTraces">> =>
  ctx.db.insert("executionTraces", {
    ...init,
    resultStatus: "running",
    startedAt: now,
  });

export type TraceStep = {
  kind: "tool" | "retrieval" | "generation" | "guard";
  name: string;
  status: "ok" | "error" | "skipped";
  sourceVersionId?: Id<"knowledgeSourceVersions">;
  latencyMs?: number;
  // Already-serialized detail (the schema field is a string). Callers with a
  // structured payload serialize it once before passing it here.
  detail?: string;
};

export const appendTraceStep = async (
  ctx: MutationCtx,
  traceId: Id<"executionTraces">,
  step: TraceStep,
  now: number,
) => {
  const last = await ctx.db
    .query("executionTraceSteps")
    .withIndex("by_traceId_and_ordinal", (q) => q.eq("traceId", traceId))
    .order("desc")
    .first();
  await ctx.db.insert("executionTraceSteps", {
    traceId,
    ordinal: (last?.ordinal ?? 0) + 1,
    kind: step.kind,
    name: step.name,
    sourceVersionId: step.sourceVersionId,
    status: step.status,
    latencyMs: step.latencyMs,
    detail: step.detail,
    createdAt: now,
  });
};

export type TraceOutcome = {
  resultStatus: "succeeded" | "abstained" | "failed";
  errorType?: ErrorType;
  latencyMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  costMicros?: number;
  externalTelemetryId?: string;
};

export const finishTrace = async (
  ctx: MutationCtx,
  traceId: Id<"executionTraces">,
  outcome: TraceOutcome,
  now: number,
) => {
  await ctx.db.patch(traceId, { ...outcome, completedAt: now });
};

export type ErrorInit = {
  organizationId?: string;
  traceId?: Id<"executionTraces">;
  conversationContextId?: Id<"conversationContexts">;
  alertId?: Id<"alerts">;
  errorType: ErrorType;
  message: string;
};

export const recordError = async (
  ctx: MutationCtx,
  init: ErrorInit,
  now: number,
) => {
  await ctx.db.insert("errorReports", { ...init, createdAt: now });
};
