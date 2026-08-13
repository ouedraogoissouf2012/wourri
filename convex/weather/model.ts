import type { MutationCtx, QueryCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";

// KNO-02 / §19 — structured SODEXAM weather access. dataOrigin keeps staging
// fixtures distinguishable from live observations at every read.

export type WeatherOrigin = "live" | "staging_fixture";

export const insertObservation = async (
  ctx: MutationCtx,
  input: {
    sourceVersionId: Id<"knowledgeSourceVersions">;
    zoneId: string;
    issuedAt: number;
    validFrom: number;
    validUntil: number;
    variables: string;
    confidence?: number;
    dataOrigin: WeatherOrigin;
  },
): Promise<Id<"weatherObservations">> =>
  ctx.db.insert("weatherObservations", input);

// The observation whose validity window covers `now`, most recent first. Returns
// null when there is no fresh data — the caller must then abstain, never invent.
export const latestValidObservation = async (
  ctx: QueryCtx | MutationCtx,
  zoneId: string,
  now: number,
) => {
  const candidates = await ctx.db
    .query("weatherObservations")
    .withIndex("by_zoneId_and_validFrom", (q) =>
      q.eq("zoneId", zoneId).lte("validFrom", now),
    )
    .order("desc")
    .take(25);
  return candidates.find((observation) => observation.validUntil > now) ?? null;
};
