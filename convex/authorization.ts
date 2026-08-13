export { authorize, authorizeMutation, authorizeResource } from "./authz/authorize";
export type {
  AuthorizationContext,
  AuthorizationRequirement,
  AuthorizationScope,
} from "./authz/types";
export {
  CAPABILITIES,
  ALL_CAPABILITIES,
  ROLE_PRESETS,
} from "./authz/capabilities";
export type { Capability, RolePreset } from "./authz/capabilities";
