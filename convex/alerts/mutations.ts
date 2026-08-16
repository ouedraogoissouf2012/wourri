import { ConvexError, v } from "convex/values";
import { internalMutation, mutation } from "../_generated/server";
import type { MutationCtx } from "../_generated/server";
import type { AuthorizationContext } from "../authorization";
import { authorizeMutation, CAPABILITIES } from "../authorization";
import { recordAudit } from "../lib/audit";
import { ERROR_TYPES, WouriError } from "../lib/errors";
import {
  addAudienceRule,
  audienceRuleValidator,
  createAlertForOrg,
  createDeliveriesForOrg,
  deliveryCallbackStateValidator,
  loadAlertForOrg,
  resolveAudience,
  setDeliveryStateByProviderMessageId,
} from "./model";

// The actor's user subject is not part of AuthorizationContext; the session
// identity already passed the authorize() gate, so read it for the audit trail.
const actorSubjectFor = async (
  ctx: MutationCtx,
  auth: AuthorizationContext,
): Promise<string> => {
  const identity = await ctx.auth.getUserIdentity();
  return identity?.subject ?? auth.memberId;
};

// ALT-01 — create a draft alert. Publishing is a separate, more privileged step.
export const createAlert = mutation({
  args: {
    message: v.string(),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, { permission: CAPABILITIES.alertsCreate });
    const now = Date.now();
    const alertId = await createAlertForOrg(
      ctx,
      auth.organizationId,
      auth.memberId,
      {
        message: args.message,
        ...(args.sourceVersionId !== undefined ? { sourceVersionId: args.sourceVersionId } : {}),
      },
      now,
    );
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        actorSubject: await actorSubjectFor(ctx, auth),
        actorMemberId: auth.memberId,
        action: "alert.create",
        resourceType: "alert",
        resourceId: alertId,
        after: { status: "draft" },
      },
      now,
    );
    return alertId;
  },
});

// ALT-01 — attach a targeting rule to a draft alert.
export const addAlertAudienceRule = mutation({
  args: {
    alertId: v.id("alerts"),
    rule: audienceRuleValidator,
    snapshotAt: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, { permission: CAPABILITIES.alertsCreate });
    const ruleId = await addAudienceRule(ctx, auth.organizationId, args.alertId, {
      kind: args.rule.kind,
      targetKey: args.rule.targetKey,
      ...(args.snapshotAt !== undefined ? { snapshotAt: args.snapshotAt } : {}),
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        actorSubject: await actorSubjectFor(ctx, auth),
        actorMemberId: auth.memberId,
        action: "alert.audienceRule.add",
        resourceType: "alert",
        resourceId: args.alertId,
        after: { kind: args.rule.kind, targetKey: args.rule.targetKey },
      },
      Date.now(),
    );
    return ruleId;
  },
});

// ALT-01 / ALT-02 — publish: resolve the audience and materialize one delivery
// per farmer in state "created". No real WhatsApp send yet (gateway not ready);
// deliveries wait for the provider callback via recordDeliveryCallback.
export const publishAlert = mutation({
  args: { alertId: v.id("alerts") },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, { permission: CAPABILITIES.alertsPublish });
    const alert = await loadAlertForOrg(ctx, auth.organizationId, args.alertId);
    if (!alert) throw new ConvexError("Unauthorized");
    if (alert.status !== "draft" && alert.status !== "scheduled") {
      throw new WouriError(
        ERROR_TYPES.DELIVERY,
        "Alert can only be published from draft or scheduled status",
      );
    }
    const rules = await ctx.db
      .query("alertAudienceRules")
      .withIndex("by_alertId", (q) => q.eq("alertId", alert._id))
      .take(500);
    const farmerIds = await resolveAudience(
      ctx,
      auth.organizationId,
      rules.map((rule) => ({ kind: rule.kind, targetKey: rule.targetKey })),
    );
    const now = Date.now();
    const deliveriesCreated = await createDeliveriesForOrg(
      ctx,
      auth.organizationId,
      alert._id,
      farmerIds,
      now,
    );
    await ctx.db.patch(alert._id, { status: "sending" });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        actorSubject: await actorSubjectFor(ctx, auth),
        actorMemberId: auth.memberId,
        action: "alert.publish",
        resourceType: "alert",
        resourceId: alert._id,
        before: { status: alert.status },
        after: { status: "sending", deliveriesCreated },
      },
      now,
    );
    return { alertId: alert._id, deliveriesCreated, audienceSize: farmerIds.length };
  },
});

// Entry point for future WhatsApp delivery callbacks: match by providerMessageId
// and advance the delivery state (attemptCount bumps on failure). Internal only.
export const recordDeliveryCallback = internalMutation({
  args: {
    providerMessageId: v.string(),
    state: deliveryCallbackStateValidator,
    provider: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const provider = args.provider ?? "whatsapp";
    const deliveryId = await setDeliveryStateByProviderMessageId(
      ctx,
      provider,
      args.providerMessageId,
      args.state,
    );
    return { deliveryId };
  },
});
