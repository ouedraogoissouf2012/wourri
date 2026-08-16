import { v } from "convex/values";
import { internalQuery } from "../_generated/server";

// Internal — resolves the Agent thread and organization for a conversation
// context, used by the answer pipeline (an action) to post messages.
export const contextThread = internalQuery({
  args: { contextId: v.id("conversationContexts") },
  handler: async (ctx, args) => {
    const context = await ctx.db.get(args.contextId);
    if (!context) return null;
    return {
      agentThreadId: context.agentThreadId,
      organizationId: context.organizationId,
      preferredLanguage: context.preferredLanguage,
    };
  },
});
