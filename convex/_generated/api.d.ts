/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as aiops_auditread from "../aiops/auditread.js";
import type * as aiops_flags from "../aiops/flags.js";
import type * as aiops_health from "../aiops/health.js";
import type * as aiops_registry from "../aiops/registry.js";
import type * as aiops_replay from "../aiops/replay.js";
import type * as aiops_shared from "../aiops/shared.js";
import type * as aiops_traces from "../aiops/traces.js";
import type * as alerts_audience from "../alerts/audience.js";
import type * as alerts_model from "../alerts/model.js";
import type * as alerts_mutations from "../alerts/mutations.js";
import type * as alerts_queries from "../alerts/queries.js";
import type * as auth from "../auth.js";
import type * as authorization from "../authorization.js";
import type * as authz_authorize from "../authz/authorize.js";
import type * as authz_capabilities from "../authz/capabilities.js";
import type * as authz_checkAccess from "../authz/checkAccess.js";
import type * as authz_policy from "../authz/policy.js";
import type * as authz_types from "../authz/types.js";
import type * as conversations_internal from "../conversations/internal.js";
import type * as conversations_model from "../conversations/model.js";
import type * as conversations_mutations from "../conversations/mutations.js";
import type * as conversations_queries from "../conversations/queries.js";
import type * as farmers_model from "../farmers/model.js";
import type * as farmers_mutations from "../farmers/mutations.js";
import type * as farmers_queries from "../farmers/queries.js";
import type * as http from "../http.js";
import type * as knowledge_ingest from "../knowledge/ingest.js";
import type * as knowledge_model from "../knowledge/model.js";
import type * as knowledge_mutations from "../knowledge/mutations.js";
import type * as knowledge_queries from "../knowledge/queries.js";
import type * as language_feedback from "../language/feedback.js";
import type * as language_promote from "../language/promote.js";
import type * as lib_actor from "../lib/actor.js";
import type * as lib_audit from "../lib/audit.js";
import type * as lib_entitlements from "../lib/entitlements.js";
import type * as lib_errors from "../lib/errors.js";
import type * as lib_trace from "../lib/trace.js";
import type * as lib_traceWrite from "../lib/traceWrite.js";
import type * as organizations_provisioning from "../organizations/provisioning.js";
import type * as organizations_queries from "../organizations/queries.js";
import type * as pipeline_answer from "../pipeline/answer.js";
import type * as rag_embeddingModel from "../rag/embeddingModel.js";
import type * as rag_index from "../rag/index.js";
import type * as schema_alerts from "../schema/alerts.js";
import type * as schema_audit from "../schema/audit.js";
import type * as schema_billing from "../schema/billing.js";
import type * as schema_config from "../schema/config.js";
import type * as schema_conversations from "../schema/conversations.js";
import type * as schema_farmers from "../schema/farmers.js";
import type * as schema_jobs from "../schema/jobs.js";
import type * as schema_knowledge from "../schema/knowledge.js";
import type * as schema_language from "../schema/language.js";
import type * as schema_observability from "../schema/observability.js";
import type * as schema_tenancy from "../schema/tenancy.js";
import type * as schema_weather from "../schema/weather.js";
import type * as testing_contentHelpers from "../testing/contentHelpers.js";
import type * as testing_fixtures from "../testing/fixtures.js";
import type * as testing_orgHelpers from "../testing/orgHelpers.js";
import type * as testing_seed from "../testing/seed.js";
import type * as tools_getFarmerProfile from "../tools/getFarmerProfile.js";
import type * as tools_getWeather from "../tools/getWeather.js";
import type * as tools_searchKnowledge from "../tools/searchKnowledge.js";
import type * as tools_types from "../tools/types.js";
import type * as weather_model from "../weather/model.js";
import type * as weather_mutations from "../weather/mutations.js";
import type * as weather_queries from "../weather/queries.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  "aiops/auditread": typeof aiops_auditread;
  "aiops/flags": typeof aiops_flags;
  "aiops/health": typeof aiops_health;
  "aiops/registry": typeof aiops_registry;
  "aiops/replay": typeof aiops_replay;
  "aiops/shared": typeof aiops_shared;
  "aiops/traces": typeof aiops_traces;
  "alerts/audience": typeof alerts_audience;
  "alerts/model": typeof alerts_model;
  "alerts/mutations": typeof alerts_mutations;
  "alerts/queries": typeof alerts_queries;
  auth: typeof auth;
  authorization: typeof authorization;
  "authz/authorize": typeof authz_authorize;
  "authz/capabilities": typeof authz_capabilities;
  "authz/checkAccess": typeof authz_checkAccess;
  "authz/policy": typeof authz_policy;
  "authz/types": typeof authz_types;
  "conversations/internal": typeof conversations_internal;
  "conversations/model": typeof conversations_model;
  "conversations/mutations": typeof conversations_mutations;
  "conversations/queries": typeof conversations_queries;
  "farmers/model": typeof farmers_model;
  "farmers/mutations": typeof farmers_mutations;
  "farmers/queries": typeof farmers_queries;
  http: typeof http;
  "knowledge/ingest": typeof knowledge_ingest;
  "knowledge/model": typeof knowledge_model;
  "knowledge/mutations": typeof knowledge_mutations;
  "knowledge/queries": typeof knowledge_queries;
  "language/feedback": typeof language_feedback;
  "language/promote": typeof language_promote;
  "lib/actor": typeof lib_actor;
  "lib/audit": typeof lib_audit;
  "lib/entitlements": typeof lib_entitlements;
  "lib/errors": typeof lib_errors;
  "lib/trace": typeof lib_trace;
  "lib/traceWrite": typeof lib_traceWrite;
  "organizations/provisioning": typeof organizations_provisioning;
  "organizations/queries": typeof organizations_queries;
  "pipeline/answer": typeof pipeline_answer;
  "rag/embeddingModel": typeof rag_embeddingModel;
  "rag/index": typeof rag_index;
  "schema/alerts": typeof schema_alerts;
  "schema/audit": typeof schema_audit;
  "schema/billing": typeof schema_billing;
  "schema/config": typeof schema_config;
  "schema/conversations": typeof schema_conversations;
  "schema/farmers": typeof schema_farmers;
  "schema/jobs": typeof schema_jobs;
  "schema/knowledge": typeof schema_knowledge;
  "schema/language": typeof schema_language;
  "schema/observability": typeof schema_observability;
  "schema/tenancy": typeof schema_tenancy;
  "schema/weather": typeof schema_weather;
  "testing/contentHelpers": typeof testing_contentHelpers;
  "testing/fixtures": typeof testing_fixtures;
  "testing/orgHelpers": typeof testing_orgHelpers;
  "testing/seed": typeof testing_seed;
  "tools/getFarmerProfile": typeof tools_getFarmerProfile;
  "tools/getWeather": typeof tools_getWeather;
  "tools/searchKnowledge": typeof tools_searchKnowledge;
  "tools/types": typeof tools_types;
  "weather/model": typeof weather_model;
  "weather/mutations": typeof weather_mutations;
  "weather/queries": typeof weather_queries;
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
  agent: import("@convex-dev/agent/_generated/component.js").ComponentApi<"agent">;
  rag: import("@convex-dev/rag/_generated/component.js").ComponentApi<"rag">;
};
