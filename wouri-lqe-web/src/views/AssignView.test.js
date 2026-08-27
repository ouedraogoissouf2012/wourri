// Tests de l'assignation par lot de concepts (dette #492, ADR-0034 P2/P3).
//
// C'est le comportement « assignation par lot » vise par l'issue : il vit dans
// AssignView (AdminView, lui, gere les comptes locuteurs — cf. AdminView.test.js).
// Ce qui casse en silence ici : un lot envoye vide, un lot envoye a la mauvaise
// langue apres un changement de selecteur, ou une selection qui survit au
// rechargement. Voir src/views/AssignView.vue.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import AssignView from "./AssignView.vue";

const { apiMock, push } = vi.hoisted(() => ({ apiMock: vi.fn(), push: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));

const LANGS = [
  { code: "dyu", name: "Dioula", covered: 12, total: 54, missing: 42, up_to_date: false },
  { code: "bci", name: "Baoule", covered: 0, total: 54, missing: 54, up_to_date: false },
];

// ref_dyu repris du corpus reel (dictionnaires/corpus_ivr.json) : aucun dioula invente.
const CONCEPTS_DYU = [
  { concept_id: "riz_saison_001", source_fr: "Quand planter le riz ?", ref_dyu: "Màlo sɛnɛli waati" },
  { concept_id: "riz_recolte_001", source_fr: "Quand recolter le riz ?", ref_dyu: "Màlo filɛli waati" },
  { concept_id: "engrais_dose_001", source_fr: "Quelle dose d'engrais ?", ref_dyu: null },
];
const CONCEPTS_BCI = [
  { concept_id: "mais_saison_001", source_fr: "Quand semer le mais ?", ref_dyu: null },
];

const ADMIN = { user: "admin", language: "*", roles: ["admin"] };

function btn(wrapper, label) {
  const all = wrapper.findAll("button");
  const found = all.find((b) => b.text().includes(label));
  if (!found) {
    const presents = all.map((b) => b.text()).join(" | ");
    throw new Error('bouton "' + label + '" absent — presents : ' + presents);
  }
  return found;
}

/** Le POST d'assignation, decode. */
function assignPost() {
  const call = apiMock.mock.calls.find(([p, o]) => p === "/assignments" && o && o.method === "POST");
  return call ? { init: call[1], body: JSON.parse(call[1].body) } : null;
}

function missingCalls() {
  return apiMock.mock.calls.filter(([p]) => p.startsWith("/assignments/missing"));
}

function useApi({ me = ADMIN } = {}) {
  apiMock.mockImplementation((path, opt) => {
    if (path === "/auth/me") return Promise.resolve(me);
    if (path === "/coverage") return Promise.resolve({ languages: LANGS });
    if (path.startsWith("/assignments/missing")) {
      const code = new URLSearchParams(path.split("?")[1]).get("language");
      const src = code === "bci" ? CONCEPTS_BCI : CONCEPTS_DYU;
      return Promise.resolve({ concepts: src.map((c) => ({ ...c })) });
    }
    if (path === "/assignments" && opt && opt.method === "POST") {
      const ids = JSON.parse(opt.body).concept_ids;
      return Promise.resolve({ assigned: ids.length, already: 0, skipped: [] });
    }
    return Promise.reject(new Error("appel API inattendu : " + path));
  });
}

async function mountAdmin() {
  const wrapper = mount(AssignView);
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  useApi();
});

describe("AssignView — chargement", () => {
  it("charge les concepts manquants de la premiere langue couverte", async () => {
    const w = await mountAdmin();

    expect(apiMock).toHaveBeenCalledWith("/assignments/missing?language=dyu");
    expect(w.text()).toContain("Quand planter le riz ?");
    expect(w.text()).toContain("Màlo filɛli waati");
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(3);
    expect(w.text()).toContain("0 sélectionné(s)");
  });

  it("renvoie un non-admin vers l'atelier sans rien charger", async () => {
    useApi({ me: { user: "aya", language: "dyu", roles: ["ingest", "review"] } });

    await mountAdmin();

    expect(push).toHaveBeenCalledWith("/");
    expect(missingCalls()).toHaveLength(0);
    expect(apiMock).not.toHaveBeenCalledWith("/coverage");
  });
});

