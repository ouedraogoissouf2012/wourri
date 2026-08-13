import { ConvexError } from "convex/values";
import type { Doc, Id, TableNames } from "../_generated/dataModel";
import type { GenericMutationCtx, GenericQueryCtx } from "convex/server";
import { authComponent } from "../auth";
import { components } from "../_generated/api";
import type { DataModel } from "../_generated/dataModel";
import { evaluateAuthorization } from "./policy";
import type {
  AuthorizationContext,
  AuthorizationRequirement,
  AuthorizationSnapshot,
} from "./types";

type QueryAuthorizationCtx = GenericQueryCtx<DataModel>;
type MutationAuthorizationCtx = GenericMutationCtx<DataModel>;
type AuthorizationCtx = QueryAuthorizationCtx | MutationAuthorizationCtx;

const deny = (): never => {
  throw new ConvexError("Unauthorized");
};

const getIdentity = async (ctx: AuthorizationCtx) => {
  const identity = await ctx.auth.getUserIdentity();
  if (!identity) return deny();
  const sessionId = identity["sessionId"];
  if (!identity.subject || typeof sessionId !== "string") return deny();
  return { subject: identity.subject, sessionId };
};

const loadAuthRecords = async (
  ctx: AuthorizationCtx,
  subject: string,
  sessionId: string,
) => {
  const session = await ctx.runQuery(components.betterAuth.adapter.findOne, {
    model: "session",
    where: [
      { field: "_id", value: sessionId },
      { field: "userId", value: subject },
    ],
  });
  const organizationId = session?.activeOrganizationId;
  if (typeof organizationId !== "string") return { session: null, member: null };
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
  subject: string,
  sessionId: string,
): Promise<AuthorizationSnapshot> => {
  const { session, member } = await loadAuthRecords(ctx, subject, sessionId);
  const organizationId = session?.activeOrganizationId;
  const records = typeof organizationId === "string"
    ? await loadWouriRecords(ctx, organizationId, member?._id)
    : emptyWouriRecords();
  return toSnapshot(session, member, records);
};

const loadWouriRecords = async (
  ctx: AuthorizationCtx,
  organizationId: string,
  memberId: string | undefined,
) => {
  const profile = await ctx.db
    .query("organizationProfiles")
    .withIndex("by_organizationId", (q) => q.eq("organizationId", organizationId))
    .unique();
  const assignment = memberId
    ? await activeAssignmentForMember(ctx, organizationId, memberId)
    : null;
  const policy = assignment ? await ctx.db.get(assignment.rolePolicyId) : null;
  const grants = memberId ? await grantsForMember(ctx, organizationId, memberId) : [];
  const entitlements = await ctx.db
    .query("organizationEntitlements")
    .withIndex("by_organizationId_and_key", (q) => q.eq("organizationId", organizationId))
    .collect();
  return { profile, assignment, policy, grants, entitlements };
};

// Assignments are an append-only log, so revocation of an older role is written
// after a newer role is granted. Selecting across every status would let that
// later revocation shadow the active role and deny a legitimate member.
export const activeAssignmentForMember = async (
  ctx: AuthorizationCtx,
  organizationId: string,
  memberId: string,
) =>
  ctx.db
    .query("memberRoleAssignments")
    .withIndex("by_organizationId_and_memberId_and_status", (q) =>
      q
        .eq("organizationId", organizationId)
        .eq("memberId", memberId)
        .eq("status", "active"),
    )
    .order("desc")
    .first();

const grantsForMember = async (
  ctx: AuthorizationCtx,
  organizationId: string,
  memberId: string,
) => {
  return ctx.db
    .query("membershipScopeGrants")
    .withIndex("by_organizationId_and_memberId", (q) =>
      q.eq("organizationId", organizationId).eq("memberId", memberId),
    )
    .collect();
};

const emptyWouriRecords = () => ({
  profile: null,
  assignment: null,
  policy: null,
  grants: [],
  entitlements: [],
});

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
  grants: records.grants.map((grant) => ({
    type: grant.scopeType,
    key: grant.scopeKey,
    ...(grant.expiresAt === undefined ? {} : { expiresAt: grant.expiresAt }),
  })),
  entitlements: records.entitlements.map((entitlement) => ({ key: entitlement.key, enabled: entitlement.enabled, validFrom: entitlement.validFrom, ...(entitlement.validUntil === undefined ? {} : { validUntil: entitlement.validUntil }) })),
});

const loadAuthorizedSnapshot = async (ctx: AuthorizationCtx) => {
  const identity = await getIdentity(ctx);
  if (!(await authComponent.safeGetAuthUser(ctx))) deny();
  const snapshot = await loadSnapshot(ctx, identity.subject, identity.sessionId);
  return { identity, snapshot };
};

export const authorize = async (
  ctx: QueryAuthorizationCtx,
  requirement: AuthorizationRequirement,
): Promise<AuthorizationContext> => {
  const { identity, snapshot } = await loadAuthorizedSnapshot(ctx);
  return evaluateAuthorization(snapshot, requirement, identity.subject) ?? deny();
};

export const authorizeMutation = async (
  ctx: MutationAuthorizationCtx,
  requirement: AuthorizationRequirement,
): Promise<AuthorizationContext> => {
  const { identity, snapshot } = await loadAuthorizedSnapshot(ctx);
  return evaluateAuthorization(snapshot, requirement, identity.subject, Date.now()) ?? deny();
};

const hasOrganizationId = (resource: unknown): resource is { organizationId: string } =>
  typeof resource === "object" && resource !== null &&
  "organizationId" in resource && typeof resource.organizationId === "string";

export const loadResourceForOrganization = async <TableName extends TableNames>(
  ctx: QueryAuthorizationCtx,
  resourceId: Id<TableName>,
  organizationId: string,
): Promise<Doc<TableName>> => {
  const resource = await ctx.db.get(resourceId);
  const tenantResource = hasOrganizationId(resource) ? resource : deny();
  if (tenantResource.organizationId !== organizationId) deny();
  return tenantResource as Doc<TableName>;
};

export const authorizeResource = async <TableName extends TableNames>(
  ctx: QueryAuthorizationCtx,
  resourceId: Id<TableName>,
  requirement: AuthorizationRequirement,
): Promise<{ authorization: AuthorizationContext; resource: Doc<TableName> }> => {
  const authorization = await authorize(ctx, requirement);
  const resource = await loadResourceForOrganization(ctx, resourceId, authorization.organizationId);
  return { authorization, resource };
};
