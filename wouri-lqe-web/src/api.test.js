// Tests du client HTTP de l'atelier LQE (dette #492).
//
// Ce qui casse en silence ici : le cookie de session (front lqe.* et API lqe-api.*
// sont sur des origines distinctes → sans credentials:"include" toutes les vues se
// vident sans message), et la redirection sur 401 (sans elle l'utilisateur reste
// sur une page morte). Voir src/api.js.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";

const HOME = "http://lqe.test/";

/** Reponse fetch minimale : seuls status/ok/json sont lus par api(). */
function res(status, body, { jsonThrows = false } = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: () =>
      jsonThrows
        ? Promise.reject(new SyntaxError("Unexpected token < in JSON"))
        : Promise.resolve(body),
  };
}

let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  // window === globalThis sous l'environnement jsdom : stubGlobal suffit pour
  // intercepter le window.location.href = "/login" de api().
  vi.stubGlobal("location", { href: HOME });
});

describe("api() — cookie de session", () => {
  it("envoie credentials:'include' sur chaque appel", async () => {
    fetchMock.mockResolvedValue(res(200, { user: "aya" }));

    await api("/auth/me");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/auth/me");
    expect(init.credentials).toBe("include");
  });

  it("conserve credentials:'include' quand l'appelant passe ses propres options", async () => {
    fetchMock.mockResolvedValue(res(200, {}));
    const body = JSON.stringify({ id: 7, decision: "admin_accepted" });

    await api("/tasks/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init).toMatchObject({
      credentials: "include",
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
    });
  });

  it("prefixe le chemin avec VITE_API_BASE quand l'API est sur une autre origine", async () => {
    vi.stubEnv("VITE_API_BASE", "https://lqe-api.test");
    vi.resetModules(); // BASE est fige a l'import du module
    const { api: apiWithBase } = await import("./api.js");
    fetchMock.mockResolvedValue(res(200, {}));

    await apiWithBase("/coverage");

    expect(fetchMock.mock.calls[0][0]).toBe("https://lqe-api.test/coverage");
  });
});

describe("api() — 401 et redirection", () => {
  it("redirige vers /login et leve une erreur portant status 401", async () => {
    fetchMock.mockResolvedValue(res(401, { detail: "session_expiree" }));

    await expect(api("/tasks")).rejects.toMatchObject({ message: "session", status: 401 });
    expect(location.href).toBe("/login");
  });

  it("ne redirige pas quand c'est /auth/login qui repond 401 (mauvais identifiants)", async () => {
    fetchMock.mockResolvedValue(res(401, { detail: "bad_credentials" }));

    await expect(
      api("/auth/login", { method: "POST", body: JSON.stringify({ user: "x", password: "y" }) })
    ).rejects.toMatchObject({ status: 401 });
    expect(location.href).toBe(HOME);
  });

  it("redirige meme si le corps du 401 n'est pas du JSON (page d'erreur du proxy)", async () => {
    fetchMock.mockResolvedValue(res(401, null, { jsonThrows: true }));

    await expect(api("/corpus")).rejects.toMatchObject({ status: 401 });
    expect(location.href).toBe("/login");
  });
});

describe("api() — erreurs HTTP", () => {
  it("leve le detail renvoye par l'API", async () => {
    fetchMock.mockResolvedValue(res(400, { detail: "langue_inconnue" }));

    await expect(api("/assignments", { method: "POST" })).rejects.toThrow("langue_inconnue");
  });

  it("retombe sur reason quand detail est absent", async () => {
    fetchMock.mockResolvedValue(res(409, { reason: "doublon" }));

    await expect(api("/ingest/json", { method: "POST" })).rejects.toThrow("doublon");
  });

  it("retombe sur le code HTTP quand le corps est vide", async () => {
    fetchMock.mockResolvedValue(res(500, {}));

    await expect(api("/tasks")).rejects.toThrow("500");
  });

  it("retombe sur le code HTTP quand le corps n'est pas du JSON", async () => {
    fetchMock.mockResolvedValue(res(502, null, { jsonThrows: true }));

    await expect(api("/tasks")).rejects.toThrow("502");
  });

  it("ne redirige pas sur une erreur non-401 (403 = role insuffisant, session valide)", async () => {
    fetchMock.mockResolvedValue(res(403, { detail: "role_insuffisant" }));

    await expect(api("/accounts")).rejects.toThrow("role_insuffisant");
    expect(location.href).toBe(HOME);
  });
});

describe("api() — succes", () => {
  it("retourne le JSON decode", async () => {
    fetchMock.mockResolvedValue(res(200, { assigned: 3, already: 1, skipped: [] }));

    await expect(api("/assignments", { method: "POST" })).resolves.toEqual({
      assigned: 3,
      already: 1,
      skipped: [],
    });
  });

  it("retourne un objet vide quand la reponse n'a pas de corps JSON (204)", async () => {
    fetchMock.mockResolvedValue(res(204, null, { jsonThrows: true }));

    await expect(api("/auth/logout", { method: "POST" })).resolves.toEqual({});
  });
});
