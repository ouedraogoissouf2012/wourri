// §11 / DAT-06 — canonical capability catalog. Role policies
// (organizationRolePolicies.permissions) hold these strings; every sensitive
// function references CAPABILITIES.* instead of a magic string so the permission
// matrix has a single source of truth.

export const CAPABILITIES = {
  platformManage: "platform.manage",
  organizationRead: "organization.read",
  organizationManage: "organization.manage",
  organizationMembersManage: "organization.members.manage",
  entitlementsManage: "entitlements.manage",
  farmersRead: "farmers.read",
  farmersWrite: "farmers.write",
  consentsWrite: "consents.write",
  alertsCreate: "alerts.create",
  alertsPublish: "alerts.publish",
  alertsRead: "alerts.read",
  weatherPublish: "weather.publish",
  sourcesPublish: "sources.publish",
  knowledgeIngest: "knowledge.ingest",
  knowledgePublish: "knowledge.publish",
  knowledgeRead: "knowledge.read",
  analyticsRead: "analytics.read",
  linguisticValidate: "linguistic.validate",
  aiopsRead: "aiops.read",
  aiopsReplay: "aiops.replay",
  featureFlagsManage: "featureflags.manage",
  auditRead: "audit.read",
} as const;

export type Capability = (typeof CAPABILITIES)[keyof typeof CAPABILITIES];

export const ALL_CAPABILITIES: Capability[] = Object.values(CAPABILITIES);

// Role presets used when provisioning an organization's role policies. Kept in
// code so the seed, the permission matrix doc, and the tests never drift.
export const ROLE_PRESETS = {
  // ADC platform operator — full platform administration.
  adcAdmin: ALL_CAPABILITIES,
  // SODEXAM — weather data provider and alert publisher.
  sodexamOperator: [
    CAPABILITIES.organizationRead,
    CAPABILITIES.weatherPublish,
    CAPABILITIES.sourcesPublish,
    CAPABILITIES.alertsCreate,
    CAPABILITIES.alertsPublish,
    CAPABILITIES.alertsRead,
    CAPABILITIES.knowledgeRead,
    CAPABILITIES.analyticsRead,
  ],
  // CNRA — agronomic knowledge provider.
  cnraOperator: [
    CAPABILITIES.organizationRead,
    CAPABILITIES.knowledgeIngest,
    CAPABILITIES.knowledgePublish,
    CAPABILITIES.sourcesPublish,
    CAPABILITIES.knowledgeRead,
    CAPABILITIES.alertsCreate,
    CAPABILITIES.alertsRead,
    CAPABILITIES.analyticsRead,
  ],
  // Cooperative / NGO client organization — manages its own farmers.
  clientAdmin: [
    CAPABILITIES.organizationRead,
    CAPABILITIES.organizationManage,
    CAPABILITIES.organizationMembersManage,
    CAPABILITIES.farmersRead,
    CAPABILITIES.farmersWrite,
    CAPABILITIES.consentsWrite,
    CAPABILITIES.alertsCreate,
    CAPABILITIES.alertsPublish,
    CAPABILITIES.alertsRead,
    CAPABILITIES.knowledgeRead,
    CAPABILITIES.analyticsRead,
  ],
  clientOperator: [
    CAPABILITIES.organizationRead,
    CAPABILITIES.farmersRead,
    CAPABILITIES.farmersWrite,
    CAPABILITIES.alertsRead,
    CAPABILITIES.knowledgeRead,
    CAPABILITIES.analyticsRead,
  ],
  // Linguistic validator — scoped to the validation console.
  linguist: [
    CAPABILITIES.organizationRead,
    CAPABILITIES.linguisticValidate,
    CAPABILITIES.knowledgeRead,
  ],
} satisfies Record<string, Capability[]>;

export type RolePreset = keyof typeof ROLE_PRESETS;
