import { query } from "../_generated/server";
import { authorize, CAPABILITIES } from "../authorization";

// G03 support — a member reads only their own organization's profile,
// entitlements and default zones. The organization is derived from the session.
export const getMyOrganization = query({
  args: {},
  handler: async (ctx) => {
    const auth = await authorize(ctx, {
      permission: CAPABILITIES.organizationRead,
    });
    const profile = await ctx.db
      .query("organizationProfiles")
      .withIndex("by_organizationId", (q) =>
        q.eq("organizationId", auth.organizationId),
      )
      .unique();
    const entitlements = await ctx.db
      .query("organizationEntitlements")
      .withIndex("by_organizationId_and_key", (q) =>
        q.eq("organizationId", auth.organizationId),
      )
      .take(100);
    const defaultZones = await ctx.db
      .query("organizationDefaultZones")
      .withIndex("by_organizationId_and_zoneId", (q) =>
        q.eq("organizationId", auth.organizationId),
      )
      .take(200);
    return {
      organizationId: auth.organizationId,
      profile,
      entitlements: entitlements.map((e) => ({
        key: e.key,
        enabled: e.enabled,
        limit: e.limit,
      })),
      defaultZones: defaultZones.map((z) => z.zoneId),
    };
  },
});
