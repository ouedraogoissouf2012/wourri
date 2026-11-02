// Écran « Mes demandes » : le locuteur répond à une assignation (ADR-0047).
//
// Deux catalogues alimentent le même écran — une phrase du corpus, ou un mot pour un
// concept NLU. Le repère dioula est affiché, jamais à recopier (ADR-0046).

import { describe, expect, it, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import RequestsView from "./RequestsView.vue";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const MOT = {
  concept_id: "TEMPS_METEO", source_fr: "météo",
  kind: "mot_cle", ref_dyu: "tile, foroko",
};
const PHRASE = { concept_id: "cacao_001", source_fr: "Plantez en début de saison.", kind: "contenu" };

function routes(assignments) {
  apiMock.mockImplementation(async (path) => {
    if (path === "/assignments") return { assignments };
    if (path === "/auth/me") return { user: "loc", language: "bci", roles: ["ingest"] };
    return {};
  });
}

beforeEach(() => apiMock.mockReset());

describe("RequestsView — demander un mot pour un concept", () => {
  it("annonce qu'on attend un mot et montre le repère dioula", async () => {
    routes([MOT]);
    const w = mount(RequestsView);
    await flushPromises();

    expect(w.find('[data-demande="mot_cle"]').exists()).toBe(true);
    expect(w.text()).toContain("météo");
    const ref = w.find("[data-ref]");
    expect(ref.exists()).toBe(true);
    expect(ref.text()).toContain("tile, foroko");
    // la consigne de ne pas recopier doit être visible, c'est une règle du projet
    expect(ref.text()).toContain("ne pas recopier");
  });

  it("une phrase du corpus reste présentée comme avant", async () => {
    routes([PHRASE]);
    const w = mount(RequestsView);
    await flushPromises();

    expect(w.find('[data-demande="mot_cle"]').exists()).toBe(false);
    expect(w.find("[data-ref]").exists()).toBe(false);
    expect(w.text()).toContain("Plantez en début de saison.");
  });
});
