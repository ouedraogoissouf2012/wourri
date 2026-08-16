import { defineSchema } from "convex/server";
import { alertTables } from "./schema/alerts";
import { auditTables } from "./schema/audit";
import { billingTables } from "./schema/billing";
import { configTables } from "./schema/config";
import { conversationTables } from "./schema/conversations";
import { farmerTables } from "./schema/farmers";
import { jobTables } from "./schema/jobs";
import { knowledgeTables } from "./schema/knowledge";
import { languageTables } from "./schema/language";
import { observabilityTables } from "./schema/observability";
import { tenancyTables } from "./schema/tenancy";
import { weatherTables } from "./schema/weather";

export default defineSchema({
  ...alertTables,
  ...auditTables,
  ...billingTables,
  ...configTables,
  ...conversationTables,
  ...farmerTables,
  ...jobTables,
  ...knowledgeTables,
  ...languageTables,
  ...observabilityTables,
  ...tenancyTables,
  ...weatherTables,
});
