import { v } from "convex/values";
import { mutation } from "../_generated/server";
import type { MutationCtx } from "../_generated/server";
import type { Doc } from "../_generated/dataModel";
import { authorizeMutation, CAPABILITIES } from "../authorization";
import { recordAudit } from "../lib/audit";
import { resolveAuditActor } from "../lib/actor";
import { WouriError, ERROR_TYPES } from "../lib/errors";

// G09 — promote a validated correction into the versioned glossary or corpus.
// A new version row is always appended; the previous version is never
// overwritten, so the correction history stays auditable.

const requireValidatedFeedback = async (
  ctx: MutationCtx,
  organizationId: string,
  feedbackId: Doc<"linguisticFeedback">["_id"],
) => {
  const feedback = await ctx.db.get(feedbackId);
  if (!feedback || feedback.organizationId !== organizationId) {
    throw new WouriError(ERROR_TYPES.PERMISSION, "Feedback not accessible");
  }
  if (feedback.status !== "validated") {
    throw new WouriError(
      ERROR_TYPES.PERMISSION,
      "Only a validated feedback can be promoted",
    );
  }
  return feedback;
};

export const promoteToGlossary = mutation({
  args: {
    feedbackId: v.id("linguisticFeedback"),
    normalizedKey: v.string(),
    definition: v.string(),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.linguisticValidate,
    });
    const feedback = await requireValidatedFeedback(
      ctx,
      auth.organizationId,
      args.feedbackId,
    );
    const now = Date.now();
    const head =
      (await ctx.db
        .query("glossaryTerms")
        .withIndex("by_organizationId_and_language_and_normalizedKey", (q) =>
          q
            .eq("organizationId", auth.organizationId)
            .eq("language", feedback.language)
            .eq("normalizedKey", args.normalizedKey),
        )
        .unique()) ??
      (await ctx.db.get(
        await ctx.db.insert("glossaryTerms", {
          organizationId: auth.organizationId,
          language: feedback.language,
          normalizedKey: args.normalizedKey,
          status: "approved",
        }),
      ))!;
    const last = await ctx.db
      .query("glossaryTermVersions")
      .withIndex("by_termId_and_version", (q) => q.eq("termId", head._id))
      .order("desc")
      .first();
    const version = (last?.version ?? 0) + 1;
    const versionId = await ctx.db.insert("glossaryTermVersions", {
      termId: head._id,
      version,
      definition: args.definition,
      reviewerMemberId: auth.memberId,
      approvedAt: now,
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "linguistic.glossary.promote",
        resourceType: "glossaryTermVersions",
        resourceId: versionId,
        after: { termId: head._id, version },
      },
      now,
    );
    return { termId: head._id, version };
  },
});

export const promoteToCorpus = mutation({
  args: {
    feedbackId: v.id("linguisticFeedback"),
    normalizedKey: v.string(),
    inputText: v.string(),
    outputText: v.string(),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.linguisticValidate,
    });
    const feedback = await requireValidatedFeedback(
      ctx,
      auth.organizationId,
      args.feedbackId,
    );
    const now = Date.now();
    const head =
      (await ctx.db
        .query("languageExamples")
        .withIndex("by_organizationId_and_language_and_normalizedKey", (q) =>
          q
            .eq("organizationId", auth.organizationId)
            .eq("language", feedback.language)
            .eq("normalizedKey", args.normalizedKey),
        )
        .unique()) ??
      (await ctx.db.get(
        await ctx.db.insert("languageExamples", {
          organizationId: auth.organizationId,
          language: feedback.language,
          normalizedKey: args.normalizedKey,
          status: "approved",
        }),
      ))!;
    const last = await ctx.db
      .query("languageExampleVersions")
      .withIndex("by_exampleId_and_version", (q) => q.eq("exampleId", head._id))
      .order("desc")
      .first();
    const version = (last?.version ?? 0) + 1;
    const versionId = await ctx.db.insert("languageExampleVersions", {
      exampleId: head._id,
      version,
      inputText: args.inputText,
      outputText: args.outputText,
      reviewerMemberId: auth.memberId,
      approvedAt: now,
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "linguistic.corpus.promote",
        resourceType: "languageExampleVersions",
        resourceId: versionId,
        after: { exampleId: head._id, version },
      },
      now,
    );
    return { exampleId: head._id, version };
  },
});
