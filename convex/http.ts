import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { internal } from "./_generated/api";
import { authComponent, createAuth } from "./auth";

const http = httpRouter();

authComponent.registerRoutes(http, createAuth);

const runtimeEnvironment = globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};

/** 👎 moteur → file locuteur (Bronze / needs_review). Clé = X-Callback-Key. */
http.route({
  path: "/lqe/bronze-task",
  method: "POST",
  handler: httpAction(async (ctx, req) => {
    const expected =
      runtimeEnvironment.process?.env?.X_CALLBACK_KEY ??
      runtimeEnvironment.process?.env?.CONVEX_CALLBACK_KEY ??
      "";
    const got = req.headers.get("X-Callback-Key") ?? "";
    if (!expected || got !== expected) {
      return new Response(JSON.stringify({ error: "unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
    let body: unknown;
    try {
      body = await req.json();
    } catch {
      return new Response(JSON.stringify({ error: "invalid_json" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (!body || typeof body !== "object") {
      return new Response(JSON.stringify({ error: "invalid_body" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }
    const b = body as Record<string, unknown>;
    const organizationId =
      typeof b.organizationId === "string" ? b.organizationId : "";
    if (!organizationId) {
      return new Response(JSON.stringify({ error: "organizationId_required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }
    const language = typeof b.language === "string" ? b.language : "dyu";
    const cultures = Array.isArray(b.cultures)
      ? b.cultures.filter((c): c is string => typeof c === "string")
      : undefined;
    const id = await ctx.runMutation(internal.language.engineIngest.insertBronzeFromEngine, {
      organizationId,
      language,
      intent: typeof b.intent === "string" ? b.intent : undefined,
      source: typeof b.source === "string" ? b.source : undefined,
      excerpt: typeof b.excerpt === "string" ? b.excerpt : undefined,
      cultures,
    });
    return new Response(JSON.stringify({ ok: true, id }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

export default http;
