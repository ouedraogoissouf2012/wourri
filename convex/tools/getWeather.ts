import { v } from "convex/values";
import { action } from "../_generated/server";
import { internal } from "../_generated/api";
import { CAPABILITIES } from "../authorization";
import { abstain, type ToolResult } from "./types";

// §22 — getWeather. Reads structured SODEXAM data only; never invents weather.
// Returns insufficient_evidence when no fresh observation covers the zone (§23).
export const getWeather = action({
  args: { zoneId: v.string() },
  handler: async (ctx, args): Promise<ToolResult<{
    zoneId: string;
    variables: unknown;
    validFrom: number;
    validUntil: number;
    confidence?: number;
    dataOrigin: string;
  }>> => {
    await ctx.runQuery(internal.authz.checkAccess.requireCapability, {
      permission: CAPABILITIES.knowledgeRead,
    });
    const now = Date.now();
    const found = await ctx.runQuery(internal.weather.queries.currentObservation, {
      zoneId: args.zoneId,
      now,
    });
    if (!found) {
      return abstain(`No fresh weather observation for zone '${args.zoneId}'`);
    }
    const { observation, provenance } = found;
    let variables: unknown = null;
    try {
      variables = JSON.parse(observation.variables);
    } catch {
      variables = observation.variables;
    }
    return {
      status: "ok",
      data: {
        zoneId: observation.zoneId,
        variables,
        validFrom: observation.validFrom,
        validUntil: observation.validUntil,
        confidence: observation.confidence,
        dataOrigin: observation.dataOrigin,
      },
      provenance: [
        {
          sourceVersionId: observation.sourceVersionId,
          sourceId: provenance?.source?._id,
          authority: provenance?.source?.authority,
          version: provenance?.version?.version,
          dataOrigin: observation.dataOrigin,
        },
      ],
    };
  },
});
