import type { MutationCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";
import type { AuthorizationContext } from "../authorization";
import { recordAudit } from "../lib/audit";

// Shared AIOPS/CONFIG helpers. Kept tiny so every domain module stays focused.

const MAX_LIMIT = 200;
const DEFAULT_LIMIT = 50;

// Bounds every listing so a table that grows cannot produce an unbounded read.
export const clampLimit = (limit: number | undefined): number =>
  Math.min(Math.max(Math.trunc(limit ?? DEFAULT_LIMIT), 1), MAX_LIMIT);

type AiopsAuditEntry = {
  action: string;
  resourceType: string;
  resourceId?: string;
  before?: unknown;
  after?: unknown;
  traceId?: Id<"executionTraces">;
};

// Records a platform audit entry, deriving the actor subject server-side. The
// caller supplies the already-authorized context; we never trust a client id.
export const auditAiops = async (
  ctx: MutationCtx,
  auth: AuthorizationContext,
  now: number,
  entry: AiopsAuditEntry,
): Promise<void> => {
  const identity = await ctx.auth.getUserIdentity();
  await recordAudit(
    ctx,
    {
      organizationId: auth.organizationId,
      actorSubject: identity?.subject ?? auth.memberId,
      actorMemberId: auth.memberId,
      action: entry.action,
      resourceType: entry.resourceType,
      resourceId: entry.resourceId,
      before: entry.before,
      after: entry.after,
      traceId: entry.traceId,
    },
    now,
  );
};
