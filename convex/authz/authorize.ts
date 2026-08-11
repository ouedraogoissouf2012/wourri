import { ConvexError } from "convex/values";
import type { GenericMutationCtx, GenericQueryCtx } from "convex/server";
import { authComponent } from "../auth";
import { components } from "../_generated/api";
import type { DataModel } from "../_generated/dataModel";
import { evaluateAuthorization } from "./policy";
import type {
  AuthorizationContext,
  AuthorizationRequirement,
  AuthorizationScope,
  AuthorizationSnapshot,
} from "./types";

type AuthorizationCtx =
  | GenericQueryCtx<DataModel>
  | GenericMutationCtx<DataModel>;

const deny = (): never => {
  throw new ConvexError("Unauthorized");
};

const getIdentity = async (
  ctx: AuthorizationCtx,
): Promise<{ subject: string; sessionId: string }> => {
  const identity = await ctx.auth.getUserIdentity();
  if (!identity) return deny();
  const sessionId = identity["sessionId"];
  if (!identity.subject || typeof sessionId !== "string") return deny();
  return { subject: identity.subject, sessionId };
};

const loadAuthRecords = async (ctx: AuthorizationCtx, organizationId: string, subject: string, sessionId: string) => {
  const now = Date.now();
  const session = await ctx.runQuery(components.betterAuth.adapter.findOne, {
    model: "session",
    where: [
      { field: "_id", value: sessionId },
      { field: "userId", value: subject },
      { field: "activeOrganizationId", value: organizationId },
      { field: "expiresAt", operator: "gt", value: now },
    ],
  });
  const member = await ctx.runQuery(components.betterAuth.adapter.findOne, {
    model: "member",
    where: [
      { field: "organizationId", value: organizationId },
      { field: "userId", value: subject },
    ],
  });
  return { session, member };
};

const loadSnapshot = async (
  ctx: AuthorizationCtx,
  requirement: AuthorizationRequirement,
  subject: string,
  sessionId: string,
): Promise<AuthorizationSnapshot> => {
  const { session, member } = await loadAuthRecords(
    ctx,
    requirement.organizationId,
    subject,
    sessionId,
  );
  const records = await loadWouriRecords(ctx, requirement, member?._id);
  return toSnapshot(session, member, records);
};

const loadWouriRecords = async (
  ctx: AuthorizationCtx,
  requirement: AuthorizationRequirement,
  memberId: string | undefined,
) => {
  const profile = await ctx.db
    .query("organizationProfiles")
    .withIndex("by_organizationId", (q) => q.eq("organizationId", requirement.organizationId))
    .unique();
  const assignment = memberId
    ? await ctx.db
        .query("memberRoleAssignments")
        .withIndex("by_organizationId_and_memberId", (q) =>
          q.eq("organizationId", requirement.organizationId).eq("memberId", memberId),
        )
        .unique()
    : null;
  const policy = assignment ? await ctx.db.get(assignment.rolePolicyId) : null;
  const grants = memberId ? await activeGrants(ctx, requirement.organizationId, memberId) : [];
  const entitlements = requirement.entitlement
    ? await ctx.db
        .query("organizationEntitlements")
        .withIndex("by_organizationId_and_key", (q) =>
          q.eq("organizationId", requirement.organizationId).eq("key", requirement.entitlement!),
        )
        .collect()
    : [];
  return { profile, assignment, policy, grants, entitlements };
};

const activeGrants = async (ctx: AuthorizationCtx, organizationId: string, memberId: string) => {
  const now = Date.now();
  const grants = await ctx.db
    .query("membershipScopeGrants")
    .withIndex("by_organizationId_and_memberId", (q) =>
      q.eq("organizationId", organizationId).eq("memberId", memberId),
    )
    .collect();
  return grants.filter((grant) => grant.expiresAt === undefined || grant.expiresAt > now);
};

const toSnapshot = (
  session: Awaited<ReturnType<typeof loadAuthRecords>>["session"],
  member: Awaited<ReturnType<typeof loadAuthRecords>>["member"],
  records: Awaited<ReturnType<typeof loadWouriRecords>>,
): AuthorizationSnapshot => ({
  organizationStatus: records.profile?.status ?? null,
  session: session
    ? { userId: session.userId, organizationId: session.activeOrganizationId, expiresAt: session.expiresAt }
    : null,
  member: member ? { id: member._id, userId: member.userId, organizationId: member.organizationId } : null,
  assignment: records.assignment
    ? { organizationId: records.assignment.organizationId, memberId: records.assignment.memberId, policyId: records.assignment.rolePolicyId, status: records.assignment.status }
    : null,
  policy: records.policy
    ? { id: records.policy._id, organizationId: records.policy.organizationId, permissions: records.policy.permissions, scopeMode: records.policy.scopeMode }
    : null,
  grants: records.grants.map((grant) => ({ type: grant.scopeType, key: grant.scopeKey })),
  entitlements: records.entitlements.map((entitlement) => ({ key: entitlement.key, enabled: entitlement.enabled, validFrom: entitlement.validFrom, ...(entitlement.validUntil === undefined ? {} : { validUntil: entitlement.validUntil }) })),
});

export const authorize = async (
  ctx: AuthorizationCtx,
  requirement: AuthorizationRequirement,
): Promise<AuthorizationContext> => {
  const identity = await getIdentity(ctx);
  if (!(await authComponent.safeGetAuthUser(ctx))) deny();
  const snapshot = await loadSnapshot(ctx, requirement, identity.subject, identity.sessionId);
  return evaluateAuthorization(snapshot, requirement, identity.subject, Date.now()) ?? deny();
};
