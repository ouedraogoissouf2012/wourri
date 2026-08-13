import { v } from "convex/values";
import { internalQuery } from "../_generated/server";
import * as model from "./model";
import { getProvenance } from "../knowledge/model";

// Internal — the observation valid at `now` for a zone, with provenance. Time is
// passed in by the caller (an action) so this query stays deterministic.
export const currentObservation = internalQuery({
  args: { zoneId: v.string(), now: v.number() },
  handler: async (ctx, args) => {
    const observation = await model.latestValidObservation(
      ctx,
      args.zoneId,
      args.now,
    );
    if (!observation) return null;
    const provenance = await getProvenance(ctx, observation.sourceVersionId);
    return { observation, provenance };
  },
});
