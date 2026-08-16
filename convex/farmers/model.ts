import type { PaginationOptions, PaginationResult } from "convex/server";
import type { MutationCtx, QueryCtx } from "../_generated/server";
import type { Doc, Id } from "../_generated/dataModel";

// DAT-04 / §15 — org-scoped data access for the FARMERS domain. Every helper
// takes organizationId (or a farmer already proven to belong to the org)
// EXPLICITLY so tenant scoping can be exercised in tests without a session.

type Ctx = QueryCtx | MutationCtx;

export type ConsentState = "granted" | "withdrawn";

export type FarmerProfileInput = {
  preferredLanguage: string;
  countryCode: string;
  notificationOptIn: boolean;
};

// Farmers -------------------------------------------------------------------

export const getFarmerByExternalHash = async (
  ctx: Ctx,
  organizationId: string,
  externalIdentityHash: string,
): Promise<Doc<"farmers"> | null> =>
  ctx.db
    .query("farmers")
    .withIndex("by_organizationId_and_externalIdentityHash", (q) =>
      q
        .eq("organizationId", organizationId)
        .eq("externalIdentityHash", externalIdentityHash),
    )
    .unique();

// Returns the farmer only when it belongs to the org, else null (fail closed).
export const getFarmerForOrg = async (
  ctx: Ctx,
  organizationId: string,
  farmerId: Id<"farmers">,
): Promise<Doc<"farmers"> | null> => {
  const farmer = await ctx.db.get(farmerId);
  if (!farmer || farmer.organizationId !== organizationId) return null;
  return farmer;
};

// Bounded active-farmer count: reads at most `cap` rows. Enough to enforce a
// plan limit (cap = limit + 1) without scanning a whole tenant, which would
// break registration for the largest customers.
export const countActiveFarmersBounded = async (
  ctx: Ctx,
  organizationId: string,
  cap: number,
): Promise<number> => {
  const farmers = await ctx.db
    .query("farmers")
    .withIndex("by_organizationId_and_status", (q) =>
      q.eq("organizationId", organizationId).eq("status", "active"),
    )
    .take(cap);
  return farmers.length;
};

export const listFarmersForOrg = async (
  ctx: Ctx,
  organizationId: string,
  paginationOpts: PaginationOptions,
): Promise<PaginationResult<Doc<"farmers">>> =>
  ctx.db
    .query("farmers")
    .withIndex("by_organizationId_and_status", (q) =>
      q.eq("organizationId", organizationId),
    )
    .order("desc")
    .paginate(paginationOpts);

export const createFarmerForOrg = async (
  ctx: MutationCtx,
  organizationId: string,
  externalIdentityHash: string,
  now: number,
): Promise<Id<"farmers">> =>
  ctx.db.insert("farmers", {
    organizationId,
    externalIdentityHash,
    status: "active",
    createdAt: now,
  });

// Profiles ------------------------------------------------------------------

export const getFarmerProfileForFarmer = async (
  ctx: Ctx,
  farmerId: Id<"farmers">,
): Promise<Doc<"farmerProfiles"> | null> =>
  ctx.db
    .query("farmerProfiles")
    .withIndex("by_farmerId", (q) => q.eq("farmerId", farmerId))
    .unique();

export const upsertFarmerProfile = async (
  ctx: MutationCtx,
  farmerId: Id<"farmers">,
  input: FarmerProfileInput,
  now: number,
): Promise<Id<"farmerProfiles">> => {
  const existing = await getFarmerProfileForFarmer(ctx, farmerId);
  if (existing) {
    await ctx.db.patch(existing._id, { ...input, updatedAt: now });
    return existing._id;
  }
  return ctx.db.insert("farmerProfiles", { farmerId, ...input, updatedAt: now });
};

// Zone & crop links ---------------------------------------------------------

export const listZoneLinksForFarmer = async (
  ctx: Ctx,
  farmerId: Id<"farmers">,
): Promise<Doc<"farmerZoneLinks">[]> =>
  ctx.db
    .query("farmerZoneLinks")
    .withIndex("by_farmerId_and_zoneId", (q) => q.eq("farmerId", farmerId))
    .collect();

