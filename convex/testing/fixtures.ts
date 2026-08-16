// §38 — STAGING demo dataset definitions. Pure declarative data (no logic) used
// by convex/testing/seed.ts to build a reproducible restitution dataset. Every
// identifier is a STABLE string so the seed is idempotent and the demo script can
// reference the exact same organizations, members, farmers and sources on every
// run. NONE of this is live data: it must never reach production (see seed.ts).

export type OrgKind = "adc" | "sodexam" | "cnra" | "cooperative" | "ngo";

export type OrgFixture = {
  organizationId: string;
  kind: OrgKind;
  legalName: string;
};

// Stable organization identifiers ("demo-*"). provisionOrganization creates the
// profile + role policies from the capability presets attached to each kind.
export const ORGANIZATIONS: OrgFixture[] = [
  { organizationId: "demo-adc", kind: "adc", legalName: "DEMO ADC Platform" },
  { organizationId: "demo-sodexam", kind: "sodexam", legalName: "DEMO SODEXAM" },
  { organizationId: "demo-cnra", kind: "cnra", legalName: "DEMO CNRA" },
  { organizationId: "demo-coop-a", kind: "cooperative", legalName: "DEMO Cooperative A" },
  { organizationId: "demo-coop-b", kind: "cooperative", legalName: "DEMO Cooperative B" },
  { organizationId: "demo-ngo", kind: "ngo", legalName: "DEMO NGO Partner" },
];

// The organization whose role policies must gain an extra "linguist" policy
// (provisionOrganization does not create it from the cnra preset).
export const LINGUIST_ORGANIZATION_ID = "demo-cnra";

export type MemberFixture = {
  organizationId: string;
  memberId: string;
  rolePolicyKey: string;
};

// Stable member identifiers. rolePolicyKey = preset name = role policy key.
export const MEMBERS: MemberFixture[] = [
  { organizationId: "demo-adc", memberId: "demo-adc-admin", rolePolicyKey: "adcAdmin" },
  { organizationId: "demo-sodexam", memberId: "demo-sodexam-op", rolePolicyKey: "sodexamOperator" },
  { organizationId: "demo-cnra", memberId: "demo-cnra-op", rolePolicyKey: "cnraOperator" },
  { organizationId: "demo-cnra", memberId: "demo-linguist", rolePolicyKey: "linguist" },
  { organizationId: "demo-coop-a", memberId: "demo-coop-a-admin", rolePolicyKey: "clientAdmin" },
  { organizationId: "demo-coop-b", memberId: "demo-coop-b-admin", rolePolicyKey: "clientAdmin" },
  { organizationId: "demo-ngo", memberId: "demo-ngo-admin", rolePolicyKey: "clientAdmin" },
];

export type EntitlementFixture = {
  organizationId: string;
  key: string;
  enabled: boolean;
  limit?: number;
};

// Manual entitlements granted to the demo cooperatives.
export const ENTITLEMENTS: EntitlementFixture[] = [
  { organizationId: "demo-coop-a", key: "maxFarmers", enabled: true, limit: 500 },
  { organizationId: "demo-coop-a", key: "whatsappEnabled", enabled: true },
  { organizationId: "demo-coop-b", key: "maxFarmers", enabled: true, limit: 500 },
  { organizationId: "demo-coop-b", key: "whatsappEnabled", enabled: true },
];

export type FarmerFixture = {
  organizationId: string;
  externalIdentityHash: string;
  preferredLanguage: string;
};

// Demo farmers. externalIdentityHash is stable so re-runs never duplicate them.
export const FARMERS: FarmerFixture[] = [
  { organizationId: "demo-coop-a", externalIdentityHash: "demo-coop-a-A1", preferredLanguage: "dyu" },
  { organizationId: "demo-coop-a", externalIdentityHash: "demo-coop-a-A2", preferredLanguage: "bci" },
  { organizationId: "demo-coop-b", externalIdentityHash: "demo-coop-b-B1", preferredLanguage: "dyu" },
];

// Shared farmer attributes for the demo cohort.
export const FARMER_COUNTRY_CODE = "CI";
export const FARMER_ZONE_ID = "abidjan-nord";
export const FARMER_CROP_CODE = "cacao";
export const CONSENT_PURPOSE = "whatsapp_alerts";
export const CONSENT_POLICY_VERSION = "v1";
export const CONSENT_CAPTURE_SOURCE = "seed";

export type SourceFixture = {
  key: "sodexam" | "cnra";
  authority: string;
  canonicalLocator: string;
  license: string;
  version: string;
  acquisitionMethod: string;
  contentHash: string;
};

// Global provenance sources (visibility "global"), one per authority.
export const SOURCES: SourceFixture[] = [
  {
    key: "sodexam",
    authority: "SODEXAM",
    canonicalLocator: "demo://sodexam/bulletin",
    license: "DEMO-CC-BY",
    version: "demo-v1",
    acquisitionMethod: "seed",
    contentHash: "demo-sodexam-v1",
  },
  {
    key: "cnra",
    authority: "CNRA",
    canonicalLocator: "demo://cnra/agronomie",
    license: "DEMO-CC-BY",
    version: "demo-v1",
    acquisitionMethod: "seed",
    contentHash: "demo-cnra-v1",
  },
];

// SODEXAM weather fixture window offsets (relative to now) and payload.
export const WEATHER_ZONE_ID = "abidjan-nord";
export const WEATHER_VALID_FROM_OFFSET = -3600000; // now - 1h
export const WEATHER_VALID_UNTIL_OFFSET = 86400000; // now + 24h
export const WEATHER_CONFIDENCE = 0.8;
export const WEATHER_VARIABLES = JSON.stringify({ rainMm: 40, tempC: 27, wind: "modéré" });
