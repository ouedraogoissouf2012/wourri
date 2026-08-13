import { v } from "convex/values";
import { mutation, query } from "../_generated/server";
import type { MutationCtx, QueryCtx } from "../_generated/server";
import type { Doc } from "../_generated/dataModel";
import { authorize, authorizeMutation, CAPABILITIES } from "../authorization";
import { WouriError, ERROR_TYPES } from "../lib/errors";
import { auditAiops } from "./shared";

// AI-05 / §26 — versioned prompt/policy/model registry with controlled
// activation. The three registries share the same key/version/status shape, so
// the shared transitions are generic over a single literal table name (keeping
// every db call concrete for type safety, never a table-name union).

type RegistryTable = "promptVersions" | "policyVersions" | "modelConfigs";

// The three registries share the same key/version/status shape. Convex's query
// builder needs a literal table name, so we narrow the runtime value to one
// literal for typing — sound because the shared fields are identical across the
// three tables — and cast the read result back to the concrete table at the edge.
const asVersionTable = (table: RegistryTable) => table as "promptVersions";

// Next version = (highest existing version for the key) + 1.
async function nextVersion(
  ctx: MutationCtx,
  table: RegistryTable,
  key: string,
): Promise<number> {
  const latest = await ctx.db
    .query(asVersionTable(table))
    .withIndex("by_key_and_version", (q) => q.eq("key", key))
    .order("desc")
    .first();
  return (latest?.version ?? 0) + 1;
}

// Controlled activation: promote the target version to "active" and retire any
// previously active version for the same key.
async function activateVersion(
  ctx: MutationCtx,
  table: RegistryTable,
  key: string,
  version: number,
) {
  const literal = asVersionTable(table);
  const target = await ctx.db
    .query(literal)
    .withIndex("by_key_and_version", (q) =>
      q.eq("key", key).eq("version", version),
    )
    .unique();
  if (!target) {
    throw new WouriError(ERROR_TYPES.INTERNAL, `Unknown ${table} version`);
  }
  const actives = await ctx.db
    .query(literal)
    .withIndex("by_key_and_status", (q) =>
      q.eq("key", key).eq("status", "active"),
    )
    .take(32);
  for (const active of actives) {
    if (active._id !== target._id) {
      await ctx.db.patch(active._id, { status: "retired" });
    }
  }
  await ctx.db.patch(target._id, { status: "active" });
  return target;
}

// Reads the active version for a key. Exported so the pipeline can resolve the
// live prompt/policy/model without an authenticated session (testable directly).
async function activeVersion(ctx: QueryCtx, table: RegistryTable, key: string) {
  return ctx.db
    .query(asVersionTable(table))
    .withIndex("by_key_and_status", (q) =>
      q.eq("key", key).eq("status", "active"),
    )
    .first();
}

export const getActivePromptVersion = (ctx: QueryCtx, key: string) =>
  activeVersion(ctx, "promptVersions", key);
export const getActivePolicyVersion = (ctx: QueryCtx, key: string) =>
  activeVersion(ctx, "policyVersions", key) as Promise<Doc<"policyVersions"> | null>;
export const getActiveModelConfigVersion = (ctx: QueryCtx, key: string) =>
  activeVersion(ctx, "modelConfigs", key) as Promise<Doc<"modelConfigs"> | null>;

// --- Prompt registry -------------------------------------------------------

export const createPromptVersion = mutation({
  args: { key: v.string(), template: v.string() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const version = await nextVersion(ctx, "promptVersions", args.key);
    const id = await ctx.db.insert("promptVersions", {
      key: args.key,
      version,
      template: args.template,
      status: "draft",
      createdByMemberId: auth.memberId,
      createdAt: now,
    });
    await auditAiops(ctx, auth, now, {
      action: "aiops.prompt.create",
      resourceType: "promptVersions",
      resourceId: id,
      after: { key: args.key, version },
    });
    return { id, version };
  },
});

export const activatePromptVersion = mutation({
  args: { key: v.string(), version: v.number() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const target = await activateVersion(ctx, "promptVersions", args.key, args.version);
    await auditAiops(ctx, auth, now, {
      action: "aiops.prompt.activate",
      resourceType: "promptVersions",
      resourceId: target._id,
      after: { key: args.key, version: args.version },
    });
    return { id: target._id, version: target.version };
  },
});

export const getActivePrompt = query({
  args: { key: v.string() },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    return activeVersion(ctx, "promptVersions", args.key);
  },
});

// --- Policy registry -------------------------------------------------------

export const createPolicyVersion = mutation({
  args: { key: v.string(), definition: v.string() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const version = await nextVersion(ctx, "policyVersions", args.key);
    const id = await ctx.db.insert("policyVersions", {
      key: args.key,
      version,
      definition: args.definition,
      status: "draft",
      createdByMemberId: auth.memberId,
      createdAt: now,
    });
    await auditAiops(ctx, auth, now, {
      action: "aiops.policy.create",
      resourceType: "policyVersions",
      resourceId: id,
      after: { key: args.key, version },
    });
    return { id, version };
  },
});

export const activatePolicyVersion = mutation({
  args: { key: v.string(), version: v.number() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const target = await activateVersion(ctx, "policyVersions", args.key, args.version);
    await auditAiops(ctx, auth, now, {
      action: "aiops.policy.activate",
      resourceType: "policyVersions",
      resourceId: target._id,
      after: { key: args.key, version: args.version },
    });
    return { id: target._id, version: target.version };
  },
});

export const getActivePolicy = query({
  args: { key: v.string() },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    return activeVersion(ctx, "policyVersions", args.key);
  },
});

// --- Model config registry -------------------------------------------------

export const createModelConfig = mutation({
  args: {
    key: v.string(),
    provider: v.string(),
    model: v.string(),
    parameters: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const version = await nextVersion(ctx, "modelConfigs", args.key);
    const id = await ctx.db.insert("modelConfigs", {
      key: args.key,
      version,
      provider: args.provider,
      model: args.model,
      parameters: args.parameters,
      status: "draft",
      createdByMemberId: auth.memberId,
      createdAt: now,
    });
    await auditAiops(ctx, auth, now, {
      action: "aiops.modelConfig.create",
      resourceType: "modelConfigs",
      resourceId: id,
      after: { key: args.key, version },
    });
    return { id, version };
  },
});

export const activateModelConfig = mutation({
  args: { key: v.string(), version: v.number() },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.featureFlagsManage,
    });
    const now = Date.now();
    const target = await activateVersion(ctx, "modelConfigs", args.key, args.version);
    await auditAiops(ctx, auth, now, {
      action: "aiops.modelConfig.activate",
      resourceType: "modelConfigs",
      resourceId: target._id,
      after: { key: args.key, version: args.version },
    });
    return { id: target._id, version: target.version };
  },
});

export const getActiveModelConfig = query({
  args: { key: v.string() },
  handler: async (ctx, args) => {
    await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    return activeVersion(ctx, "modelConfigs", args.key);
  },
});
