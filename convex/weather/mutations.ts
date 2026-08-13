import { v } from "convex/values";
import { mutation } from "../_generated/server";
import { authorizeMutation, CAPABILITIES } from "../authorization";
import { recordAudit } from "../lib/audit";
import { resolveAuditActor } from "../lib/actor";
import { WouriError, ERROR_TYPES } from "../lib/errors";
import * as knowledge from "../knowledge/model";
import * as model from "./model";

// KNO-02 — publish a SODEXAM observation. dataOrigin must be explicit so a
// staging fixture can never be recorded as live production data (§19).
export const publishWeatherObservation = mutation({
  args: {
    sourceVersionId: v.id("knowledgeSourceVersions"),
    zoneId: v.string(),
    validFrom: v.number(),
    validUntil: v.number(),
    variables: v.string(),
    confidence: v.optional(v.number()),
    dataOrigin: v.union(v.literal("live"), v.literal("staging_fixture")),
  },
  handler: async (ctx, args) => {
    const auth = await authorizeMutation(ctx, {
      permission: CAPABILITIES.weatherPublish,
    });
    const provenance = await knowledge.sourceVersionVisibleToOrg(
      ctx,
      args.sourceVersionId,
      auth.organizationId,
    );
    if (!provenance) {
      throw new WouriError(ERROR_TYPES.SOURCE, "Source version not accessible");
    }
    const now = Date.now();
    const observationId = await model.insertObservation(ctx, {
      sourceVersionId: args.sourceVersionId,
      zoneId: args.zoneId,
      issuedAt: now,
      validFrom: args.validFrom,
      validUntil: args.validUntil,
      variables: args.variables,
      confidence: args.confidence,
      dataOrigin: args.dataOrigin,
    });
    await recordAudit(
      ctx,
      {
        organizationId: auth.organizationId,
        ...(await resolveAuditActor(ctx, auth)),
        action: "weather.observation.publish",
        resourceType: "weatherObservations",
        resourceId: observationId,
        after: { zoneId: args.zoneId, dataOrigin: args.dataOrigin },
      },
      now,
    );
    return observationId;
  },
});
