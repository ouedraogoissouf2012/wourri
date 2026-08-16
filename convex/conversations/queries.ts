import { listMessages } from "@convex-dev/agent";
import { paginationOptsValidator } from "convex/server";
import { v } from "convex/values";
import { query } from "../_generated/server";
import { components } from "../_generated/api";
import { authorizeResource, CAPABILITIES } from "../authorization";
import * as model from "./model";

// G05 — proves the conversation recovers its originating alert without the
// farmer repeating it. authorizeResource confirms the context belongs to the
// caller's organization.
export const getConversationContext = query({
  args: { contextId: v.id("conversationContexts") },
  handler: async (ctx, args) => {
    const { authorization } = await authorizeResource(ctx, args.contextId, {
      permission: CAPABILITIES.alertsRead,
    });
    return model.resolveAlertContext(
      ctx,
      authorization.organizationId,
      args.contextId,
    );
  },
});

export const listConversationMessages = query({
  args: {
    contextId: v.id("conversationContexts"),
    paginationOpts: paginationOptsValidator,
  },
  handler: async (ctx, args) => {
    const { resource: context } = await authorizeResource(ctx, args.contextId, {
      permission: CAPABILITIES.alertsRead,
    });
    return listMessages(ctx, components.agent, {
      threadId: context.agentThreadId,
      paginationOpts: args.paginationOpts,
    });
  },
});
