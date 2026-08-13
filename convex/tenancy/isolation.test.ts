import { convexTest } from "convex-test";
import { describe, expect, it } from "vitest";
import schema from "../schema";
import {
  createFarmerForOrg,
  getFarmerForOrg,
  countActiveFarmersBounded,
  addZoneLink,
} from "../farmers/model";
import { resolveAudience } from "../alerts/model";
import {
  createSource,
  createSourceVersion,
  sourceVersionVisibleToOrg,
} from "../knowledge/model";

const modules = {
  "../_generated/api.js": () => import("../_generated/api.js"),
};

// DAT-07 / G03 / G06 — cross-organization isolation at the data layer. The
// authorize() layer derives the org from the session; these tests prove the
// scoped data access never leaks across organizations even with a known id.
describe("cross-organization isolation", () => {
  it("a farmer is invisible to another organization", async () => {
    const t = convexTest(schema, modules);
    const farmerB = await t.run((ctx) => createFarmerForOrg(ctx, "org-b", "b1", 1));
    expect(await t.run((ctx) => getFarmerForOrg(ctx, "org-a", farmerB))).toBeNull();
    await t.run((ctx) => createFarmerForOrg(ctx, "org-a", "a1", 1));
    expect(await t.run((ctx) => countActiveFarmersBounded(ctx, "org-a", 10))).toBe(1);
  });

  it("audience targeting stays within the organization", async () => {
    const t = convexTest(schema, modules);
    const { a1, b1 } = await t.run(async (ctx) => {
      const a1 = await createFarmerForOrg(ctx, "org-a", "a1", 1);
      const b1 = await createFarmerForOrg(ctx, "org-b", "b1", 1);
      await addZoneLink(ctx, "org-a", a1, "abidjan-nord");
      await addZoneLink(ctx, "org-b", b1, "abidjan-nord");
      return { a1, b1 };
    });
    const audience = await t.run((ctx) =>
      resolveAudience(ctx, "org-a", [{ kind: "zone", targetKey: "abidjan-nord" }]),
    );
    expect(audience).toEqual([a1]);
    expect(audience).not.toContain(b1);
  });

  it("a source version from another org is not visible; a global one is", async () => {
    const t = convexTest(schema, modules);
    const { orgBVersion, globalVersion } = await t.run(async (ctx) => {
      const orgBSource = await createSource(ctx, {
        organizationId: "org-b",
        visibility: "organization",
        authority: "CNRA",
        license: "restricted",
        canonicalLocator: "loc-b",
      });
      const orgBVersion = await createSourceVersion(ctx, {
        sourceId: orgBSource,
        version: "1",
        contentHash: "h",
        acquiredAt: 1,
        acquisitionMethod: "seed",
      });
      const globalSource = await createSource(ctx, {
        visibility: "global",
        authority: "SODEXAM",
        license: "open",
        canonicalLocator: "loc-g",
      });
      const globalVersion = await createSourceVersion(ctx, {
        sourceId: globalSource,
        version: "1",
        contentHash: "h",
        acquiredAt: 1,
        acquisitionMethod: "seed",
      });
      return { orgBVersion, globalVersion };
    });
    expect(
      await t.run((ctx) =>
        sourceVersionVisibleToOrg(ctx, orgBVersion, "org-a"),
      ),
    ).toBeNull();
    expect(
      await t.run((ctx) =>
        sourceVersionVisibleToOrg(ctx, globalVersion, "org-a"),
      ),
    ).not.toBeNull();
  });
});
