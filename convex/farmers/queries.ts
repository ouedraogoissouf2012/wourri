import { v } from "convex/values";
import { paginationOptsValidator } from "convex/server";
import { query } from "../_generated/server";
import { authorize, authorizeResource, CAPABILITIES } from "../authorization";
import * as model from "./model";

// DAT-04 / §15 — public read surface for the FARMERS domain. authorize()/
// authorizeResource() derive the org from the session; model helpers are always
// called with the authorized org so a tenant can never read another's farmers.

export const listFarmers = query({
  args: { paginationOpts: paginationOptsValidator },
  handler: async (ctx, args) => {
    const auth = await authorize(ctx, { permission: CAPABILITIES.farmersRead });
    return model.listFarmersForOrg(ctx, auth.organizationId, args.paginationOpts);
  },
});

export const getFarmer = query({
  args: { farmerId: v.id("farmers") },
  handler: async (ctx, args) => {
    const { resource } = await authorizeResource(ctx, args.farmerId, {
      permission: CAPABILITIES.farmersRead,
    });
    return resource;
  },
});

// Full farmer view: profile (language/country/opt-in), zone & crop links and
// recent consent history for the consent center.
export const getFarmerProfile = query({
  args: { farmerId: v.id("farmers") },
  handler: async (ctx, args) => {
    const { resource } = await authorizeResource(ctx, args.farmerId, {
      permission: CAPABILITIES.farmersRead,
    });
    const [profile, zoneLinks, cropLinks, consents] = await Promise.all([
      model.getFarmerProfileForFarmer(ctx, resource._id),
      model.listZoneLinksForFarmer(ctx, resource._id),
      model.listCropLinksForFarmer(ctx, resource._id),
      model.listConsentsForFarmer(ctx, resource._id),
    ]);
    return {
      farmer: resource,
      profile,
      zoneIds: zoneLinks.map((link) => link.zoneId),
      cropCodes: cropLinks.map((link) => link.cropCode),
      consents,
    };
  },
});

export const listFarmerGroups = query({
  args: {},
  handler: async (ctx) => {
    const auth = await authorize(ctx, { permission: CAPABILITIES.farmersRead });
    return model.listGroupsForOrg(ctx, auth.organizationId);
  },
});
