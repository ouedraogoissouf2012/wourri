import { ConvexError, v } from "convex/values";
import type { MutationCtx, QueryCtx } from "../_generated/server";
import type { Doc, Id } from "../_generated/dataModel";

// ALT-01 / ALT-02 — alert + delivery model helpers. Every helper takes
// organizationId EXPLICITLY (never from an argument) so the public functions
// stay the only place that reads the session, and the logic is unit-testable.
// Audience targeting/scoping lives in ./audience; re-exported for a single
// import surface.
export {
  audienceKindValidator,
  audienceRuleValidator,
  resolveAudience,
} from "./audience";
export type { AudienceRule } from "./audience";

const ALERT_LIST_LIMIT = 100;
const RULE_LIST_LIMIT = 500;
const DELIVERY_SUMMARY_SCAN_LIMIT = 10000;

export const alertStatusValidator = v.union(
  v.literal("draft"),
  v.literal("scheduled"),
  v.literal("sending"),
  v.literal("completed"),
  v.literal("canceled"),
);

// States a provider callback can move a delivery into (created/scheduled are
// set by us; a callback never regresses to those).
export const deliveryCallbackStateValidator = v.union(
  v.literal("sent"),
  v.literal("delivered"),
  v.literal("read"),
  v.literal("replied"),
  v.literal("failed"),
);

export type DeliveryCallbackState = "sent" | "delivered" | "read" | "replied" | "failed";
export type DeliverySummary = {
  total: number;
  capped: boolean;
  byState: Record<Doc<"alertDeliveries">["state"], number>;
};

// --- Alerts ------------------------------------------------------------

export const loadAlertForOrg = async (
  ctx: QueryCtx,
  organizationId: string,
  alertId: Id<"alerts">,
): Promise<Doc<"alerts"> | null> => {
  const alert = await ctx.db.get(alertId);
  if (!alert || alert.organizationId !== organizationId) return null;
  return alert;
};

export const createAlertForOrg = async (
  ctx: MutationCtx,
  organizationId: string,
  creatorMemberId: string,
  input: { message: string; sourceVersionId?: Id<"knowledgeSourceVersions"> },
  now: number,
): Promise<Id<"alerts">> =>
  ctx.db.insert("alerts", {
    organizationId,
    creatorMemberId,
    message: input.message,
    status: "draft",
    createdAt: now,
    ...(input.sourceVersionId !== undefined ? { sourceVersionId: input.sourceVersionId } : {}),
  });

export const addAudienceRule = async (
  ctx: MutationCtx,
  organizationId: string,
  alertId: Id<"alerts">,
  rule: { kind: Doc<"alertAudienceRules">["kind"]; targetKey: string; snapshotAt?: number },
): Promise<Id<"alertAudienceRules">> => {
  const alert = await loadAlertForOrg(ctx, organizationId, alertId);
  if (!alert) throw new ConvexError("Unauthorized");
  return ctx.db.insert("alertAudienceRules", {
    alertId: alert._id,
    kind: rule.kind,
    targetKey: rule.targetKey,
    ...(rule.snapshotAt !== undefined ? { snapshotAt: rule.snapshotAt } : {}),
  });
};

export const listAlertsForOrg = async (
  ctx: QueryCtx,
  organizationId: string,
  options: { status?: Doc<"alerts">["status"]; limit?: number },
): Promise<Doc<"alerts">[]> => {
  const limit = Math.min(options.limit ?? 50, ALERT_LIST_LIMIT);
  return ctx.db
    .query("alerts")
    .withIndex("by_organizationId_and_status", (q) =>
      options.status
        ? q.eq("organizationId", organizationId).eq("status", options.status)
        : q.eq("organizationId", organizationId),
    )
    .order("desc")
    .take(limit);
};

const summarizeDeliveries = async (
  ctx: QueryCtx,
  alertId: Id<"alerts">,
): Promise<DeliverySummary> => {
  const deliveries = await ctx.db
    .query("alertDeliveries")
    .withIndex("by_alertId_and_state", (q) => q.eq("alertId", alertId))
    .take(DELIVERY_SUMMARY_SCAN_LIMIT);
  const byState: DeliverySummary["byState"] = {
    created: 0,
    scheduled: 0,
    sent: 0,
    delivered: 0,
    read: 0,
    replied: 0,
    failed: 0,
  };
  for (const delivery of deliveries) byState[delivery.state] += 1;
  return {
    total: deliveries.length,
    capped: deliveries.length === DELIVERY_SUMMARY_SCAN_LIMIT,
    byState,
  };
};

