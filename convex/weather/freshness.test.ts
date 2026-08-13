import { convexTest } from "convex-test";
import { describe, expect, it } from "vitest";
import schema from "../schema";
import { insertObservation, latestValidObservation } from "./model";

const modules = {
  "../_generated/api.js": () => import("../_generated/api.js"),
};

// §23 / G07 — getWeather abstains when no fresh data covers the zone. This tests
// its basis: latestValidObservation returns null once the validity window closes.
describe("weather freshness", () => {
  it("returns the observation inside its window and nothing after it", async () => {
    const t = convexTest(schema, modules);
    const sourceVersionId = await t.run(async (ctx) => {
      const sourceId = await ctx.db.insert("knowledgeSources", {
        visibility: "global",
        authority: "SODEXAM",
        license: "open",
        canonicalLocator: "loc",
        status: "active",
      });
      return ctx.db.insert("knowledgeSourceVersions", {
        sourceId,
        version: "1",
        contentHash: "h",
        acquiredAt: 1,
        acquisitionMethod: "seed",
      });
    });
    await t.run((ctx) =>
      insertObservation(ctx, {
        sourceVersionId,
        zoneId: "abidjan-nord",
        issuedAt: 100,
        validFrom: 100,
        validUntil: 200,
        variables: "{}",
        dataOrigin: "staging_fixture",
      }),
    );

    expect(
      await t.run((ctx) => latestValidObservation(ctx, "abidjan-nord", 150)),
    ).not.toBeNull();
    expect(
      await t.run((ctx) => latestValidObservation(ctx, "abidjan-nord", 300)),
    ).toBeNull();
  });
});
