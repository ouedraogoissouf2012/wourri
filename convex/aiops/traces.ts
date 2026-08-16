import { v } from "convex/values";
import { query } from "../_generated/server";
import { authorize, CAPABILITIES } from "../authorization";
import { clampLimit } from "./shared";

// §28 / OBS-01 & OBS-04 — read access to execution traces and error reports.
// Platform-scoped: requires aiopsRead.

const resultStatus = v.union(
  v.literal("running"),
  v.literal("succeeded"),
  v.literal("abstained"),
  v.literal("failed"),
);

// Recent traces, filterable by result status or by organization. When neither a
// status nor an org is given, returns the platform-scoped traces (org unset).
export const listTraces = query({
  args: {
    organizationId: v.optional(v.string()),
    resultStatus: v.optional(resultStatus),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    const limit = clampLimit(args.limit);
    if (args.resultStatus !== undefined) {
      const status = args.resultStatus;
      return ctx.db
        .query("executionTraces")
        .withIndex("by_resultStatus_and_startedAt", (q) =>
          q.eq("resultStatus", status),
        )
        .order("desc")
        .take(limit);
    }
    return ctx.db
      .query("executionTraces")
      .withIndex("by_organizationId_and_startedAt", (q) =>
        q.eq("organizationId", args.organizationId),
      )
      .order("desc")
      .take(limit);
  },
});

// A single trace with its ordered steps — the "Execution Trace" view (G11).
export const getTrace = query({
  args: { traceId: v.id("executionTraces") },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    const trace = await ctx.db.get(args.traceId);
    if (!trace) return null;
    const steps = await ctx.db
      .query("executionTraceSteps")
      .withIndex("by_traceId_and_ordinal", (q) => q.eq("traceId", args.traceId))
      .order("asc")
      .take(500);
    return { trace, steps };
  },
});

// Recent error reports, filterable by taxonomy code or by organization.
export const listErrors = query({
  args: {
    organizationId: v.optional(v.string()),
    errorType: v.optional(v.string()),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    const limit = clampLimit(args.limit);
    if (args.errorType !== undefined) {
      const errorType = args.errorType;
      return ctx.db
        .query("errorReports")
        .withIndex("by_errorType_and_createdAt", (q) =>
          q.eq("errorType", errorType),
        )
        .order("desc")
        .take(limit);
    }
    return ctx.db
      .query("errorReports")
      .withIndex("by_organizationId_and_createdAt", (q) =>
        q.eq("organizationId", args.organizationId),
      )
      .order("desc")
      .take(limit);
  },
});
