import { v } from "convex/values";
import { internalMutation } from "../_generated/server";

/**
 * Ingest Bronze depuis le moteur (👎 WhatsApp) — pas de session Better Auth.
 * Appelé uniquement via httpAction /lqe/bronze-task (clé callback).
 * Locuteur : listFeedback language=dyu status=needs_review.
 */
export const insertBronzeFromEngine = internalMutation({
  args: {
    organizationId: v.string(),
    language: v.string(),
    intent: v.optional(v.string()),
    source: v.optional(v.string()),
    excerpt: v.optional(v.string()),
    cultures: v.optional(v.array(v.string())),
  },
  handler: async (ctx, args) => {
    const now = Date.now();
    const language = args.language || "dyu";
    const id = await ctx.db.insert("linguisticFeedback", {
      organizationId: args.organizationId,
      language,
      culture: args.cultures?.[0],
      generatedOutput: args.excerpt,
      comment: [
        args.intent ? `intent=${args.intent}` : "",
        args.source ? `source=${args.source}` : "",
      ]
        .filter(Boolean)
        .join(" "),
      errorType: "field_downvote",
      reviewerMemberId: "engine:whatsapp",
      status: "needs_review",
      version: 1,
      createdAt: now,
      updatedAt: now,
    });
    return id;
  },
});
