import { defineSchema } from "convex/server";
import { alertTables } from "./schema/alerts";
import { billingTables } from "./schema/billing";
import { conversationTables } from "./schema/conversations";
import { farmerTables } from "./schema/farmers";
import { knowledgeTables } from "./schema/knowledge";
import { languageTables } from "./schema/language";
import { tenancyTables } from "./schema/tenancy";

export default defineSchema({
  ...alertTables,
  ...billingTables,
  ...conversationTables,
  ...farmerTables,
  ...knowledgeTables,
  ...languageTables,
  ...tenancyTables,
});
