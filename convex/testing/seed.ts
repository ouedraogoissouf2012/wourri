import { v } from "convex/values";
import { internalMutation } from "../_generated/server";
import { internal } from "../_generated/api";
import type { Id } from "../_generated/dataModel";
import {
  ENTITLEMENTS,
  FARMERS,
  LINGUIST_ORGANIZATION_ID,
  MEMBERS,
  ORGANIZATIONS,
  SOURCES,
  WEATHER_ZONE_ID,
} from "./fixtures";
import {
  ensureEntitlement,
  ensureLinguistPolicy,
  ensureMemberRole,
  guardNotProduction,
} from "./orgHelpers";
import {
  ensureGlobalSource,
  ensureWeatherFixture,
  seedFarmer,
} from "./contentHelpers";

// §38 — STAGING demo seed for the 17/08 restitution. Builds a fully DEMO,
// idempotent dataset (organizations, members/roles, entitlements, farmers,
// provenance sources, one SODEXAM weather fixture). It is INTERNAL and must NEVER
// run in production: guardNotProduction() aborts when WOURI_ENV === "production".
// Re-running it never duplicates data (every entity keys off a stable identifier).

export const seedStaging = internalMutation({
  // dryRun only runs the production guard + returns the plan without writing.
  args: { dryRun: v.optional(v.boolean()) },
  handler: async (ctx, args) => {
    guardNotProduction();
    const now = Date.now();

    if (args.dryRun === true) {
      return {
        dryRun: true as const,
        wouldSeed: {
          organizations: ORGANIZATIONS.map((o) => o.organizationId),
          members: MEMBERS.map((m) => m.memberId),
          farmers: FARMERS.map((f) => f.externalIdentityHash),
          sources: SOURCES.map((s) => s.key),
        },
      };
    }

    // 1. Provision every organization (idempotent; also creates role policies).
    for (const org of ORGANIZATIONS) {
      const profileId: Id<"organizationProfiles"> = await ctx.runMutation(
        internal.organizations.provisioning.provisionOrganization,
        {
          organizationId: org.organizationId,
          kind: org.kind,
          legalName: org.legalName,
          defaultZoneIds: [WEATHER_ZONE_ID],
        },
      );
      void profileId;
    }

    // 2. Extra "linguist" role policy (not created by any provisioning preset).
    await ensureLinguistPolicy(ctx, LINGUIST_ORGANIZATION_ID);

    // 3. Member role assignments (idempotent on active assignment).
    const members: { memberId: string; organizationId: string; rolePolicyKey: string }[] = [];
    for (const member of MEMBERS) {
      await ensureMemberRole(
        ctx,
        member.organizationId,
        member.memberId,
        member.rolePolicyKey,
      );
      members.push(member);
    }

    // 4. Manual entitlements for the demo cooperatives.
    for (const entitlement of ENTITLEMENTS) {
      await ensureEntitlement(ctx, entitlement);
    }

    // 5. Farmers (profile, zone/crop links, WhatsApp consent).
    const farmers: {
      externalIdentityHash: string;
      organizationId: string;
      farmerId: Id<"farmers">;
      created: boolean;
    }[] = [];
    for (const fixture of FARMERS) {
      const { farmerId, created } = await seedFarmer(ctx, fixture, now);
      farmers.push({
        externalIdentityHash: fixture.externalIdentityHash,
        organizationId: fixture.organizationId,
        farmerId,
        created,
      });
    }

    // 6. Global provenance sources + versions (SODEXAM, CNRA).
    const sources: {
      key: string;
      sourceId: Id<"knowledgeSources">;
      sourceVersionId: Id<"knowledgeSourceVersions">;
    }[] = [];
    for (const source of SOURCES) {
      const { sourceId, sourceVersionId } = await ensureGlobalSource(
        ctx,
        source,
        now,
      );
      sources.push({ key: source.key, sourceId, sourceVersionId });
    }

    // 7. SODEXAM weather fixture for abidjan-nord, tied to the SODEXAM version.
    const sodexam = sources.find((s) => s.key === "sodexam");
    if (!sodexam) throw new Error("SODEXAM source missing after seed");
    const weatherObservationId = await ensureWeatherFixture(
      ctx,
      sodexam.sourceVersionId,
      WEATHER_ZONE_ID,
      now,
    );

    return {
      dryRun: false as const,
      organizations: ORGANIZATIONS.map((o) => o.organizationId),
      members,
      entitlements: ENTITLEMENTS.map((e) => ({
        organizationId: e.organizationId,
        key: e.key,
      })),
      farmers,
      sources,
      weatherObservationId,
    };
  },
});
