import { convexTest } from "convex-test";
import { describe, expect, it } from "vitest";
import schema from "../schema";
import { loadResourceForOrganization } from "./authorize";

const modules = {
  "../_generated/api.js": () => import("../_generated/api.js"),
};

// Better Auth data lives in its local component store, not this app schema.
// Snapshot policy tests cover component responses; this test uses a real app row.
describe("tenant resource authorization", () => {
  it("rejects a real resource owned by another organization", async () => {
    const t = convexTest(schema, modules);
    const resourceId = await t.run((ctx) => ctx.db.insert("organizationProfiles", {
      organizationId: "org-b",
      kind: "cooperative",
      legalName: "Coopérative B",
      status: "active",
    }));

    await expect(t.query((ctx) =>
      loadResourceForOrganization(ctx, resourceId, "org-a"),
    )).rejects.toThrow("Unauthorized");
  });
});
