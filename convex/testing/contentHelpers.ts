import type { MutationCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import {
  addConsent,
  addCropLink,
  addZoneLink,
  createFarmerForOrg,
  getFarmerByExternalHash,
  upsertFarmerProfile,
} from "../farmers/model";
import { createSource, createSourceVersion } from "../knowledge/model";
import { insertObservation } from "../weather/model";
import {
  CONSENT_CAPTURE_SOURCE,
  CONSENT_POLICY_VERSION,
  CONSENT_PURPOSE,
  FARMER_COUNTRY_CODE,
  FARMER_CROP_CODE,
  FARMER_ZONE_ID,
  WEATHER_CONFIDENCE,
  WEATHER_VALID_FROM_OFFSET,
  WEATHER_VALID_UNTIL_OFFSET,
  WEATHER_VARIABLES,
} from "./fixtures";
import type { FarmerFixture, SourceFixture } from "./fixtures";

// §38 — content seed helpers (farmers, provenance sources, weather fixture). All
// STAGING; the weather observation is tagged dataOrigin "staging_fixture" so it
// can never be mistaken for a live SODEXAM reading.

export type SeededFarmer = { farmerId: Id<"farmers">; created: boolean };

// Seed one farmer end to end (profile, zone/crop links, WhatsApp consent). If the
// farmer already exists (same externalIdentityHash), skip untouched — the profile
// and links are only wired on first creation, keeping the seed idempotent.
export const seedFarmer = async (
  ctx: MutationCtx,
  fixture: FarmerFixture,
  now: number,
): Promise<SeededFarmer> => {
  const existing = await getFarmerByExternalHash(
    ctx,
    fixture.organizationId,
    fixture.externalIdentityHash,
  );
  if (existing) return { farmerId: existing._id, created: false };

  const farmerId = await createFarmerForOrg(
    ctx,
    fixture.organizationId,
    fixture.externalIdentityHash,
    now,
  );
  await upsertFarmerProfile(
    ctx,
    farmerId,
    {
      preferredLanguage: fixture.preferredLanguage,
      countryCode: FARMER_COUNTRY_CODE,
      notificationOptIn: true,
    },
    now,
  );
  await addZoneLink(ctx, fixture.organizationId, farmerId, FARMER_ZONE_ID);
  await addCropLink(ctx, fixture.organizationId, farmerId, FARMER_CROP_CODE);
  await addConsent(
    ctx,
    farmerId,
    CONSENT_PURPOSE,
    CONSENT_POLICY_VERSION,
    "granted",
    CONSENT_CAPTURE_SOURCE,
    now,
  );
  return { farmerId, created: true };
};

export type SeededSource = {
  sourceId: Id<"knowledgeSources">;
  sourceVersionId: Id<"knowledgeSourceVersions">;
};

// Ensure a global provenance source + version. Idempotent on canonicalLocator
// (and source+version). Returns both ids so callers can attach observations.
export const ensureGlobalSource = async (
  ctx: MutationCtx,
  fixture: SourceFixture,
  now: number,
): Promise<SeededSource> => {
  const existingSource = await ctx.db
    .query("knowledgeSources")
    .withIndex("by_canonicalLocator", (q) =>
      q.eq("canonicalLocator", fixture.canonicalLocator),
    )
    .unique();
  const sourceId =
    existingSource?._id ??
    (await createSource(ctx, {
      visibility: "global",
      authority: fixture.authority,
      license: fixture.license,
      canonicalLocator: fixture.canonicalLocator,
    }));

  const existingVersion = await ctx.db
    .query("knowledgeSourceVersions")
    .withIndex("by_sourceId_and_version", (q) =>
      q.eq("sourceId", sourceId).eq("version", fixture.version),
    )
    .unique();
  const sourceVersionId =
    existingVersion?._id ??
    (await createSourceVersion(ctx, {
      sourceId,
      version: fixture.version,
      contentHash: fixture.contentHash,
      acquiredAt: now,
      acquisitionMethod: fixture.acquisitionMethod,
    }));
  return { sourceId, sourceVersionId };
};

// Ensure the SODEXAM staging weather observation for a zone. Idempotent: reuses
// an existing staging fixture for the same (sourceVersion, zone).
export const ensureWeatherFixture = async (
  ctx: MutationCtx,
  sourceVersionId: Id<"knowledgeSourceVersions">,
  zoneId: string,
  now: number,
): Promise<Id<"weatherObservations">> => {
  const existing = await ctx.db
    .query("weatherObservations")
    .withIndex("by_sourceVersionId", (q) =>
      q.eq("sourceVersionId", sourceVersionId),
    )
    .collect();
  const match = existing.find(
    (o) => o.zoneId === zoneId && o.dataOrigin === "staging_fixture",
  );
  if (match) return match._id;
  return insertObservation(ctx, {
    sourceVersionId,
    zoneId,
    issuedAt: now,
    validFrom: now + WEATHER_VALID_FROM_OFFSET,
    validUntil: now + WEATHER_VALID_UNTIL_OFFSET,
    variables: WEATHER_VARIABLES,
    confidence: WEATHER_CONFIDENCE,
    dataOrigin: "staging_fixture",
  });
};
