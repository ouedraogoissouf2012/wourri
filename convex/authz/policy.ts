import type {
  AuthorizationContext,
  AuthorizationRequirement,
  AuthorizationScope,
  AuthorizationSnapshot,
} from "./types";

const scopeMatches = (grant: AuthorizationScope, scope: AuthorizationScope) =>
  grant.type === scope.type && grant.key === scope.key;

const hasValidEntitlement = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
  now: number,
) => {
  if (!requirement.entitlement) return true;
  return snapshot.entitlements.some(
    (entitlement) =>
      entitlement.key === requirement.entitlement &&
      entitlement.enabled &&
      entitlement.validFrom <= now &&
      (entitlement.validUntil === undefined || entitlement.validUntil > now),
  );
};

const hasQuerySafeEntitlement = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
) => {
  if (!requirement.entitlement) return true;
  // A reactive query cannot safely reevaluate a time window as time passes.
  // Time-bounded entitlements are consequently mutation-only until materialized.
  return snapshot.entitlements.some((entitlement) =>
    entitlement.key === requirement.entitlement &&
    entitlement.enabled &&
    entitlement.validFrom === 0 &&
    entitlement.validUntil === undefined,
  );
};

const hasRequiredScope = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
  now?: number,
) => {
  if (snapshot.policy?.scopeMode === "organization") return true;
  return requirement.scope !== undefined && snapshot.grants.some((grant) => {
    if (!scopeMatches(grant, requirement.scope!)) return false;
    if (now === undefined) return grant.expiresAt === undefined;
    return grant.expiresAt === undefined || grant.expiresAt > now;
  });
};

const hasActiveRelationship = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
  subject: string,
  now?: number,
) => {
  const { session, member, assignment, policy } = snapshot;
  return (
    snapshot.organizationStatus === "active" &&
    session?.userId === subject &&
    (now === undefined || session.expiresAt > now) &&
    member?.userId === subject &&
    member.organizationId === session.organizationId &&
    assignment?.status === "active" &&
    assignment.memberId === member.id &&
    assignment.organizationId === session.organizationId &&
    policy?.id === assignment.policyId &&
    policy.organizationId === session.organizationId
  );
};

export const evaluateAuthorization = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
  subject: string,
  now?: number,
): AuthorizationContext | null => {
  if (!hasActiveRelationship(snapshot, requirement, subject, now)) return null;
  const { member, policy } = snapshot;
  if (!member || !policy) return null;
  if (!policy.permissions.includes(requirement.permission)) return null;
  if (!hasRequiredScope(snapshot, requirement, now)) return null;
  if (now === undefined && !hasQuerySafeEntitlement(snapshot, requirement)) return null;
  if (now !== undefined && !hasValidEntitlement(snapshot, requirement, now)) return null;

  return {
    organizationId: member.organizationId,
    memberId: member.id,
    rolePolicyId: policy.id,
    permissions: policy.permissions,
  };
};
