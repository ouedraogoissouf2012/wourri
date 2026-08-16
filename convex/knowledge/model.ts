import type { MutationCtx, QueryCtx } from "../_generated/server";
import type { Id } from "../_generated/dataModel";

// KNO-01 / §18 — provenance registry. Sources and their versions keep SODEXAM
// and CNRA identifiable as owners/origins; documents attribute each ingested
// content to an exact source version. The RAG component owns the searchable
// vector chunks; these tables own the citable provenance.

export type SourceVisibility = "global" | "organization";

export const createSource = async (
  ctx: MutationCtx,
  input: {
    organizationId?: string;
    visibility: SourceVisibility;
    authority: string;
    license: string;
    canonicalLocator: string;
  },
): Promise<Id<"knowledgeSources">> =>
  ctx.db.insert("knowledgeSources", { ...input, status: "active" });

export const getSource = async (ctx: QueryCtx | MutationCtx, sourceId: Id<"knowledgeSources">) =>
  ctx.db.get(sourceId);

export const listSourcesVisibleToOrg = async (
  ctx: QueryCtx | MutationCtx,
  organizationId: string,
) => {
  const globals = await ctx.db
    .query("knowledgeSources")
    .withIndex("by_organizationId_and_visibility", (q) =>
      q.eq("organizationId", undefined).eq("visibility", "global"),
    )
    .take(200);
  const owned = await ctx.db
    .query("knowledgeSources")
    .withIndex("by_organizationId_and_visibility", (q) =>
      q.eq("organizationId", organizationId).eq("visibility", "organization"),
    )
    .take(200);
  return [...globals, ...owned];
};

export const createSourceVersion = async (
  ctx: MutationCtx,
  input: {
    sourceId: Id<"knowledgeSources">;
    version: string;
    contentHash: string;
    acquiredAt: number;
    acquisitionMethod: string;
    publisherMetadata?: string;
  },
): Promise<Id<"knowledgeSourceVersions">> =>
  ctx.db.insert("knowledgeSourceVersions", input);

export const getSourceVersion = async (
  ctx: QueryCtx | MutationCtx,
  sourceVersionId: Id<"knowledgeSourceVersions">,
) => ctx.db.get(sourceVersionId);

export const createDocument = async (
  ctx: MutationCtx,
  input: {
    sourceVersionId: Id<"knowledgeSourceVersions">;
    title: string;
    locator: string;
    language: string;
    mimeType: string;
    contentHash: string;
  },
): Promise<Id<"knowledgeDocuments">> =>
  ctx.db.insert("knowledgeDocuments", { ...input, status: "ready" });

// Provenance for a source version, used to cite search results precisely.
export const getProvenance = async (
  ctx: QueryCtx | MutationCtx,
  sourceVersionId: Id<"knowledgeSourceVersions">,
) => {
  const version = await ctx.db.get(sourceVersionId);
  if (!version) return null;
  const source = await ctx.db.get(version.sourceId);
  return { source, version };
};

// Tenant check: a source version is usable by an org if its source is global or
// owned by that org. Returns the source when allowed, else null (fail closed).
export const sourceVersionVisibleToOrg = async (
  ctx: QueryCtx | MutationCtx,
  sourceVersionId: Id<"knowledgeSourceVersions">,
  organizationId: string,
) => {
  const version = await ctx.db.get(sourceVersionId);
  if (!version) return null;
  const source = await ctx.db.get(version.sourceId);
  if (!source) return null;
  const visible =
    source.visibility === "global" || source.organizationId === organizationId;
  return visible ? { source, version } : null;
};
