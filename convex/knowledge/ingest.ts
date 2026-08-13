import { v } from "convex/values";
import { action } from "../_generated/server";
import { internal } from "../_generated/api";
import type { Id } from "../_generated/dataModel";
import { CAPABILITIES } from "../authorization";
import { WouriError, ERROR_TYPES } from "../lib/errors";
import { rag, knowledgeNamespace, type KnowledgeFilters } from "../rag";

const contentHash = (text: string): string => {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
};

// KNO-03 / KNO-04 — ingest a CNRA (or any) document: authorize, tenant-check the
// source version, store the searchable content in the RAG namespace with
// provenance filters, then record the document row. Runs as an action because
// embeddings are computed outside a transaction.
export const ingestDocument = action({
  args: {
    sourceVersionId: v.id("knowledgeSourceVersions"),
    title: v.string(),
    locator: v.string(),
    language: v.string(),
    text: v.string(),
    zone: v.optional(v.string()),
    culture: v.optional(v.string()),
    mimeType: v.optional(v.string()),
  },
  handler: async (
    ctx,
    args,
  ): Promise<{ documentId: Id<"knowledgeDocuments">; entryId: string }> => {
    const auth = await ctx.runQuery(
      internal.authz.checkAccess.requireCapability,
      { permission: CAPABILITIES.knowledgeIngest },
    );
    const context = await ctx.runQuery(internal.knowledge.queries.ingestContext, {
      sourceVersionId: args.sourceVersionId,
      organizationId: auth.organizationId,
    });
    if (!context) {
      throw new WouriError(ERROR_TYPES.SOURCE, "Source version not accessible");
    }

    const documentId: Id<"knowledgeDocuments"> = await ctx.runMutation(
      internal.knowledge.mutations.createDocumentRow,
      {
        sourceVersionId: args.sourceVersionId,
        title: args.title,
        locator: args.locator,
        language: args.language,
        mimeType: args.mimeType ?? "text/plain",
        contentHash: contentHash(args.text),
      },
    );

    const filterValues: Array<{
      name: keyof KnowledgeFilters;
      value: string;
    }> = [
      { name: "sourceId", value: context.sourceId },
      { name: "sourceVersionId", value: args.sourceVersionId },
      { name: "authority", value: context.authority },
      { name: "language", value: args.language },
      { name: "version", value: context.version },
    ];
    if (args.zone) filterValues.push({ name: "zone", value: args.zone });
    if (args.culture) filterValues.push({ name: "culture", value: args.culture });

    const { entryId } = await rag.add(ctx, {
      namespace: knowledgeNamespace(
        context.visibility,
        context.ownerOrganizationId ?? undefined,
      ),
      key: documentId,
      title: args.title,
      text: args.text,
      filterValues,
    });

    return { documentId, entryId };
  },
});
