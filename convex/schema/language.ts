import { defineTable } from "convex/server";
import { v } from "convex/values";

const lifecycle = v.union(v.literal("draft"), v.literal("approved"), v.literal("retired"));

export const languageTables = {
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
  // §24 / LNG-04 / G09 — rich linguistic feedback record for the validator
  // console. A validated record feeds glossary/corpus/examples; versions are
  // kept, never silently overwritten.
  linguisticFeedback: defineTable({
    organizationId: v.optional(v.string()),
    language: v.string(),
    culture: v.optional(v.string()),
    region: v.optional(v.string()),
    audioStorageId: v.optional(v.id("_storage")),
    rawTranscript: v.optional(v.string()),
    validatedTranscript: v.optional(v.string()),
    rawTranslation: v.optional(v.string()),
    validatedTranslation: v.optional(v.string()),
    translationDirection: v.optional(
      v.union(v.literal("local_to_fr"), v.literal("fr_to_local")),
    ),
    generatedOutput: v.optional(v.string()),
    audioRating: v.optional(v.number()),
    naturalnessScore: v.optional(v.number()),
    agriculturalVocabularyScore: v.optional(v.number()),
    errorType: v.optional(v.string()),
    comment: v.optional(v.string()),
    reviewerMemberId: v.string(),
    status: v.union(
      v.literal("draft"),
      v.literal("needs_review"),
      v.literal("validated"),
      v.literal("rejected"),
    ),
    version: v.number(),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_organizationId_and_status", ["organizationId", "status"])
    .index("by_language_and_status", ["language", "status"])
    .index("by_reviewerMemberId_and_createdAt", [
      "reviewerMemberId",
      "createdAt",
    ]),
};
