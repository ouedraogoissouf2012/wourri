import { v } from "convex/values";
import { internalMutation } from "../_generated/server";
import * as model from "./model";

// ALT-04 / §17 — inbound reply entry point. Server-to-server (a WhatsApp webhook
// has no user session), so this is internal: it sets the delivery to "replied",
// opens or reuses the durable conversation seeded from the alert, and stores the
// farmer's message on the Agent thread.
export const recordFarmerReply = internalMutation({
  args: {
    organizationId: v.string(),
    farmerId: v.id("farmers"),
    channel: v.string(),
    preferredLanguage: v.string(),
    alertId: v.id("alerts"),
    text: v.string(),
  },
  handler: async (ctx, args) =>
    model.recordInboundReply(ctx, args, Date.now()),
});
