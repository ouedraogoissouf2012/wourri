import { convexTest } from "convex-test";
import { describe, expect, it } from "vitest";
import schema from "../schema";
import { createFarmerForOrg, addZoneLink } from "../farmers/model";
import {
  createAlertForOrg,
  addAudienceRule,
  createDeliveriesForOrg,
  resolveAudience,
  setDeliveryStateByAlertAndFarmer,
} from "../alerts/model";
import { resolveAlertContext } from "../conversations/model";

const modules = {
  "../_generated/api.js": () => import("../_generated/api.js"),
};

// G05 / QA-03 — an alert reaches a targeted farmer, the delivery advances to
// "replied", and the conversation recovers the originating alert (its message,
// date and zone) without the farmer repeating it.
describe("alert to conversation flow", () => {
  it("targets, delivers, replies and recovers the alert context", async () => {
    const t = convexTest(schema, modules);
    const ids = await t.run(async (ctx) => {
      const now = 1000;
      const farmer = await createFarmerForOrg(ctx, "org-a", "a1", now);
      await addZoneLink(ctx, "org-a", farmer, "abidjan-nord");
      const alertId = await createAlertForOrg(
        ctx,
        "org-a",
        "member-a",
        { message: "Forte pluie prevue demain" },
        now,
      );
      await addAudienceRule(ctx, "org-a", alertId, {
        kind: "zone",
        targetKey: "abidjan-nord",
      });
      const audience = await resolveAudience(ctx, "org-a", [
        { kind: "zone", targetKey: "abidjan-nord" },
      ]);
      await createDeliveriesForOrg(ctx, "org-a", alertId, audience, now);
      const deliveryId = await setDeliveryStateByAlertAndFarmer(
        ctx,
        alertId,
        farmer,
        "replied",
      );
      const contextId = await ctx.db.insert("conversationContexts", {
        organizationId: "org-a",
        farmerId: farmer,
        agentThreadId: "thread-1",
        channel: "whatsapp",
        preferredLanguage: "dyu",
        originAlertId: alertId,
        status: "open",
        lastActivityAt: now,
        createdAt: now,
      });
      return { alertId, farmer, deliveryId, contextId, audienceSize: audience.length };
    });

    expect(ids.audienceSize).toBe(1);
    expect(ids.deliveryId).not.toBeNull();

    const recovered = await t.run((ctx) =>
      resolveAlertContext(ctx, "org-a", ids.contextId),
    );
    expect(recovered?.alert.message).toBe("Forte pluie prevue demain");
    expect(recovered?.zones).toContain("abidjan-nord");

    // Another organization cannot recover this conversation's context.
    expect(
      await t.run((ctx) => resolveAlertContext(ctx, "org-b", ids.contextId)),
    ).toBeNull();
  });
});
