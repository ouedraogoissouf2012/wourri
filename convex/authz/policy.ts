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

const hasRequiredScope = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
) => {
  if (snapshot.policy?.scopeMode === "organization") return true;
  return requirement.scope !== undefined && snapshot.grants.some((grant) =>
    scopeMatches(grant, requirement.scope!),
  );
};

const hasActiveRelationship = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
  subject: string,
  now: number,
) => {
  const { session, member, assignment, policy } = snapshot;
  return (
    snapshot.organizationStatus === "active" &&
    session?.userId === subject &&
    session.organizationId === requirement.organizationId &&
    session.expiresAt > now &&
    member?.userId === subject &&
    member.organizationId === requirement.organizationId &&
    assignment?.status === "active" &&
    assignment.memberId === member.id &&
    assignment.organizationId === requirement.organizationId &&
    policy?.id === assignment.policyId &&
    policy.organizationId === requirement.organizationId
  );
};

export const evaluateAuthorization = (
  snapshot: AuthorizationSnapshot,
  requirement: AuthorizationRequirement,
  subject: string,
  now: number,
): AuthorizationContext | null => {
  if (!hasActiveRelationship(snapshot, requirement, subject, now)) return null;
  const { member, policy } = snapshot;
  if (!member || !policy) return null;
  if (!policy.permissions.includes(requirement.permission)) return null;
  if (!hasRequiredScope(snapshot, requirement)) return null;
  if (!hasValidEntitlement(snapshot, requirement, now)) return null;

  return {
    organizationId: requirement.organizationId,
    memberId: member.id,
    rolePolicyId: policy.id,
    permissions: policy.permissions,
  };
};
