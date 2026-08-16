import { v } from "convex/values";
import { mutation, query } from "../_generated/server";
import { authorize, authorizeMutation, CAPABILITIES } from "../authorization";
import { recordAudit } from "../lib/audit";
import { resolveAuditActor } from "../lib/actor";
import { WouriError, ERROR_TYPES } from "../lib/errors";

// LNG-04 / §24 / G09 — linguistic feedback lifecycle. A correction is captured,
// reviewed and validated; validated corrections are promoted to the glossary or
// corpus (see promote.ts) and prior versions are always kept.


export const submitFeedback = mutation({
  args: {
    language: v.string(),
    culture: v.optional(v.string()),
    region: v.optional(v.string()),
    rawTranscript: v.optional(v.string()),
    validatedTranscript: v.optional(v.string()),
    rawTranslation: v.optional(v.string()),
    validatedTranslation: v.optional(v.string()),
    translationDirection: v.optional(
      v.union(v.literal("local_to_fr"), v.literal("fr_to_local")),
    ),
    generatedOutput: v.optional(v.string()),
    audioRating: v.optional(v.number()),
    naturalnessScore: v.optional(v.number()),
    agriculturalVocabularyScore: v.optional(v.number()),
    errorType: v.optional(v.string()),
    comment: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.linguisticValidate,
    });
    const now = Date.now();
    const id = await ctx.db.insert("linguisticFeedback", {
      organizationId: auth.organizationId,
      ...args,
      reviewerMemberId: auth.memberId,
      status: "needs_review",
      version: 1,
      createdAt: now,
      updatedAt: now,
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "linguistic.feedback.submit",
        resourceType: "linguisticFeedback",
        resourceId: id,
        after: { language: args.language, errorType: args.errorType },
      },
      now,
    );
    return id;
  },
});

export const setFeedbackStatus = mutation({
  args: {
    feedbackId: v.id("linguisticFeedback"),
    status: v.union(
      v.literal("draft"),
      v.literal("needs_review"),
      v.literal("validated"),
      v.literal("rejected"),
    ),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.linguisticValidate,
    });
    const feedback = await ctx.db.get(args.feedbackId);
    if (!feedback || feedback.organizationId !== auth.organizationId) {
      throw new WouriError(ERROR_TYPES.PERMISSION, "Feedback not accessible");
    }
    const now = Date.now();
    await ctx.db.patch(args.feedbackId, { status: args.status, updatedAt: now });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "linguistic.feedback.status",
        resourceType: "linguisticFeedback",
        resourceId: args.feedbackId,
        before: { status: feedback.status },
        after: { status: args.status },
      },
      now,
    );
  },
});

export const listFeedback = query({
  args: {
    status: v.optional(
      v.union(
        v.literal("draft"),
        v.literal("needs_review"),
        v.literal("validated"),
        v.literal("rejected"),
      ),
    ),
    limit: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    const auth = await authorize(ctx, {
      permission: CAPABILITIES.linguisticValidate,
    });
    const limit = Math.min(args.limit ?? 50, 200);
    return ctx.db
      .query("linguisticFeedback")
      .withIndex("by_organizationId_and_status", (q) =>
        args.status
          ? q.eq("organizationId", auth.organizationId).eq("status", args.status)
          : q.eq("organizationId", auth.organizationId),
      )
      .order("desc")
      .take(limit);
  },
});
