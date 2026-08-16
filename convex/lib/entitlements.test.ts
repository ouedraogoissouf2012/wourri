import { convexTest } from "convex-test";
import { describe, expect, it } from "vitest";
import schema from "../schema";
import { enforceEntitlementLimit, requireEntitlement } from "./entitlements";

const modules = {
  "../_generated/api.js": () => import("../_generated/api.js"),
};

// DAT-03 / §13 — a plan limit is actually enforceable in code: the 501st farmer
// is refused, and a missing entitlement fails closed.
describe("entitlement enforcement", () => {
  it("refuses to exceed a numeric limit and fails closed when missing", async () => {
    const t = convexTest(schema, modules);
    await t.run((ctx) =>
      ctx.db.insert("organizationEntitlements", {
        organizationId: "org-a",
        key: "maxFarmers",
        enabled: true,
        limit: 2,
        validFrom: 0,
        source: "manual",
      }),
    );

    // Adding one more when already at the limit is refused.
    await expect(
      t.run((ctx) => enforceEntitlementLimit(ctx, "org-a", "maxFarmers", 2, 1000)),
    ).rejects.toThrow();

    // Below the limit is allowed.
    await expect(
      t.run((ctx) => enforceEntitlementLimit(ctx, "org-a", "maxFarmers", 1, 1000)),
    ).resolves.toBeTruthy();

    // An entitlement that does not exist is denied (fail closed).
    await expect(
      t.run((ctx) => requireEntitlement(ctx, "org-a", "whatsappEnabled", 1000)),
    ).rejects.toThrow();
  });

  it("treats an expired entitlement as inactive", async () => {
    const t = convexTest(schema, modules);
    await t.run((ctx) =>
      ctx.db.insert("organizationEntitlements", {
        organizationId: "org-a",
        key: "alerts",
        enabled: true,
        validFrom: 0,
        validUntil: 500,
        source: "subscription",
      }),
    );
    await expect(
      t.run((ctx) => requireEntitlement(ctx, "org-a", "alerts", 1000)),
    ).rejects.toThrow();
  });
});
