import { v } from "convex/values";
import { internalMutation, mutation } from "../_generated/server";
import type { MutationCtx } from "../_generated/server";
import { ROLE_PRESETS, type RolePreset } from "../authz/capabilities";
import { authorizeMutation, CAPABILITIES } from "../authorization";
import { recordAudit } from "../lib/audit";
import { resolveAuditActor } from "../lib/actor";
import { WouriError, ERROR_TYPES } from "../lib/errors";

// DAT-02 / §10 — organization provisioning. Better Auth owns the organization,
// member and invitation records; these functions attach the WOURI profile,
// role policies (from the capability presets) and default zones, and flip the
// profile from provisioning to active. A new organization never gets implicit
// rights: activation is an explicit operator step.

const organizationKind = v.union(
  v.literal("adc"),
  v.literal("sodexam"),
  v.literal("cnra"),
  v.literal("cooperative"),
  v.literal("ngo"),
  v.literal("other"),
);

type OrganizationKind =
  | "adc"
  | "sodexam"
  | "cnra"
  | "cooperative"
  | "ngo"
  | "other";

const PRESETS_BY_KIND: Record<OrganizationKind, RolePreset[]> = {
  adc: ["adcAdmin"],
  sodexam: ["sodexamOperator"],
  cnra: ["cnraOperator"],
  cooperative: ["clientAdmin", "clientOperator"],
  ngo: ["clientAdmin", "clientOperator"],
  other: ["clientOperator"],
};

const upsertProfile = async (
  ctx: MutationCtx,
  organizationId: string,
  kind: OrganizationKind,
  legalName: string,
) => {
  const existing = await ctx.db
    .query("organizationProfiles")
    .withIndex("by_organizationId", (q) => q.eq("organizationId", organizationId))
    .unique();
  if (existing) {
    await ctx.db.patch(existing._id, { kind, legalName, status: "active" });
    return existing._id;
  }
  return ctx.db.insert("organizationProfiles", {
    organizationId,
    kind,
    legalName,
    status: "active",
  });
};

const ensureRolePolicies = async (
  ctx: MutationCtx,
  organizationId: string,
  kind: OrganizationKind,
) => {
  for (const preset of PRESETS_BY_KIND[kind]) {
    const existing = await ctx.db
      .query("organizationRolePolicies")
      .withIndex("by_organizationId_and_key", (q) =>
        q.eq("organizationId", organizationId).eq("key", preset),
      )
      .unique();
    const permissions = [...ROLE_PRESETS[preset]];
    if (existing) {
      await ctx.db.patch(existing._id, { permissions });
    } else {
      await ctx.db.insert("organizationRolePolicies", {
        organizationId,
        key: preset,
        permissions,
        scopeMode: "organization",
      });
    }
  }
};

// Internal — provisions an organization end to end. Used by the ADC console and
// the staging seed. Idempotent.
export const provisionOrganization = internalMutation({
  args: {
    organizationId: v.string(),
    kind: organizationKind,
    legalName: v.string(),
    defaultZoneIds: v.optional(v.array(v.string())),
  },
  handler: async (ctx, args) => {
    const profileId = await upsertProfile(
      ctx,
      args.organizationId,
      args.kind,
      args.legalName,
    );
    await ensureRolePolicies(ctx, args.organizationId, args.kind);
    for (const zoneId of args.defaultZoneIds ?? []) {
      const existing = await ctx.db
        .query("organizationDefaultZones")
        .withIndex("by_organizationId_and_zoneId", (q) =>
          q.eq("organizationId", args.organizationId).eq("zoneId", zoneId),
        )
        .unique();
      if (!existing) {
        await ctx.db.insert("organizationDefaultZones", {
          organizationId: args.organizationId,
          zoneId,
        });
      }
    }
    return profileId;
  },
});

// Internal — assigns a Better Auth member to one of the organization's role
// policies (append-only; the active-most-recent assignment wins).
export const assignMemberRole = internalMutation({
  args: {
    organizationId: v.string(),
    memberId: v.string(),
    rolePolicyKey: v.string(),
  },
  handler: async (ctx, args) => {
    const policy = await ctx.db
      .query("organizationRolePolicies")
      .withIndex("by_organizationId_and_key", (q) =>
        q.eq("organizationId", args.organizationId).eq("key", args.rolePolicyKey),
      )
      .unique();
    if (!policy) {
      throw new WouriError(ERROR_TYPES.INTERNAL, "Unknown role policy");
    }
    return ctx.db.insert("memberRoleAssignments", {
      organizationId: args.organizationId,
      memberId: args.memberId,
      rolePolicyId: policy._id,
      status: "active",
      assignedAt: Date.now(),
    });
  },
});

// Internal — grants a scope (zone/crop/group) to a member for restricted roles.
export const grantMemberScope = internalMutation({
  args: {
    organizationId: v.string(),
    memberId: v.string(),
    scopeType: v.union(v.literal("zone"), v.literal("crop"), v.literal("group")),
    scopeKey: v.string(),
    expiresAt: v.optional(v.number()),
  },
  handler: async (ctx, args) =>
    ctx.db.insert("membershipScopeGrants", {
      organizationId: args.organizationId,
      memberId: args.memberId,
      scopeType: args.scopeType,
      scopeKey: args.scopeKey,
      grantedAt: Date.now(),
      expiresAt: args.expiresAt,
    }),
});

// Public — an ADC platform operator activates a provisioning organization.
export const activateOrganization = mutation({
  args: {
    organizationId: v.string(),
    kind: organizationKind,
    legalName: v.string(),
    defaultZoneIds: v.optional(v.array(v.string())),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.platformManage,
    });
    const now = Date.now();
    const profileId = await upsertProfile(
      ctx,
      args.organizationId,
      args.kind,
      args.legalName,
    );
    await ensureRolePolicies(ctx, args.organizationId, args.kind);
    await recordAudit(
      ctx,
      {
        organizationId: args.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "organization.activate",
        resourceType: "organizationProfiles",
        resourceId: profileId,
        after: { kind: args.kind, legalName: args.legalName },
      },
      now,
    );
    return profileId;
  },
});
