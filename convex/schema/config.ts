import { defineTable } from "convex/server";
import { v } from "convex/values";

const environment = v.union(v.literal("staging"), v.literal("production"));
const registryStatus = v.union(
  v.literal("draft"),
  v.literal("active"),
  v.literal("retired"),
);

export const configTables = {
  // AI-06 / §27 — feature flags scoped by environment and optionally organization.
  featureFlags: defineTable({
    key: v.string(),
    environment,
    // undefined = flag applies to the whole environment; a value overrides per org.
    organizationId: v.optional(v.string()),
    enabled: v.boolean(),
    description: v.optional(v.string()),
    updatedByMemberId: v.optional(v.string()),
    updatedAt: v.number(),
  })
    .index("by_environment_and_key", ["environment", "key"])
    .index("by_environment_and_organizationId_and_key", [
      "environment",
      "organizationId",
      "key",
    ]),
  // AI-05 — versioned prompt registry. Never store provider secrets here.
  promptVersions: defineTable({
    key: v.string(),
    version: v.number(),
    template: v.string(),
    status: registryStatus,
    createdByMemberId: v.optional(v.string()),
    createdAt: v.number(),
  })
    .index("by_key_and_version", ["key", "version"])
    .index("by_key_and_status", ["key", "status"]),
  // AI-05 — versioned policy registry (anti-hallucination and guard policies).
  policyVersions: defineTable({
    key: v.string(),
    version: v.number(),
    definition: v.string(),
    status: registryStatus,
    createdByMemberId: v.optional(v.string()),
    createdAt: v.number(),
  })
    .index("by_key_and_version", ["key", "version"])
    .index("by_key_and_status", ["key", "status"]),
  // AI-05 — model configuration registry. Parameters only, never secrets.
  modelConfigs: defineTable({
    key: v.string(),
    version: v.number(),
    provider: v.string(),
    model: v.string(),
    parameters: v.optional(v.string()),
    status: registryStatus,
    createdByMemberId: v.optional(v.string()),
    createdAt: v.number(),
  })
    .index("by_key_and_version", ["key", "version"])
    .index("by_key_and_status", ["key", "status"]),
};