export const addZoneLink = async (
  ctx: MutationCtx,
  organizationId: string,
  farmerId: Id<"farmers">,
  zoneId: string,
): Promise<Id<"farmerZoneLinks">> => {
  const existing = await ctx.db
    .query("farmerZoneLinks")
    .withIndex("by_farmerId_and_zoneId", (q) =>
      q.eq("farmerId", farmerId).eq("zoneId", zoneId),
    )
    .unique();
  if (existing) return existing._id;
  return ctx.db.insert("farmerZoneLinks", { organizationId, farmerId, zoneId });
};

export const listCropLinksForFarmer = async (
  ctx: Ctx,
  farmerId: Id<"farmers">,
): Promise<Doc<"farmerCropLinks">[]> =>
  ctx.db
    .query("farmerCropLinks")
    .withIndex("by_farmerId_and_cropCode", (q) => q.eq("farmerId", farmerId))
    .collect();

export const addCropLink = async (
  ctx: MutationCtx,
  organizationId: string,
  farmerId: Id<"farmers">,
  cropCode: string,
): Promise<Id<"farmerCropLinks">> => {
  const existing = await ctx.db
    .query("farmerCropLinks")
    .withIndex("by_farmerId_and_cropCode", (q) =>
      q.eq("farmerId", farmerId).eq("cropCode", cropCode),
    )
    .unique();
  if (existing) return existing._id;
  return ctx.db.insert("farmerCropLinks", { organizationId, farmerId, cropCode });
};

// Groups --------------------------------------------------------------------

export const createGroupForOrg = async (
  ctx: MutationCtx,
  organizationId: string,
  name: string,
): Promise<Id<"farmerGroups">> =>
  ctx.db.insert("farmerGroups", { organizationId, name, status: "active" });

export const getGroupForOrg = async (
  ctx: Ctx,
  organizationId: string,
  groupId: Id<"farmerGroups">,
): Promise<Doc<"farmerGroups"> | null> => {
  const group = await ctx.db.get(groupId);
  if (!group || group.organizationId !== organizationId) return null;
  return group;
};

export const listGroupsForOrg = async (
  ctx: Ctx,
  organizationId: string,
): Promise<Doc<"farmerGroups">[]> =>
  ctx.db
    .query("farmerGroups")
    .withIndex("by_organizationId", (q) => q.eq("organizationId", organizationId))
    .order("desc")
    .take(200);

export const addGroupMember = async (
  ctx: MutationCtx,
  organizationId: string,
  groupId: Id<"farmerGroups">,
  farmerId: Id<"farmers">,
): Promise<Id<"farmerGroupMembers">> => {
  const existing = await ctx.db
    .query("farmerGroupMembers")
    .withIndex("by_groupId_and_farmerId", (q) =>
      q.eq("groupId", groupId).eq("farmerId", farmerId),
    )
    .unique();
  if (existing) return existing._id;
  return ctx.db.insert("farmerGroupMembers", { organizationId, groupId, farmerId });
};

// Consents (§15) ------------------------------------------------------------

export const addConsent = async (
  ctx: MutationCtx,
  farmerId: Id<"farmers">,
  purpose: string,
  policyVersion: string,
  state: ConsentState,
  captureSource: string,
  now: number,
): Promise<Id<"farmerConsents">> =>
  ctx.db.insert("farmerConsents", {
    farmerId,
    purpose,
    policyVersion,
    state,
    captureSource,
    recordedAt: now,
  });

// Latest state for a (farmerId, purpose) = most recent row on the descending
// (farmerId, purpose, recordedAt) index.
export const latestConsent = async (
  ctx: Ctx,
  farmerId: Id<"farmers">,
  purpose: string,
): Promise<Doc<"farmerConsents"> | null> =>
  ctx.db
    .query("farmerConsents")
    .withIndex("by_farmerId_and_purpose_and_recordedAt", (q) =>
      q.eq("farmerId", farmerId).eq("purpose", purpose),
    )
    .order("desc")
    .first();

export const isOptedIn = async (
  ctx: Ctx,
  farmerId: Id<"farmers">,
  purpose: string,
): Promise<boolean> => {
  const latest = await latestConsent(ctx, farmerId, purpose);
  return latest?.state === "granted";
};

export const listConsentsForFarmer = async (
  ctx: Ctx,
  farmerId: Id<"farmers">,
): Promise<Doc<"farmerConsents">[]> =>
  ctx.db
    .query("farmerConsents")
    .withIndex("by_farmerId_and_purpose_and_recordedAt", (q) =>
      q.eq("farmerId", farmerId),
    )
    .order("desc")
    .take(100);
