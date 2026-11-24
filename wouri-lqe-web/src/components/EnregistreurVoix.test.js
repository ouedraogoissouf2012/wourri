// Tests de la presentation de l'enregistreur partage (ADR-0045, revision du 2026-11-24).
// Le cycle lui-meme (micro, flux, extrait) est teste dans useEnregistreur.test.js ;
// ici : ce que voit et declenche le locuteur.

import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { ref } from "vue";
import EnregistreurVoix from "./EnregistreurVoix.vue";

/** Enregistreur factice : les etats se posent a la main, demarrer est espionne. */
function faux({ enCours = false, extrait = null, resultat = { ok: true } } = {}) {
  return {
    enCours: ref(enCours),
    extrait: ref(extrait),
    demarrer: vi.fn().mockResolvedValue(resultat),
    arreter: vi.fn(),
    effacer: vi.fn(),
  };
}

const textes = (w) => w.findAll("button").map((b) => b.text());

describe("EnregistreurVoix", () => {
  it("au repos : un seul bouton, au libelle par defaut", () => {
    const w = mount(EnregistreurVoix, { props: { enregistreur: faux() } });
    expect(textes(w)).toEqual(["🎙️ Enregistrer"]);
  });

  it("accepte un libelle propre a l'ecran", () => {
    const w = mount(EnregistreurVoix, { props: { enregistreur: faux(), libelle: "🎙️ Redire la réponse" } });
    expect(textes(w)).toEqual(["🎙️ Redire la réponse"]);
  });

  it("annonce le demarrage, puis le refus avec son message", async () => {
    const e = faux({ resultat: { ok: false, erreur: "Micro non autorisé" } });
    const w = mount(EnregistreurVoix, { props: { enregistreur: e } });
    await w.find("button").trigger("click");
    await flushPromises();
    expect(e.demarrer).toHaveBeenCalledTimes(1);
    expect(w.emitted("demarrage")).toHaveLength(1);
    expect(w.emitted("refus")).toEqual([["Micro non autorisé"]]);
  });

  it("n'annonce aucun refus quand le demarrage reussit", async () => {
    const w = mount(EnregistreurVoix, { props: { enregistreur: faux() } });
    await w.find("button").trigger("click");
    await flushPromises();
    expect(w.emitted("refus")).toBeUndefined();
  });

  it("en cours : seul « Arrêter », qui arrete", async () => {
    const e = faux({ enCours: true });
    const w = mount(EnregistreurVoix, { props: { enregistreur: e } });
    expect(textes(w)).toEqual(["⏹️ Arrêter"]);
    await w.find("button").trigger("click");
    expect(e.arreter).toHaveBeenCalledTimes(1);
  });

  it("extrait pret : le lecteur et « Refaire », qui efface", async () => {
    const e = faux({ extrait: { blob: new Blob(["a"]), url: "blob:x", mime: "audio/webm" } });
    const w = mount(EnregistreurVoix, { props: { enregistreur: e } });
    expect(w.find("audio").attributes("src")).toBe("blob:x");
    expect(textes(w)).toEqual(["Refaire"]);
    await w.find("button").trigger("click");
    expect(e.effacer).toHaveBeenCalledTimes(1);
  });
});
