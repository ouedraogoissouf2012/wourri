/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as auth from "../auth.js";
import type * as http from "../http.js";
import type * as schema_alerts from "../schema/alerts.js";
import type * as schema_billing from "../schema/billing.js";
import type * as schema_conversations from "../schema/conversations.js";
import type * as schema_farmers from "../schema/farmers.js";
import type * as schema_knowledge from "../schema/knowledge.js";
import type * as schema_language from "../schema/language.js";
import type * as schema_tenancy from "../schema/tenancy.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  auth: typeof auth;
  http: typeof http;
  "schema/alerts": typeof schema_alerts;
  "schema/billing": typeof schema_billing;
  "schema/conversations": typeof schema_conversations;
  "schema/farmers": typeof schema_farmers;
  "schema/knowledge": typeof schema_knowledge;
  "schema/language": typeof schema_language;
  "schema/tenancy": typeof schema_tenancy;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {
  betterAuth: import("../betterAuth/_generated/component.js").ComponentApi<"betterAuth">;
};
