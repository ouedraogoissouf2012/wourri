import { saveMessage } from "@convex-dev/agent";
import { v } from "convex/values";
import { action } from "../_generated/server";
import { components, internal, api } from "../_generated/api";
import type { Id } from "../_generated/dataModel";
import { CAPABILITIES } from "../authorization";
import { ERROR_TYPES } from "../lib/errors";
import type { ToolProvenance } from "../tools/types";

// §23 / AI-04 / G07 / G11 — anti-hallucination answer pipeline. It gathers
// evidence through the business tools, and if no source supports the question it
// ABSTAINS (insufficient_evidence) instead of letting a model invent. Every run
// is recorded as an Execution Trace with its tool and guard steps.

type PipelineResult =
  | {
      status: "ok";
      answer: string;
      provenance: ToolProvenance[];
      traceId: Id<"executionTraces">;
    }
  | {
      status: "insufficient_evidence";
      reason: string;
      traceId: Id<"executionTraces">;
    };

export const answerFarmerQuestion = action({
  args: {
    question: v.string(),
    intent: v.union(v.literal("weather"), v.literal("agronomy")),
    zoneId: v.optional(v.string()),
    culture: v.optional(v.string()),
    language: v.optional(v.string()),
    conversationContextId: v.optional(v.id("conversationContexts")),
  },
  handler: async (ctx, args): Promise<PipelineResult> => {
    const auth = await ctx.runQuery(
      internal.authz.checkAccess.requireCapability,
      { permission: CAPABILITIES.knowledgeRead },
    );

    const thread = args.conversationContextId
      ? await ctx.runQuery(internal.conversations.internal.contextThread, {
          contextId: args.conversationContextId,
        })
      : null;
    const contextForTrace =
      thread && thread.organizationId === auth.organizationId
        ? args.conversationContextId
        : undefined;

    const traceId: Id<"executionTraces"> = await ctx.runMutation(
      internal.lib.traceWrite.openTrace,
      {
        organizationId: auth.organizationId,
        conversationContextId: contextForTrace,
        intent: args.intent,
        language: args.language,
      },
    );

    const postAssistant = async (content: string) => {
      if (thread && thread.organizationId === auth.organizationId) {
        await saveMessage(ctx, components.agent, {
          threadId: thread.agentThreadId,
          message: { role: "assistant", content },
        });
      }
    };

    const abstain = async (reason: string): Promise<PipelineResult> => {
      await ctx.runMutation(internal.lib.traceWrite.addTraceStep, {
        traceId,
        kind: "guard",
        name: "evidence-required",
        status: "error",
        detail: reason,
      });
      await ctx.runMutation(internal.lib.traceWrite.closeTrace, {
        traceId,
        resultStatus: "abstained",
        errorType: ERROR_TYPES.SOURCE,
      });
      await postAssistant(`insufficient_evidence: ${reason}`);
      return { status: "insufficient_evidence", reason, traceId };
    };

    let provenance: ToolProvenance[] = [];
    let answer: string;

    if (args.intent === "weather") {
      if (!args.zoneId) return abstain("A zone is required for weather");
      const weather = await ctx.runAction(api.tools.getWeather.getWeather, {
        zoneId: args.zoneId,
      });
      await ctx.runMutation(internal.lib.traceWrite.addTraceStep, {
        traceId,
        kind: "tool",
        name: "getWeather",
        status: weather.status === "ok" ? "ok" : "skipped",
      });
      if (weather.status !== "ok") return abstain(weather.reason);
      provenance = weather.provenance;
      answer = `Weather for zone ${args.zoneId}: ${JSON.stringify(weather.data.variables)}`;
    } else {
      const knowledge = await ctx.runAction(
        api.tools.searchKnowledge.searchKnowledge,
        { query: args.question, zone: args.zoneId, culture: args.culture },
      );
      await ctx.runMutation(internal.lib.traceWrite.addTraceStep, {
        traceId,
        kind: "retrieval",
        name: "searchKnowledge",
        status: knowledge.status === "ok" ? "ok" : "skipped",
      });
      if (knowledge.status !== "ok") return abstain(knowledge.reason);
      provenance = knowledge.provenance;
      answer = knowledge.data.passages.map((p) => p.text).join("\n\n");
    }

    await ctx.runMutation(internal.lib.traceWrite.addTraceStep, {
      traceId,
      kind: "generation",
      name: "compose-answer",
      status: "ok",
    });
    await ctx.runMutation(internal.lib.traceWrite.closeTrace, {
      traceId,
      resultStatus: "succeeded",
    });
    await postAssistant(answer);
    return { status: "ok", answer, provenance, traceId };
  },
});
