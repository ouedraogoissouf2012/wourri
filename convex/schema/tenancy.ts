import { defineTable } from "convex/server";
import { v } from "convex/values";

const organizationKind = v.union(
  v.literal("sodexam"),
  v.literal("cnra"),
  v.literal("cooperative"),
  v.literal("ngo"),
);

export const tenancyTables = {
  organizationProfiles: defineTable({
    organizationId: v.string(),
    kind: organizationKind,
    legalName: v.string(),
    status: v.union(v.literal("active"), v.literal("suspended")),
    defaultZoneIds: v.array(v.string()),
  }).index("by_organizationId", ["organizationId"]),
  organizationRolePolicies: defineTable({
    organizationId: v.string(),
    key: v.string(),
    permissions: v.array(v.string()),
    scopeMode: v.union(v.literal("organization"), v.literal("restricted")),
  })
    .index("by_organizationId", ["organizationId"])
    .index("by_organizationId_and_key", ["organizationId", "key"]),
  memberRoleAssignments: defineTable({
    organizationId: v.string(),
    memberId: v.string(),
    rolePolicyId: v.id("organizationRolePolicies"),
    status: v.union(v.literal("active"), v.literal("revoked")),
    assignedAt: v.number(),
    revokedAt: v.optional(v.number()),
  })
    .index("by_organizationId_and_memberId", ["organizationId", "memberId"])
    .index("by_memberId_and_status", ["memberId", "status"]),
  membershipScopeGrants: defineTable({
    organizationId: v.string(),
    memberId: v.string(),
    scopeType: v.union(v.literal("zone"), v.literal("crop"), v.literal("group")),
    scopeKey: v.string(),
    grantedAt: v.number(),
    expiresAt: v.optional(v.number()),
  })
    .index("by_organizationId_and_memberId", ["organizationId", "memberId"])
    .index("by_memberId_and_scopeType", ["memberId", "scopeType"]),
};
