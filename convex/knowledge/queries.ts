import { v } from "convex/values";
import { query, internalQuery } from "../_generated/server";
import { authorize, CAPABILITIES } from "../authorization";
import * as model from "./model";

export const listKnowledgeSources = query({
  args: {},
  handler: async (ctx) => {
    const auth = await authorize(ctx, { permission: CAPABILITIES.knowledgeRead });
    return model.listSourcesVisibleToOrg(ctx, auth.organizationId);
  },
});

export const getProvenance = query({
  args: { sourceVersionId: v.id("knowledgeSourceVersions") },
  handler: async (ctx, args) => {
    const auth = await authorize(ctx, { permission: CAPABILITIES.knowledgeRead });
    const visible = await model.sourceVersionVisibleToOrg(
      ctx,
      args.sourceVersionId,
      auth.organizationId,
    );
    if (!visible) return null;
    return visible;
  },
});

// Internal — resolves the tenant-checked ingest context for the ingest action.
export const ingestContext = internalQuery({
  args: {
    sourceVersionId: v.id("knowledgeSourceVersions"),
    organizationId: v.string(),
  },
  handler: async (ctx, args) => {
    const visible = await model.sourceVersionVisibleToOrg(
      ctx,
      args.sourceVersionId,
      args.organizationId,
    );
    if (!visible) return null;
    return {
      sourceId: visible.source._id,
      authority: visible.source.authority,
      visibility: visible.source.visibility,
      ownerOrganizationId: visible.source.organizationId ?? null,
      version: visible.version.version,
    };
  },
});