export const getAlertDetail = async (ctx: QueryCtx, alert: Doc<"alerts">) => {
  const rules = await ctx.db
    .query("alertAudienceRules")
    .withIndex("by_alertId", (q) => q.eq("alertId", alert._id))
    .take(RULE_LIST_LIMIT);
  const deliverySummary = await summarizeDeliveries(ctx, alert._id);
  return { alert, rules, deliverySummary };
};

export const getAlertForOrg = async (
  ctx: QueryCtx,
  organizationId: string,
  alertId: Id<"alerts">,
) => {
  const alert = await loadAlertForOrg(ctx, organizationId, alertId);
  return alert ? getAlertDetail(ctx, alert) : null;
};

// --- Deliveries --------------------------------------------------------

// One alertDeliveries row per farmer, state "created". No provider API call is
// made here — the external WhatsApp gateway is not ready yet.
export const createDeliveriesForOrg = async (
  ctx: MutationCtx,
  organizationId: string,
  alertId: Id<"alerts">,
  farmerIds: Id<"farmers">[],
  now: number,
): Promise<number> => {
  for (const farmerId of farmerIds) {
    await ctx.db.insert("alertDeliveries", {
      organizationId,
      alertId,
      farmerId,
      provider: "whatsapp",
      state: "created",
      attemptCount: 0,
      createdAt: now,
    });
  }
  return farmerIds.length;
};

// Delivery state ranks. WhatsApp callbacks can arrive out of order, so a state
// only ever advances: a late "delivered" after "read" is ignored, and terminal
// outcomes (replied/failed) never regress to a progress state.
const DELIVERY_RANK: Record<Doc<"alertDeliveries">["state"], number> = {
  created: 0,
  scheduled: 1,
  sent: 2,
  delivered: 3,
  read: 4,
  replied: 5,
  failed: 5,
};

const applyDeliveryState = async (
  ctx: MutationCtx,
  delivery: Doc<"alertDeliveries">,
  state: Doc<"alertDeliveries">["state"],
) => {
  if (DELIVERY_RANK[state] <= DELIVERY_RANK[delivery.state]) return delivery._id;
  await ctx.db.patch(delivery._id, {
    state,
    ...(state === "failed" ? { attemptCount: delivery.attemptCount + 1 } : {}),
  });
  return delivery._id;
};

export const setDeliveryStateByProviderMessageId = async (
  ctx: MutationCtx,
  provider: string,
  providerMessageId: string,
  state: Doc<"alertDeliveries">["state"],
): Promise<Id<"alertDeliveries"> | null> => {
  const delivery = await ctx.db
    .query("alertDeliveries")
    .withIndex("by_provider_and_providerMessageId", (q) =>
      q.eq("provider", provider).eq("providerMessageId", providerMessageId),
    )
    .first();
  if (!delivery) return null;
  return applyDeliveryState(ctx, delivery, state);
};

export const setDeliveryStateByAlertAndFarmer = async (
  ctx: MutationCtx,
  alertId: Id<"alerts">,
  farmerId: Id<"farmers">,
  state: Doc<"alertDeliveries">["state"],
): Promise<Id<"alertDeliveries"> | null> => {
  const delivery = await ctx.db
    .query("alertDeliveries")
    .withIndex("by_alertId_and_farmerId", (q) =>
      q.eq("alertId", alertId).eq("farmerId", farmerId),
    )
    .first();
  if (!delivery) return null;
  return applyDeliveryState(ctx, delivery, state);
};

// Exposed for the conversations module: links a delivery to the conversation
// context an inbound reply ("Et pour mon cacao ?") opened from this alert.
export const setDeliveryConversation = async (
  ctx: MutationCtx,
  deliveryId: Id<"alertDeliveries">,
  conversationContextId: Id<"conversationContexts">,
): Promise<void> => {
  await ctx.db.patch(deliveryId, { conversationContextId });
};
