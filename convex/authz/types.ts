export type AuthorizationScope = {
  type: "zone" | "crop" | "group";
  key: string;
  expiresAt?: number;
};

export type AuthorizationRequirement = {
  permission: string;
  scope?: AuthorizationScope;
  entitlement?: string;
};

export type AuthorizationSnapshot = {
  organizationStatus: "active" | "provisioning" | "suspended" | null;
  session: { userId: string; organizationId: string; expiresAt: number } | null;
  member: { id: string; userId: string; organizationId: string } | null;
  assignment: {
    organizationId: string;
    memberId: string;
    policyId: string;
    status: "active" | "revoked";
  } | null;
  policy: {
    id: string;
    organizationId: string;
    permissions: string[];
    scopeMode: "organization" | "restricted";
  } | null;
  grants: AuthorizationScope[];
  entitlements: Array<{
    key: string;
    enabled: boolean;
    validFrom: number;
    validUntil?: number;
  }>;
};

export type AuthorizationContext = {
  organizationId: string;
  memberId: string;
  rolePolicyId: string;
  permissions: string[];
};
