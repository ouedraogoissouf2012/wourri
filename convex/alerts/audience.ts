import { v } from "convex/values";
import type { QueryCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";

// ALT-01 — audience targeting + tenant scoping. Every helper takes
// organizationId EXPLICITLY so the public functions stay the only place that
// reads the session, and the resolution is unit-testable in isolation.

// Bound every audience resolution so a large tenant can never blow the
// transaction budget. previewAudience and publishAlert share these ceilings.
const RULE_SCAN_LIMIT = 5000;
const MAX_AUDIENCE = 20000;

export const audienceKindValidator = v.union(
  v.literal("farmer"),
  v.literal("zone"),
  v.literal("crop"),
  v.literal("group"),
);

export const audienceRuleValidator = v.object({
  kind: audienceKindValidator,
  targetKey: v.string(),
});

export type AudienceRule = { kind: "farmer" | "zone" | "crop" | "group"; targetKey: string };

const resolveZone = async (ctx: QueryCtx, organizationId: string, zoneId: string) => {
  const links = await ctx.db
    .query("farmerZoneLinks")
    .withIndex("by_organizationId_and_zoneId", (q) =>
      q.eq("organizationId", organizationId).eq("zoneId", zoneId),
    )
    .take(RULE_SCAN_LIMIT);
  return links.map((link) => link.farmerId);
};

const resolveCrop = async (ctx: QueryCtx, organizationId: string, cropCode: string) => {
  const links = await ctx.db
    .query("farmerCropLinks")
    .withIndex("by_organizationId_and_cropCode", (q) =>
      q.eq("organizationId", organizationId).eq("cropCode", cropCode),
    )
    .take(RULE_SCAN_LIMIT);
  return links.map((link) => link.farmerId);
};

const resolveGroup = async (ctx: QueryCtx, organizationId: string, targetKey: string) => {
  const groupId = ctx.db.normalizeId("farmerGroups", targetKey);
  if (!groupId) return [];
  const members = await ctx.db
    .query("farmerGroupMembers")
    .withIndex("by_groupId_and_farmerId", (q) => q.eq("groupId", groupId))
    .take(RULE_SCAN_LIMIT);
  // by_groupId_and_farmerId is not org-scoped, so verify tenant on each row.
  return members
    .filter((member) => member.organizationId === organizationId)
    .map((member) => member.farmerId);
};

const resolveFarmer = async (ctx: QueryCtx, organizationId: string, targetKey: string) => {
  const farmerId = ctx.db.normalizeId("farmers", targetKey);
  if (!farmerId) return [];
  const farmer = await ctx.db.get(farmerId);
  if (!farmer || farmer.organizationId !== organizationId) return [];
  return [farmer._id];
};

const resolveRule = async (
  ctx: QueryCtx,
  organizationId: string,
  rule: AudienceRule,
): Promise<Id<"farmers">[]> => {
  switch (rule.kind) {
    case "zone":
      return resolveZone(ctx, organizationId, rule.targetKey);
    case "crop":
      return resolveCrop(ctx, organizationId, rule.targetKey);
    case "group":
      return resolveGroup(ctx, organizationId, rule.targetKey);
    case "farmer":
      return resolveFarmer(ctx, organizationId, rule.targetKey);
  }
};

// Union of all rules, deduplicated, restricted to farmers of organizationId.
export const resolveAudience = async (
  ctx: QueryCtx,
  organizationId: string,
  rules: AudienceRule[],
): Promise<Id<"farmers">[]> => {
  const seen = new Set<string>();
  const audience: Id<"farmers">[] = [];
  for (const rule of rules) {
    const farmerIds = await resolveRule(ctx, organizationId, rule);
    for (const farmerId of farmerIds) {
      if (seen.has(farmerId)) continue;
      seen.add(farmerId);
      audience.push(farmerId);
      if (audience.length >= MAX_AUDIENCE) return audience;
    }
  }
  return audience;
};
