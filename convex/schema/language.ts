import { defineTable } from "convex/server";
import { v } from "convex/values";

const lifecycle = v.union(v.literal("draft"), v.literal("approved"), v.literal("retired"));

export const languageTables = {
  approvedPhrases: defineTable({
    organizationId: v.optional(v.string()),
    language: v.string(),
    normalizedKey: v.string(),
    status: lifecycle,
  }).index("by_organizationId_and_language_and_normalizedKey", [
    "organizationId",
    "language",
    "normalizedKey",
  ]),
  approvedPhraseVersions: defineTable({
    phraseId: v.id("approvedPhrases"),
    version: v.number(),
    text: v.string(),
    reviewerMemberId: v.string(),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
    approvedAt: v.optional(v.number()),
  }).index("by_phraseId_and_version", ["phraseId", "version"]),
  glossaryTerms: defineTable({
    organizationId: v.optional(v.string()),
    language: v.string(),
    normalizedKey: v.string(),
    status: lifecycle,
  }).index("by_organizationId_and_language_and_normalizedKey", [
    "organizationId",
    "language",
    "normalizedKey",
  ]),
  glossaryTermVersions: defineTable({
    termId: v.id("glossaryTerms"),
    version: v.number(),
    definition: v.string(),
    reviewerMemberId: v.string(),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
    approvedAt: v.optional(v.number()),
  }).index("by_termId_and_version", ["termId", "version"]),
  languageExamples: defineTable({
    organizationId: v.optional(v.string()),
    language: v.string(),
    normalizedKey: v.string(),
    status: lifecycle,
  }).index("by_organizationId_and_language_and_normalizedKey", [
    "organizationId",
    "language",
    "normalizedKey",
  ]),
  languageExampleVersions: defineTable({
    exampleId: v.id("languageExamples"),
    version: v.number(),
    inputText: v.string(),
    outputText: v.string(),
    reviewerMemberId: v.string(),
    sourceVersionId: v.optional(v.id("knowledgeSourceVersions")),
    approvedAt: v.optional(v.number()),
  }).index("by_exampleId_and_version", ["exampleId", "version"]),
  languageCorrections: defineTable({
    targetVersionId: v.string(),
    replacementVersionId: v.optional(v.string()),
    reason: v.string(),
    reviewerMemberId: v.string(),
    createdAt: v.number(),
  }).index("by_targetVersionId_and_createdAt", ["targetVersionId", "createdAt"]),
};
