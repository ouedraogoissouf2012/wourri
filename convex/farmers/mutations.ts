import { v } from "convex/values";
import { mutation } from "../_generated/server";
import type { MutationCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import { authorizeMutation, CAPABILITIES } from "../authorization";
import type { AuthorizationContext } from "../authorization";
import { requireEntitlement } from "../lib/entitlements";
import { recordAudit } from "../lib/audit";
import { ERROR_TYPES, WouriError } from "../lib/errors";
import * as model from "./model";

// DAT-04 / §15 — public write surface for the FARMERS domain. Every mutation
// authorizes via authorizeMutation() (session-derived org) THEN delegates to
// org-scoped model helpers with auth.organizationId — never a client-supplied org.

const MAX_FARMERS_KEY = "maxFarmers";

// Resolve the audit actor from the verified session identity; falls back to the
// member id so the log never carries an empty subject.
const auditActor = async (ctx: MutationCtx, auth: AuthorizationContext) => {
  const identity = await ctx.auth.getUserIdentity();
  return {
    actorSubject: identity?.subject ?? auth.memberId,
    actorMemberId: auth.memberId,
  };
};

// Load a farmer proven to belong to the caller's org, or fail closed.
const requireOrgFarmer = async (
  ctx: MutationCtx,
  organizationId: string,
  farmerId: Id<"farmers">,
) => {
  const farmer = await model.getFarmerForOrg(ctx, organizationId, farmerId);
  if (!farmer) {
    throw new WouriError(ERROR_TYPES.PERMISSION, "Farmer not found in organization");
  }
  return farmer;
};

export const registerFarmer = mutation({
  args: { externalIdentityHash: v.string() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.farmersWrite,
    });
    const now = Date.now();
    const existing = await model.getFarmerByExternalHash(
      ctx,
      auth.organizationId,
      args.externalIdentityHash,
    );
    if (existing) {
      throw new WouriError(
        ERROR_TYPES.PERMISSION,
        "Farmer already registered for this organization",
      );
    }
    const entitlement = await requireEntitlement(
      ctx,
      auth.organizationId,
      MAX_FARMERS_KEY,
      now,
    );
    if (entitlement.limit !== undefined) {
      const bounded = await model.countActiveFarmersBounded(
        ctx,
        auth.organizationId,
        entitlement.limit + 1,
      );
      if (bounded + 1 > entitlement.limit) {
        throw new WouriError(
          ERROR_TYPES.PERMISSION,
          `Entitlement '${MAX_FARMERS_KEY}' limit of ${entitlement.limit} reached`,
        );
      }
    }
    const farmerId = await model.createFarmerForOrg(
      ctx,
      auth.organizationId,
      args.externalIdentityHash,
      now,
    );
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await auditActor(ctx, auth)),
        action: "farmer.register",
        resourceType: "farmers",
        resourceId: farmerId,
        after: { status: "active" },
      },
      now,
    );
    return farmerId;
  },
});

export const upsertFarmerProfile = mutation({
  args: {
    farmerId: v.id("farmers"),
    preferredLanguage: v.string(),
    countryCode: v.string(),
    notificationOptIn: v.boolean(),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.farmersWrite,
    });
    await requireOrgFarmer(ctx, auth.organizationId, args.farmerId);
    return model.upsertFarmerProfile(
      ctx,
      args.farmerId,
      {
        preferredLanguage: args.preferredLanguage,
        countryCode: args.countryCode,
        notificationOptIn: args.notificationOptIn,
      },
      Date.now(),
    );
  },
});

export const linkFarmerZone = mutation({
  args: { farmerId: v.id("farmers"), zoneId: v.string() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.farmersWrite,
    });
    await requireOrgFarmer(ctx, auth.organizationId, args.farmerId);
    return model.addZoneLink(ctx, auth.organizationId, args.farmerId, args.zoneId);
  },
});

export const linkFarmerCrop = mutation({
  args: { farmerId: v.id("farmers"), cropCode: v.string() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.farmersWrite,
    });
    await requireOrgFarmer(ctx, auth.organizationId, args.farmerId);
    return model.addCropLink(ctx, auth.organizationId, args.farmerId, args.cropCode);
  },
});

export const createFarmerGroup = mutation({
  args: { name: v.string() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.farmersWrite,
    });
    return model.createGroupForOrg(ctx, auth.organizationId, args.name);
  },
});

export const addFarmerToGroup = mutation({
  args: { groupId: v.id("farmerGroups"), farmerId: v.id("farmers") },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.farmersWrite,
    });
    const group = await model.getGroupForOrg(ctx, auth.organizationId, args.groupId);
    if (!group) {
      throw new WouriError(ERROR_TYPES.PERMISSION, "Group not found in organization");
    }
    await requireOrgFarmer(ctx, auth.organizationId, args.farmerId);
    return model.addGroupMember(ctx, auth.organizationId, args.groupId, args.farmerId);
  },
});

export const recordConsent = mutation({
  args: {
    farmerId: v.id("farmers"),
    purpose: v.string(),
    policyVersion: v.string(),
    state: v.union(v.literal("granted"), v.literal("withdrawn")),
    captureSource: v.string(),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.consentsWrite,
    });
    await requireOrgFarmer(ctx, auth.organizationId, args.farmerId);
    const now = Date.now();
    const consentId = await model.addConsent(
      ctx,
      args.farmerId,
      args.purpose,
      args.policyVersion,
      args.state,
      args.captureSource,
      now,
    );
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await auditActor(ctx, auth)),
        action: "farmer.consent.record",
        resourceType: "farmerConsents",
        resourceId: consentId,
        after: { purpose: args.purpose, state: args.state },
      },
      now,
    );
    return consentId;
  },
});

// Opt-out (§15): writes a withdrawn state so downstream delivery can be blocked.
// policyVersion defaults to the farmer's latest recorded version for this purpose.
export const withdrawConsent = mutation({
  args: {
    farmerId: v.id("farmers"),
    purpose: v.string(),
    captureSource: v.string(),
    policyVersion: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.consentsWrite,
    });
    await requireOrgFarmer(ctx, auth.organizationId, args.farmerId);
    const latest = await model.latestConsent(ctx, args.farmerId, args.purpose);
    const policyVersion = args.policyVersion ?? latest?.policyVersion ?? "unknown";
    const now = Date.now();
    const consentId = await model.addConsent(
      ctx,
      args.farmerId,
      args.purpose,
      policyVersion,
      "withdrawn",
      args.captureSource,
      now,
    );
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await auditActor(ctx, auth)),
        action: "farmer.consent.withdraw",
        resourceType: "farmerConsents",
        resourceId: consentId,
        before: latest ? { state: latest.state } : undefined,
        after: { purpose: args.purpose, state: "withdrawn" },
      },
      now,
    );
    return consentId;
  },
});
