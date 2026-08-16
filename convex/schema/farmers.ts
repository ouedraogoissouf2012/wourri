import { defineTable } from "convex/server";
import { v } from "convex/values";

export const farmerTables = {
  farmers: defineTable({
    organizationId: v.string(),
    externalIdentityHash: v.string(),
    status: v.union(v.literal("active"), v.literal("archived")),
    createdAt: v.number(),
  })
    .index("by_organizationId_and_externalIdentityHash", [
      "organizationId",
      "externalIdentityHash",
    ])
    .index("by_organizationId_and_status", ["organizationId", "status"]),
  farmerProfiles: defineTable({
    farmerId: v.id("farmers"),
    preferredLanguage: v.string(),
    countryCode: v.string(),
    notificationOptIn: v.boolean(),
    updatedAt: v.number(),
  }).index("by_farmerId", ["farmerId"]),
  farmerZoneLinks: defineTable({
    organizationId: v.string(),
    farmerId: v.id("farmers"),
    zoneId: v.string(),
  })
    .index("by_organizationId_and_zoneId", ["organizationId", "zoneId"])
    .index("by_farmerId_and_zoneId", ["farmerId", "zoneId"]),
  farmerCropLinks: defineTable({
    organizationId: v.string(),
    farmerId: v.id("farmers"),
    cropCode: v.string(),
  })
    .index("by_organizationId_and_cropCode", ["organizationId", "cropCode"])
    .index("by_farmerId_and_cropCode", ["farmerId", "cropCode"]),
  farmerGroups: defineTable({
    organizationId: v.string(),
    name: v.string(),
    status: v.union(v.literal("active"), v.literal("archived")),
  }).index("by_organizationId", ["organizationId"]),
  farmerGroupMembers: defineTable({
    organizationId: v.string(),
    groupId: v.id("farmerGroups"),
    farmerId: v.id("farmers"),
  })
    .index("by_groupId_and_farmerId", ["groupId", "farmerId"])
    .index("by_farmerId", ["farmerId"]),
  farmerConsents: defineTable({
    farmerId: v.id("farmers"),
    purpose: v.string(),
    policyVersion: v.string(),
    state: v.union(v.literal("granted"), v.literal("withdrawn")),
    captureSource: v.string(),
    recordedAt: v.number(),
  }).index("by_farmerId_and_purpose_and_recordedAt", [
    "farmerId",
    "purpose",
    "recordedAt",
  ]),
};
