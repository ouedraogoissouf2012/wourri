import { RAG } from "@convex-dev/rag";
import { components } from "../_generated/api";
import {
  createLocalEmbeddingModel,
  LOCAL_EMBEDDING_DIMENSION,
} from "./embeddingModel";

// KNO-04 / §21 — knowledge RAG. Tenant isolation is enforced by NAMESPACE:
// org-scoped sources live in their organization namespace, global sources
// (SODEXAM/CNRA published widely) live in the shared "global" namespace. Filters
// narrow retrieval by source, version, authority, language, zone and culture,
// and every result carries provenance metadata for citation.

export type KnowledgeFilters = {
  sourceId: string;
  sourceVersionId: string;
  authority: string;
  language: string;
  zone: string;
  culture: string;
  version: string;
};

export const GLOBAL_NAMESPACE = "global";

export const knowledgeNamespace = (
  visibility: "global" | "organization",
  organizationId?: string,
): string =>
  visibility === "global" || !organizationId ? GLOBAL_NAMESPACE : organizationId;

export const rag = new RAG<KnowledgeFilters>(components.rag, {
  textEmbeddingModel: createLocalEmbeddingModel(),
  embeddingDimension: LOCAL_EMBEDDING_DIMENSION,
  filterNames: [
    "sourceId",
    "sourceVersionId",
    "authority",
    "language",
    "zone",
    "culture",
    "version",
  ],
});
