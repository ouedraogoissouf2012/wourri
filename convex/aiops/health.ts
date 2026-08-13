import { query } from "../_generated/server";
import { authorize, CAPABILITIES } from "../authorization";

// DEV-01 / DEV-02 — read-only health/whoami endpoint for the WOURI MCP and CLI.
// It exposes liveness and the caller's effective capabilities without any raw
// database access, so a diagnostic agent stays within its permissions.
export const health = query({
  args: {},
  handler: async (ctx) => {
    const auth = await authorize(ctx, { permission: CAPABILITIES.aiopsRead });
    return {
      ok: true,
      organizationId: auth.organizationId,
      capabilities: auth.permissions,
    };
  },
});
