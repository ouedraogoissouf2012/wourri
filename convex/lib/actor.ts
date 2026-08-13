import type { MutationCtx } from "../_generated/server";

// §31 — resolve the audit actor from the verified session identity. The subject
// falls back to the member id (never an empty or "unknown" actor) so every
// sensitive operation stays imputable in the audit log.
export const resolveAuditActor = async (
  ctx: MutationCtx,
  auth: { memberId: string },
): Promise<{ actorSubject: string; actorMemberId: string }> => {
  const identity = await ctx.auth.getUserIdentity();
  return {
    actorSubject: identity?.subject ?? auth.memberId,
    actorMemberId: auth.memberId,
  };
};
