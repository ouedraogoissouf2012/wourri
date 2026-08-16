import { ConvexError } from "convex/values";

// §29 / OBS-04 — canonical error taxonomy. Every guard, tool and pipeline step
// classifies failures against this list so feedback and traces stay comparable.
export const ERROR_TYPES = {
  ASR: "ASR_ERROR",
  TRANSLATION: "TRANSLATION_ERROR",
  RAG: "RAG_ERROR",
  SOURCE: "SOURCE_ERROR",
  TOOL: "TOOL_ERROR",
  HALLUCINATION: "LLM_HALLUCINATION",
  OUTDATED_DATA: "OUTDATED_DATA",
  TTS: "TTS_PRONUNCIATION",
  PERMISSION: "PERMISSION_ERROR",
  DELIVERY: "DELIVERY_ERROR",
  INTERNAL: "INTERNAL_ERROR",
} as const;

export type ErrorType = (typeof ERROR_TYPES)[keyof typeof ERROR_TYPES];

export const ALL_ERROR_TYPES: ErrorType[] = Object.values(ERROR_TYPES);

// A domain error that carries a taxonomy code. Thrown fail-closed; the message
// is safe to surface, secrets never belong here.
export class WouriError extends ConvexError<{
  errorType: ErrorType;
  message: string;
}> {
  constructor(errorType: ErrorType, message: string) {
    super({ errorType, message });
  }
}
