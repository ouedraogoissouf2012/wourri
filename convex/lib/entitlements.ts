import type { MutationCtx, QueryCtx } from "../_generated/server";
import { ERROR_TYPES, WouriError } from "./errors";

// DAT-03 / §13 — organization entitlement enforcement. An entitlement is a
// named capability of a plan (whatsappEnabled, maxFarmers, ...) with an optional
// numeric limit. These helpers make a plan actually enforceable in code.

export const getEntitlement = async (
  ctx: QueryCtx | MutationCtx,
  organizationId: string,
  key: string,
) =>
  ctx.db
    .query("organizationEntitlements")
    .withIndex("by_organizationId_and_key", (q) =>
      q.eq("organizationId", organizationId).eq("key", key),
    )
    .unique();

const isActive = (
  entitlement: { enabled: boolean; validFrom: number; validUntil?: number },
  now: number,
) =>
  entitlement.enabled &&
  entitlement.validFrom <= now &&
  (entitlement.validUntil === undefined || entitlement.validUntil > now);

// Throws fail-closed when the entitlement is missing, disabled or expired.
export const requireEntitlement = async (
  ctx: MutationCtx,
  organizationId: string,
  key: string,
  now: number,
) => {
  const entitlement = await getEntitlement(ctx, organizationId, key);
  if (!entitlement || !isActive(entitlement, now)) {
    throw new WouriError(
      ERROR_TYPES.PERMISSION,
      `Entitlement '${key}' is not active for this organization`,
    );
  }
  return entitlement;
};

// Enforces a numeric ceiling: adding `addend` must not push `currentCount`
// past the entitlement limit. No limit set = unlimited.
export const enforceEntitlementLimit = async (
  ctx: MutationCtx,
  organizationId: string,
  key: string,
  currentCount: number,
  now: number,
  addend = 1,
) => {
  const entitlement = await requireEntitlement(ctx, organizationId, key, now);
  if (entitlement.limit !== undefined && currentCount + addend > entitlement.limit) {
    throw new WouriError(
      ERROR_TYPES.PERMISSION,
      `Entitlement '${key}' limit of ${entitlement.limit} reached`,
    );
  }
  return entitlement;
};
