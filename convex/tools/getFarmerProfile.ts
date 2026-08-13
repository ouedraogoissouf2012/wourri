import { v } from "convex/values";
import { query } from "../_generated/server";
import { authorizeResource, CAPABILITIES } from "../authorization";
import {
  getFarmerProfileForFarmer,
  listZoneLinksForFarmer,
  listCropLinksForFarmer,
} from "../farmers/model";
import { type ToolResult } from "./types";

// §22 — getFarmerProfile. authorizeResource verifies the farmer belongs to the
// caller's organization, so a guessed id from another org fails closed. Never
// exposes an arbitrary farmer.
export const getFarmerProfile = query({
  args: { farmerId: v.id("farmers") },
  handler: async (ctx, args): Promise<ToolResult<{
    farmerId: string;
    status: string;
    preferredLanguage?: string;
    countryCode?: string;
    notificationOptIn?: boolean;
    zoneIds: string[];
    cropCodes: string[];
  }>> => {
    const { resource: farmer } = await authorizeResource(ctx, args.farmerId, {
      permission: CAPABILITIES.farmersRead,
    });
    const profile = await getFarmerProfileForFarmer(ctx, args.farmerId);
    const zones = await listZoneLinksForFarmer(ctx, args.farmerId);
    const crops = await listCropLinksForFarmer(ctx, args.farmerId);
    return {
      status: "ok",
      data: {
        farmerId: farmer._id,
        status: farmer.status,
        preferredLanguage: profile?.preferredLanguage,
        countryCode: profile?.countryCode,
        notificationOptIn: profile?.notificationOptIn,
        zoneIds: zones.map((z) => z.zoneId),
        cropCodes: crops.map((c) => c.cropCode),
      },
      provenance: [],
    };
  },
});
