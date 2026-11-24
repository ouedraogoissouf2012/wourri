// Correction d'une fiche dans l'atelier, voix comprise (ADR-0045, revision du 2026-11-24).
//
// Ce qui casse en silence ici : la voix part AVANT le texte (le serveur l'attacherait a
// l'ancienne reponse), un echec de la voix efface l'extrait que le locuteur vient de dire,
// ou un bouton de la fiche reprend le mot « Enregistrer » pour sauvegarder — le piege
// meme que la revision supprime.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import FicheCorrection from "./FicheCorrection.vue";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));

// Textes repris de la dictee validee du locuteur (StudioView.test.js) : aucun baoule invente.
const PAIRE = {
  id: "2", kind: "paire_qr",
  text_local: "Blɛ benin nun yɛ ɔ fata kɛ amun lua kakao waka ɔ ?",
  text_fr: "Quand faut-il planter le cacaoyer ?",
  meta: { reponse_bci: "Be lua i …", reponse_fr: "Au début de la saison des pluies." },
};
const MOT = { id: "1", kind: "mot_cle", text_local: "kakao", text_fr: "cacao", meta: {} };
const CONTENU = { id: "3", text_local: "Aw ni ce", text_fr: "Merci" };

class FakeMediaRecorder {
  constructor() {
    this.state = "inactive";
    this.mimeType = "audio/webm;codecs=opus";
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    if (this.ondataavailable) this.ondataavailable({ data: new Blob(["voix"], { type: this.mimeType }) });
    if (this.onstop) this.onstop();
  }
}

let getUserMedia;

const boutons = (w) => w.findAll("button").map((b) => b.text());
const bouton = (w, libelle) => w.findAll("button").find((b) => b.text().includes(libelle));
const appels = () => apiMock.mock.calls.map(([path]) => path);

async function cliquer(w, libelle) {
  await bouton(w, libelle).trigger("click");
  await flushPromises();
}

async function redireLaReponse(w) {
  await cliquer(w, "Redire la réponse");
  await cliquer(w, "Arrêter");
}

beforeEach(() => {
  apiMock.mockReset();
  apiMock.mockResolvedValue({ ok: true });
  getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, writable: true, value: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:voix");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
});

afterEach(() => {
  delete navigator.mediaDevices;
  vi.restoreAllMocks();
});

describe("FicheCorrection — le mot « Enregistrer » ne veut plus dire sauvegarder", () => {
  it("aucun bouton de la fiche ne dit « Enregistrer », pour aucun type", () => {
    for (const fiche of [PAIRE, MOT, CONTENU]) {
      const w = mount(FicheCorrection, { props: { fiche } });
      expect(boutons(w).some((t) => t.includes("Enregistrer"))).toBe(false);
      expect(bouton(w, "Valider la correction")).toBeTruthy();
    }
  });

  it("la confirmation ne dit jamais « Enregistré », avec ou sans voix", async () => {
    const sansVoix = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await cliquer(sansVoix, "Valider la correction");
    const avecVoix = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await redireLaReponse(avecVoix);
    await cliquer(avecVoix, "Valider la correction");
    const messages = [...sansVoix.emitted("fini"), ...avecVoix.emitted("fini")].map(([m]) => m);
    expect(messages).toHaveLength(2);
    messages.forEach((m) => expect(m).not.toMatch(/enregistr/i));
  });
});

describe("FicheCorrection — la voix", () => {
  it("seule une paire offre de redire la réponse", () => {
    expect(bouton(mount(FicheCorrection, { props: { fiche: PAIRE } }), "Redire la réponse")).toBeTruthy();
    expect(bouton(mount(FicheCorrection, { props: { fiche: MOT } }), "Redire la réponse")).toBeFalsy();
    expect(bouton(mount(FicheCorrection, { props: { fiche: CONTENU } }), "Redire la réponse")).toBeFalsy();
  });

  it("le texte part d'abord, la voix ensuite : le serveur l'attache a la reponse corrigee", async () => {
    const w = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await redireLaReponse(w);
    await cliquer(w, "Valider la correction");
    expect(appels()).toEqual(["/tasks/edit", "/tasks/2/voix"]);
    const [, options] = apiMock.mock.calls[1];
    expect(options.method).toBe("POST");
    const fichier = options.body.get("audio");
    expect(fichier.name).toBe("voix.webm");
    expect(w.emitted("fini")).toHaveLength(1);
  });

  it("sans voix, seule la correction du texte part : la voix reste facultative", async () => {
    const w = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await cliquer(w, "Valider la correction");
    expect(appels()).toEqual(["/tasks/edit"]);
    expect(w.emitted("fini")).toHaveLength(1);
  });

  it("la voix qui echoue : erreur dans la fiche, extrait conserve, fiche ouverte", async () => {
    apiMock.mockImplementation(async (path) => {
      if (path.endsWith("/voix")) throw new Error("audio_trop_grand");
      return { ok: true };
    });
    const w = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await redireLaReponse(w);
    await cliquer(w, "Valider la correction");
    expect(w.find("[data-erreur]").text()).toContain("audio_trop_grand");
    expect(w.find("audio[src='blob:voix']").exists()).toBe(true);
    expect(w.emitted("fini")).toBeUndefined();
  });

  it("le texte qui echoue : erreur, et la voix ne part pas", async () => {
    apiMock.mockRejectedValue(new Error("locked"));
    const w = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await redireLaReponse(w);
    await cliquer(w, "Valider la correction");
    expect(appels()).toEqual(["/tasks/edit"]);
    expect(w.find("[data-erreur]").text()).toContain("locked");
    expect(w.emitted("fini")).toBeUndefined();
  });

  it("micro refuse : message dans la fiche, la correction se valide quand meme", async () => {
    getUserMedia.mockRejectedValue(new DOMException("Permission denied", "NotAllowedError"));
    const w = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await cliquer(w, "Redire la réponse");
    expect(w.find("[data-erreur]").text()).toContain("Micro non autorisé");
    await cliquer(w, "Valider la correction");
    expect(appels()).toEqual(["/tasks/edit"]);
    expect(w.emitted("fini")).toHaveLength(1);
  });
});

describe("FicheCorrection — annuler", () => {
  it("« Annuler » ne sauvegarde rien", async () => {
    const w = mount(FicheCorrection, { props: { fiche: PAIRE } });
    await cliquer(w, "Annuler");
    expect(apiMock).not.toHaveBeenCalled();
    expect(w.emitted("annule")).toHaveLength(1);
  });
});