describe("AssignView — assignation par lot", () => {
  it("envoie tout le lot coche a la langue selectionnee et recharge la liste", async () => {
    const w = await mountAdmin();

    await btn(w, "Tout cocher").trigger("click");
    expect(w.text()).toContain("3 sélectionné(s)");
    expect(btn(w, "Assigner").text()).toContain("Assigner 3 concept(s) à dyu");

    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    const post = assignPost();
    expect(post, "aucun POST /assignments").toBeTruthy();
    expect(post.init.headers).toEqual({ "Content-Type": "application/json" });
    expect(post.body).toEqual({
      target_language: "dyu",
      concept_ids: ["riz_saison_001", "riz_recolte_001", "engrais_dose_001"],
    });

    expect(missingCalls()).toHaveLength(2); // la liste est rechargee apres envoi
    expect(w.text()).toContain("0 sélectionné(s)"); // et la selection repartie a zero
  });

  // Test de caracterisation : il fige le comportement REEL, pas l'intention.
  // Bug produit mis au jour par cette suite — assign() pose msg (AssignView.vue:78)
  // puis appelle loadMissing() qui le remet a "" (AssignView.vue:37) avant tout rendu.
  // L'operateur n'a donc aucun retour sur son lot. Correction hors perimetre de #492 :
  // ce test devra etre inverse le jour ou le bug sera corrige.
  it("ne montre AUCUN compte-rendu apres un lot reussi (bug connu, msg efface)", async () => {
    const w = await mountAdmin();

    await btn(w, "Tout cocher").trigger("click");
    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    expect(assignPost().body.concept_ids).toHaveLength(3); // le lot est bien parti
    expect(w.text()).not.toContain("Assignés:"); // ... mais rien ne le dit a l'ecran
  });

  it("n'envoie que les concepts effectivement coches", async () => {
    const w = await mountAdmin();
    const boxes = w.findAll('input[type="checkbox"]');

    await boxes[0].setValue(true);
    await boxes[2].setValue(true);

    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    expect(assignPost().body.concept_ids).toEqual(["riz_saison_001", "engrais_dose_001"]);
  });

  it("refuse un lot vide au lieu de poster une assignation sans effet", async () => {
    const w = await mountAdmin();

    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Sélectionne au moins un concept.");
    expect(assignPost()).toBeNull();
    expect(missingCalls()).toHaveLength(1);
  });

  it("« Tout décocher » vide reellement le lot", async () => {
    const w = await mountAdmin();

    await btn(w, "Tout cocher").trigger("click");
    await btn(w, "Tout décocher").trigger("click");
    expect(w.text()).toContain("0 sélectionné(s)");

    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    expect(assignPost()).toBeNull();
  });

  it("remet la selection a zero quand on change de langue cible", async () => {
    const w = await mountAdmin();
    await btn(w, "Tout cocher").trigger("click");
    expect(w.text()).toContain("3 sélectionné(s)");

    await w.find("select").setValue("bci");
    await flushPromises();

    // sinon les concepts du dioula partiraient sur le baoule
    expect(apiMock).toHaveBeenCalledWith("/assignments/missing?language=bci");
    expect(w.text()).toContain("Quand semer le mais ?");
    expect(w.text()).toContain("0 sélectionné(s)");

    await w.findAll('input[type="checkbox"]')[0].setValue(true);
    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    expect(assignPost().body).toEqual({
      target_language: "bci",
      concept_ids: ["mais_saison_001"],
    });
  });

  it("affiche l'erreur de l'API et conserve le lot pour un nouvel essai", async () => {
    const w = await mountAdmin();
    await btn(w, "Tout cocher").trigger("click");
    apiMock.mockImplementationOnce(() => Promise.reject(new Error("langue_inconnue")));

    await btn(w, "Assigner").trigger("click");
    await flushPromises();

    expect(w.text()).toContain("langue_inconnue");
    expect(missingCalls()).toHaveLength(1); // pas de rechargement : le lot reste coche
    expect(w.text()).toContain("3 sélectionné(s)");
  });
});
