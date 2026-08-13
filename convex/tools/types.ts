// §22 / §23 — shared tool result contract. Every business tool returns a stable
// shape: either "ok" with data and provenance, or "insufficient_evidence" with a
// reason. Tools never invent data; absence of a source yields abstention.

export type ToolProvenance = {
  documentId?: string;
  sourceId?: string;
  sourceVersionId?: string;
  authority?: string;
  version?: string;
  title?: string;
  dataOrigin?: string;
};

export type ToolOk<T> = {
  status: "ok";
  data: T;
  provenance: ToolProvenance[];
};

export type ToolAbstained = {
  status: "insufficient_evidence";
  reason: string;
};

export type ToolResult<T> = ToolOk<T> | ToolAbstained;

export const abstain = (reason: string): ToolAbstained => ({
  status: "insufficient_evidence",
  reason,
});
