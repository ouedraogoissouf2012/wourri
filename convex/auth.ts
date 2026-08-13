import {
  createClient,
  type AuthFunctions,
  type GenericCtx,
} from "@convex-dev/better-auth";
import { convex } from "@convex-dev/better-auth/plugins";
import { betterAuth, type BetterAuthOptions } from "better-auth/minimal";
import { organization } from "better-auth/plugins";
import { components, internal } from "./_generated/api";
import type { DataModel } from "./_generated/dataModel";
import authConfig from "./auth.config";
import authSchema from "./betterAuth/schema";

const localOrigin = "http://localhost:3000";

const runtimeEnvironment = globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};

const configuredOrigin = () =>
  runtimeEnvironment.process?.env?.SITE_URL ?? localOrigin;

const authFunctions: AuthFunctions = internal.auth;

export const authComponent = createClient<DataModel, typeof authSchema>(
  components.betterAuth,
  {
    authFunctions,
    local: { schema: authSchema },
    triggers: {
      organization: {
        onCreate: async (ctx, organization) => {
          await ctx.db.insert("organizationProfiles", {
            organizationId: organization._id,
            legalName: organization.name,
            status: "provisioning",
          });
        },
      },
    },
  },
);

export const { onCreate, onUpdate, onDelete } = authComponent.triggersApi();

export const createAuthOptions = (ctx: GenericCtx<DataModel>) =>
  ({
    baseURL: configuredOrigin(),
    trustedOrigins: [configuredOrigin()],
    database: authComponent.adapter(ctx),
    emailAndPassword: {
      enabled: configuredOrigin() === localOrigin,
      minPasswordLength: 12,
      requireEmailVerification: false,
    },
    plugins: [
      organization({
        allowUserToCreateOrganization: false,
        creatorRole: "owner",
      }),
      convex({ authConfig }),
    ],
  }) satisfies BetterAuthOptions;

export const createAuth = (ctx: GenericCtx<DataModel>) =>
  betterAuth(createAuthOptions(ctx));
