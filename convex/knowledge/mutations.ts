import { v } from "convex/values";
import { mutation, internalMutation } from "../_generated/server";
import { authorizeMutation, CAPABILITIES } from "../authorization";
import { recordAudit } from "../lib/audit";
import { resolveAuditActor } from "../lib/actor";
import { WouriError, ERROR_TYPES } from "../lib/errors";
import * as model from "./model";

// KNO-01/KNO-03 — register a knowledge source (SODEXAM/CNRA). A global source is
// published platform-wide; an organization source is scoped to the caller's org.
export const createKnowledgeSource = mutation({
  args: {
    visibility: v.union(v.literal("global"), v.literal("organization")),
    authority: v.string(),
    license: v.string(),
    canonicalLocator: v.string(),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.sourcesPublish,
    });
    const now = Date.now();
    const sourceId = await model.createSource(ctx, {
      organizationId:
        args.visibility === "organization" ? auth.organizationId : undefined,
      visibility: args.visibility,
      authority: args.authority,
      license: args.license,
      canonicalLocator: args.canonicalLocator,
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "knowledge.source.create",
        resourceType: "knowledgeSources",
        resourceId: sourceId,
        after: { authority: args.authority, visibility: args.visibility },
      },
      now,
    );
    return sourceId;
  },
});

export const createKnowledgeSourceVersion = mutation({
  args: {
    sourceId: v.id("knowledgeSources"),
    version: v.string(),
    contentHash: v.string(),
    acquisitionMethod: v.string(),
    publisherMetadata: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.sourcesPublish,
    });
    const source = await model.getSource(ctx, args.sourceId);
    if (
      !source ||
      (source.visibility === "organization" &&
        source.organizationId !== auth.organizationId)
    ) {
      throw new WouriError(ERROR_TYPES.PERMISSION, "Source not accessible");
    }
    const now = Date.now();
    const versionId = await model.createSourceVersion(ctx, {
      sourceId: args.sourceId,
      version: args.version,
      contentHash: args.contentHash,
      acquiredAt: now,
      acquisitionMethod: args.acquisitionMethod,
      publisherMetadata: args.publisherMetadata,
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "knowledge.sourceVersion.create",
        resourceType: "knowledgeSourceVersions",
        resourceId: versionId,
        after: { version: args.version },
      },
      now,
    );
    return versionId;
  },
});

// Internal — creates the document provenance row for the ingest action after the
// RAG entry is stored. Not public: ingestion is driven by the ingest action.
export const createDocumentRow = internalMutation({
  args: {
    sourceVersionId: v.id("knowledgeSourceVersions"),
    title: v.string(),
    locator: v.string(),
    language: v.string(),
    mimeType: v.string(),
    contentHash: v.string(),
  },
  handler: async (ctx, args) => model.createDocument(ctx, args),
});
