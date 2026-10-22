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

function routes({ bronze = [], accepted = [], decided = [] } = {}) {
  apiMock.mockImplementation(async (path) => {
    if (path === "/auth/me") return { user: "loc", language: "bci", roles: ["ingest", "review", "promote"] };
    if (path === "/tasks") return { bronze, accepted, decided };
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
    // le plus recent (id le plus grand) en haut : contenu (3), paire (2), mot-cle (1)
    expect(articles.map(corriger)).toEqual([true, false, true]);
    expect(articles[0].text()).toContain("Aw ni ce");
    expect(articles[2].text()).toContain("kakao");
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

describe("StudioView — Mes décisions", () => {
  it("montre l'état et le texte d'origine, et « Reprendre » remet la fiche à accepter", async () => {
    const corrige = { ...MOT, status: "admin_rejected", text_local: "kakaw",
                      meta: { texte_origine: { text_local: "kakao", text_fr: "cacao" } } };
    routes({ decided: [corrige, { ...PAIRE, status: "admin_accepted" }] });
    const w = mount(StudioView);
    await flushPromises();
    const onglet = w.findAll("nav button").find((b) => b.text().startsWith("Mes décisions"));
    expect(onglet.text()).toBe("Mes décisions (2)");
    await onglet.trigger("click");
    const fiches = w.findAll("[data-etat]");
    expect(fiches.map((a) => a.attributes("data-etat"))).toEqual(["admin_accepted", "admin_rejected"]);
    expect(fiches[1].text()).toContain("Rejeté");
    expect(fiches[1].text()).toContain("Texte d'origine : kakao");
    await fiches[1].findAll("button").find((b) => b.text() === "Reprendre").trigger("click");
    await flushPromises();
    const appel = apiMock.mock.calls.find(([path]) => path === "/tasks/reprendre");
    expect(JSON.parse(appel[1].body)).toEqual({ id: "1" });
  });
});
