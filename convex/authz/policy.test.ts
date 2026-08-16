import { describe, expect, it } from "vitest";
import { evaluateAuthorization } from "./policy";
import type { AuthorizationRequirement, AuthorizationSnapshot } from "./types";

const now = 1_800_000_000_000;
const requirement: AuthorizationRequirement = {
  permission: "alerts:send",
  scope: { type: "zone", key: "abidjan-nord" },
  entitlement: "alerts",
};

const snapshot = (): AuthorizationSnapshot => ({
  organizationStatus: "active",
  session: { userId: "user-a", organizationId: "org-a", expiresAt: now + 1 },
  member: { id: "member-a", userId: "user-a", organizationId: "org-a" },
  assignment: { organizationId: "org-a", memberId: "member-a", policyId: "policy-a", status: "active" },
  policy: { id: "policy-a", organizationId: "org-a", permissions: ["alerts:send"], scopeMode: "restricted" },
  grants: [{ type: "zone", key: "abidjan-nord" }],
  entitlements: [{ key: "alerts", enabled: true, validFrom: now - 1, validUntil: now + 1 }],
});

const allows = (value = snapshot(), input = requirement) =>
  evaluateAuthorization(value, input, "user-a", now);

describe("DAT-07 authorization denials", () => {
  it("denies a member without the required permission", () => {
    const value = snapshot();
    value.policy!.permissions = [];
    expect(allows(value)).toBeNull();
  });

  it("denies an absent Better Auth membership", () => {
    const value = snapshot();
    value.member = null;
    expect(allows(value)).toBeNull();
  });

  it("denies an absent Better Auth session", () => {
    const value = snapshot();
    value.session = null;
    expect(allows(value)).toBeNull();
  });

  it("denies a suspended organization", () => {
    const value = snapshot();
    value.organizationStatus = "suspended";
    expect(allows(value)).toBeNull();
  });

  it("denies a revoked WOURI role assignment", () => {
    const value = snapshot();
    value.assignment!.status = "revoked";
    expect(allows(value)).toBeNull();
  });

  it("denies a restrictive policy with no matching scope grant", () => {
    const value = snapshot();
    value.grants = [];
    expect(allows(value)).toBeNull();
  });

  it("denies an expired entitlement", () => {
    const value = snapshot();
    value.entitlements[0]!.validUntil = now;
    expect(allows(value)).toBeNull();
  });

  it("denies cross-organization session and resource access", () => {
    const value = snapshot();
    value.session!.organizationId = "org-b";
    expect(allows(value)).toBeNull();
  });

  it("fails closed for time-bounded query permissions", () => {
    expect(evaluateAuthorization(snapshot(), requirement, "user-a")).toBeNull();
  });
});
