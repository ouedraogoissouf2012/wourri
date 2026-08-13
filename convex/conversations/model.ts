import { createThread, saveMessage } from "@convex-dev/agent";
import { components } from "../_generated/api";
import type { MutationCtx, QueryCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import {
  setDeliveryConversation,
  setDeliveryStateByAlertAndFarmer,
} from "../alerts/model";
import { getProvenance } from "../knowledge/model";

// DAT-05 / ALT-04 / §17 — WOURI conversation contexts over Agent threads.

export const getContextForOrg = async (
  ctx: QueryCtx | MutationCtx,
  organizationId: string,
  contextId: Id<"conversationContexts">,
) => {
  const context = await ctx.db.get(contextId);
  if (!context || context.organizationId !== organizationId) return null;
  return context;
};

const findOpenContext = async (
  ctx: QueryCtx | MutationCtx,
  organizationId: string,
  channel: string,
  farmerId: Id<"farmers">,
) =>
  ctx.db
    .query("conversationContexts")
    .withIndex("by_organizationId_and_channel_and_farmerId", (q) =>
      q
        .eq("organizationId", organizationId)
        .eq("channel", channel)
        .eq("farmerId", farmerId),
    )
    .filter((q) => q.eq(q.field("status"), "open"))
    .first();

// Opens (or reuses) a durable conversation seeded from an alert: creates the
// Agent thread, records the alert content as an assistant message, links the
// delivery, and stamps originAlertId so a later reply recovers the alert.
export const ensureConversationForAlert = async (
  ctx: MutationCtx,
  input: {
    organizationId: string;
    farmerId: Id<"farmers">;
    channel: string;
    preferredLanguage: string;
    alertId: Id<"alerts">;
  },
  now: number,
): Promise<{ contextId: Id<"conversationContexts">; agentThreadId: string }> => {
  const existing = await findOpenContext(
    ctx,
    input.organizationId,
    input.channel,
    input.farmerId,
  );
  if (existing) {
    return { contextId: existing._id, agentThreadId: existing.agentThreadId };
  }

  const alert = await ctx.db.get(input.alertId);
  const agentThreadId = await createThread(ctx, components.agent, {
    userId: input.farmerId,
  });
  if (alert) {
    await saveMessage(ctx, components.agent, {
      threadId: agentThreadId,
      message: { role: "assistant", content: alert.message },
    });
  }
  const contextId = await ctx.db.insert("conversationContexts", {
    organizationId: input.organizationId,
    farmerId: input.farmerId,
    agentThreadId,
    channel: input.channel,
    preferredLanguage: input.preferredLanguage,
    originAlertId: input.alertId,
    status: "open",
    lastActivityAt: now,
    createdAt: now,
  });
  return { contextId, agentThreadId };
};

// §17 — records an inbound farmer reply and returns the recovered alert context,
// so "Et pour mon cacao ?" needs no repetition of the original alert.
export const recordInboundReply = async (
  ctx: MutationCtx,
  input: {
    organizationId: string;
    farmerId: Id<"farmers">;
    channel: string;
    preferredLanguage: string;
    alertId: Id<"alerts">;
    text: string;
  },
  now: number,
) => {
  const deliveryId = await setDeliveryStateByAlertAndFarmer(
    ctx,
    input.alertId,
    input.farmerId,
    "replied",
  );
  const { contextId, agentThreadId } = await ensureConversationForAlert(
    ctx,
    input,
    now,
  );
  if (deliveryId) await setDeliveryConversation(ctx, deliveryId, contextId);
  await saveMessage(ctx, components.agent, {
    threadId: agentThreadId,
    prompt: input.text,
  });
  await ctx.db.patch(contextId, { lastActivityAt: now });
  return { contextId, agentThreadId };
};

// Reconstructs the alert context bound to a conversation: alert content, date,
// organization, source provenance and targeted zones.
export const resolveAlertContext = async (
  ctx: QueryCtx | MutationCtx,
  organizationId: string,
  contextId: Id<"conversationContexts">,
) => {
  const context = await getContextForOrg(ctx, organizationId, contextId);
  if (!context || !context.originAlertId) return null;
  const alert = await ctx.db.get(context.originAlertId);
  if (!alert) return null;
  const provenance = alert.sourceVersionId
    ? await getProvenance(ctx, alert.sourceVersionId)
    : null;
  const rules = await ctx.db
    .query("alertAudienceRules")
    .withIndex("by_alertId", (q) => q.eq("alertId", alert._id))
    .take(100);
  const zones = rules
    .filter((rule) => rule.kind === "zone")
    .map((rule) => rule.targetKey);
  return {
    agentThreadId: context.agentThreadId,
    alert: {
      id: alert._id,
      organizationId: alert.organizationId,
      message: alert.message,
      createdAt: alert.createdAt,
      scheduledAt: alert.scheduledAt,
    },
    zones,
    provenance,
  };
};
