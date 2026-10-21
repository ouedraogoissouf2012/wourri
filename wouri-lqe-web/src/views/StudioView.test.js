// Ecran « Atelier langues » : types d'element (ADR-0045).
//
// Un mot-cle ou une paire question/reponse se valide dans « A accepter » avec son sens
// affiche, mais n'apparait jamais dans « A promouvoir » (ce n'est pas du contenu servi).
// Voir src/views/StudioView.vue.

import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import StudioView from "./StudioView.vue";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

// Textes repris de la dictee validee du locuteur (aucun baoule invente).
const MOT = { id: "1", kind: "mot_cle", text_local: "kakao", text_fr: "cacao", meta: {} };
const PAIRE = {
  id: "2", kind: "paire_qr",
  text_local: "Blɛ benin nun yɛ ɔ fata kɛ amun lua kakao waka ɔ ?",
  text_fr: "Quand faut-il planter le cacaoyer ?",
  meta: { reponse_bci: "Be lua i …", reponse_fr: "Au début de la saison des pluies." },
};
const CONTENU = { id: "3", text_local: "Aw ni ce", text_fr: "Merci" };

function routes({ bronze = [], accepted = [] } = {}) {
  apiMock.mockImplementation(async (path) => {
    if (path === "/auth/me") return { user: "loc", language: "bci", roles: ["ingest", "review", "promote"] };
    if (path === "/tasks") return { bronze, accepted };
    if (path === "/corpus") return { entries: [] };
    return {};
  });
}

describe("StudioView — types d'element", () => {
  it("affiche le sens d'un mot-cle et d'une paire dans « A accepter »", async () => {
    routes({ bronze: [MOT, PAIRE, CONTENU] });
    const w = mount(StudioView);
    await flushPromises();
    const text = w.text();
    expect(w.find('[data-kind="mot_cle"]').exists()).toBe(true);
    expect(text).toContain("« kakao » veut dire : cacao");
    expect(w.find('[data-kind="paire_qr"]').exists()).toBe(true);
    expect(text).toContain("Réponse proposée");
    expect(text).toContain("Au début de la saison des pluies.");
    // « Corriger » : mot-cle et contenu oui, paire non (on accepte ou on rejette la paire)
    const articles = w.findAll("article");
    const corriger = (a) => a.findAll("button").some((b) => b.text() === "Corriger");
    expect(articles.map(corriger)).toEqual([true, false, true]);
  });

  it("n'affiche que le contenu dans « A promouvoir »", async () => {
    routes({ accepted: [MOT, CONTENU] });
    const w = mount(StudioView);
    await flushPromises();
    const onglet = w.findAll("nav button").find((b) => b.text().startsWith("À promouvoir"));
    expect(onglet.text()).toBe("À promouvoir (1)");
    await onglet.trigger("click");
    const section = w.findAll("section").find((s) => s.text().includes("Promouvoir"));
    expect(section.text()).toContain("Aw ni ce");
    expect(section.text()).not.toContain("kakao");
  });
});
