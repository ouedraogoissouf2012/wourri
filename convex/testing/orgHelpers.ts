import type { MutationCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import { ROLE_PRESETS } from "../authz/capabilities";
import type { EntitlementFixture } from "./fixtures";

// §38 / §4 — org-level seed helpers (production guard, linguist role policy,
// idempotent member role assignment, manual entitlements). All operate on an
// explicit organizationId so nothing is derived from a session.

// GARDE-FOU (§38, §4): this seed must NEVER run in production. It reads
// process.env through globalThis (no direct process ref, safe in the Convex
// runtime) and refuses when the environment looks like production.
export const guardNotProduction = (): void => {
  const env =
    (globalThis as { process?: { env?: Record<string, string | undefined> } })
      .process?.env ?? {};
  if (env.WOURI_ENV === "production") {
    throw new Error("Seed refuse en production");
  }
};

// Insert the "linguist" role policy for an org (provisionOrganization does not
// create it from any preset). Idempotent on (organizationId, key).
export const ensureLinguistPolicy = async (
  ctx: MutationCtx,
  organizationId: string,
): Promise<Id<"organizationRolePolicies">> => {
  const existing = await ctx.db
    .query("organizationRolePolicies")
    .withIndex("by_organizationId_and_key", (q) =>
      q.eq("organizationId", organizationId).eq("key", "linguist"),
    )
    .unique();
  if (existing) {
    await ctx.db.patch(existing._id, { permissions: [...ROLE_PRESETS.linguist] });
    return existing._id;
  }
  return ctx.db.insert("organizationRolePolicies", {
    organizationId,
    key: "linguist",
    permissions: [...ROLE_PRESETS.linguist],
    scopeMode: "organization",
  });
};

// Idempotently assign a member to a role policy: skip when an active assignment
// to the same policy already exists, else append one.
export const ensureMemberRole = async (
  ctx: MutationCtx,
  organizationId: string,
  memberId: string,
  rolePolicyKey: string,
): Promise<Id<"memberRoleAssignments">> => {
  const policy = await ctx.db
    .query("organizationRolePolicies")
    .withIndex("by_organizationId_and_key", (q) =>
      q.eq("organizationId", organizationId).eq("key", rolePolicyKey),
    )
    .unique();
  if (!policy) {
    throw new Error(
      `Unknown role policy "${rolePolicyKey}" for org "${organizationId}"`,
    );
  }
  const active = await ctx.db
    .query("memberRoleAssignments")
    .withIndex("by_organizationId_and_memberId_and_status", (q) =>
      q
        .eq("organizationId", organizationId)
        .eq("memberId", memberId)
        .eq("status", "active"),
    )
    .collect();
  const already = active.find((a) => a.rolePolicyId === policy._id);
  if (already) return already._id;
  return ctx.db.insert("memberRoleAssignments", {
    organizationId,
    memberId,
    rolePolicyId: policy._id,
    status: "active",
    assignedAt: Date.now(),
  });
};

// Insert a manual entitlement. Idempotent on (organizationId, key).
export const ensureEntitlement = async (
  ctx: MutationCtx,
  fixture: EntitlementFixture,
): Promise<Id<"organizationEntitlements">> => {
  const existing = await ctx.db
    .query("organizationEntitlements")
    .withIndex("by_organizationId_and_key", (q) =>
      q.eq("organizationId", fixture.organizationId).eq("key", fixture.key),
    )
    .unique();
  // Build the doc dynamically so `limit` is omitted (never undefined) when absent.
  const doc = {
    organizationId: fixture.organizationId,
    key: fixture.key,
    enabled: fixture.enabled,
    validFrom: 0,
    source: "manual" as const,
    ...(fixture.limit !== undefined ? { limit: fixture.limit } : {}),
  };
  if (existing) {
    await ctx.db.patch(existing._id, doc);
    return existing._id;
  }
  return ctx.db.insert("organizationEntitlements", doc);
};
