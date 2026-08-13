import { convexTest } from "convex-test";
import { describe, expect, it } from "vitest";
import schema from "../schema";
import { activeAssignmentForMember } from "./authorize";

const modules = {
  "../_generated/api.js": () => import("../_generated/api.js"),
};

const seedPolicy = (t: ReturnType<typeof convexTest>, key: string) =>
  t.run((ctx) => ctx.db.insert("organizationRolePolicies", {
    organizationId: "org-a",
    key,
    permissions: ["alerts:send"],
    scopeMode: "organization",
  }));

describe("member role assignment selection", () => {
  it("keeps the active role when an older role is revoked afterwards", async () => {
    const t = convexTest(schema, modules);
    const grantedPolicyId = await seedPolicy(t, "agronomist");
    const supersededPolicyId = await seedPolicy(t, "observer");

    const activeAssignmentId = await t.run(async (ctx) => {
      const superseded = await ctx.db.insert("memberRoleAssignments", {
        organizationId: "org-a",
        memberId: "member-a",
        rolePolicyId: supersededPolicyId,
        status: "active",
        assignedAt: 100,
      });
      const granted = await ctx.db.insert("memberRoleAssignments", {
        organizationId: "org-a",
        memberId: "member-a",
        rolePolicyId: grantedPolicyId,
        status: "active",
        assignedAt: 200,
      });
      // Revoked last, with the highest timestamp of the three rows.
      await ctx.db.patch(superseded, { status: "revoked", revokedAt: 300 });
      return granted;
    });

    const assignment = await t.query((ctx) =>
      activeAssignmentForMember(ctx, "org-a", "member-a"),
    );

    expect(assignment?._id).toBe(activeAssignmentId);
    expect(assignment?.rolePolicyId).toBe(grantedPolicyId);
  });

  it("returns nothing once every role is revoked", async () => {
    const t = convexTest(schema, modules);
    const rolePolicyId = await seedPolicy(t, "agronomist");

    await t.run(async (ctx) => {
      const assignment = await ctx.db.insert("memberRoleAssignments", {
        organizationId: "org-a",
        memberId: "member-a",
        rolePolicyId,
        status: "active",
        assignedAt: 100,
      });
      await ctx.db.patch(assignment, { status: "revoked", revokedAt: 150 });
    });

    const assignment = await t.query((ctx) =>
      activeAssignmentForMember(ctx, "org-a", "member-a"),
    );

    expect(assignment).toBeNull();
  });

  it("ignores an active role held in another organization", async () => {
    const t = convexTest(schema, modules);
    const rolePolicyId = await seedPolicy(t, "agronomist");

    await t.run((ctx) => ctx.db.insert("memberRoleAssignments", {
      organizationId: "org-b",
      memberId: "member-a",
      rolePolicyId,
      status: "active",
      assignedAt: 100,
    }));

    const assignment = await t.query((ctx) =>
      activeAssignmentForMember(ctx, "org-a", "member-a"),
    );

    expect(assignment).toBeNull();
  });
});
