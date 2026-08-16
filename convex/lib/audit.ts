import type { MutationCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";

// §31 — audit trail for sensitive operations. before/after must be non-sensitive
// serialized snapshots; secrets never belong in the audit log.
export type AuditEntry = {
  organizationId?: string;
  actorSubject: string;
  actorMemberId?: string;
  action: string;
  resourceType: string;
  resourceId?: string;
  before?: unknown;
  after?: unknown;
  traceId?: Id<"executionTraces">;
};

const serialize = (value: unknown) =>
  value === undefined ? undefined : JSON.stringify(value);

export const recordAudit = async (ctx: MutationCtx, entry: AuditEntry, now: number) => {
  await ctx.db.insert("auditLogs", {
    organizationId: entry.organizationId,
    actorSubject: entry.actorSubject,
    actorMemberId: entry.actorMemberId,
    action: entry.action,
    resourceType: entry.resourceType,
    resourceId: entry.resourceId,
    before: serialize(entry.before),
    after: serialize(entry.after),
    traceId: entry.traceId,
    createdAt: now,
  });
};
