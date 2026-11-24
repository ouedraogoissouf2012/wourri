// Tests de l'enregistreur partage (ADR-0045, revision du 2026-11-24).
//
// Ce qui casse en silence ici : le micro reste ouvert (pistes non arretees, au
// demontage ou apres un echec), un double-clic ouvre deux flux orphelins, un echec
// laisse le bouton mort pour de bon, et une URL d'extrait jamais revoquee fuit.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import {
  MESSAGE_ENREGISTREUR_INDISPONIBLE,
  MESSAGE_MICRO_REFUSE,
  useEnregistreur,
} from "./useEnregistreur.js";

class FakeMediaRecorder {
  static instances = [];

  constructor(stream) {
    this.stream = stream;
    this.state = "inactive";
    this.mimeType = "audio/ogg;codecs=opus";
    this.ondataavailable = null;
    this.onstop = null;
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    if (this.ondataavailable) this.ondataavailable({ data: new Blob(["audio"], { type: this.mimeType }) });
    if (this.onstop) this.onstop();
  }
}

/** Fidele au vrai MediaRecorder : stop() passe a « inactive » TOUT DE SUITE, mais
 *  dataavailable et stop ne tirent que plus tard (ici : quand le test appelle tirer()). */
class DeferredMediaRecorder extends FakeMediaRecorder {
  stop() {
    this.state = "inactive";
  }

  tirer() {
    if (this.ondataavailable) this.ondataavailable({ data: new Blob(["audio"], { type: this.mimeType }) });
    if (this.onstop) this.onstop();
  }
}

let piste;
let getUserMedia;

/** Monte un composant hote : le composable a besoin d'un cycle de vie (onUnmounted). */
function monterHote() {
  let enregistreur;
  const Hote = defineComponent({
    setup() {
      enregistreur = useEnregistreur();
      return () => h("div");
    },
  });
  const wrapper = mount(Hote);
  return { wrapper, enregistreur };
}

beforeEach(() => {
  FakeMediaRecorder.instances = [];
  piste = { stop: vi.fn() };
  getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [piste] });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    writable: true,
    value: { getUserMedia },
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:extrait");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
});

afterEach(() => {
  delete navigator.mediaDevices;
  vi.restoreAllMocks();
});

describe("useEnregistreur — demarrage", () => {
  it("ouvre le micro et lance l'enregistrement", async () => {
    const { enregistreur } = monterHote();
    const res = await enregistreur.demarrer();
    expect(res).toEqual({ ok: true });
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(FakeMediaRecorder.instances).toHaveLength(1);
    expect(FakeMediaRecorder.instances[0].state).toBe("recording");
    expect(enregistreur.enCours.value).toBe(true);
  });

  it("n'ouvre qu'un seul flux malgre un second appel pendant getUserMedia", async () => {
    let liberer;
    getUserMedia.mockImplementation(() => new Promise((r) => (liberer = r)));
    const { enregistreur } = monterHote();
    const premier = enregistreur.demarrer();
    expect(await enregistreur.demarrer()).toEqual({ ok: false });
    liberer({ getTracks: () => [piste] });
    await premier;
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });
});

describe("useEnregistreur — echecs", () => {
  it("refus du micro : message, aucun enregistrement, nouvel essai possible", async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException("Permission denied", "NotAllowedError"));
    const { enregistreur } = monterHote();
    expect(await enregistreur.demarrer()).toEqual({ ok: false, erreur: MESSAGE_MICRO_REFUSE });
    expect(FakeMediaRecorder.instances).toHaveLength(0);
    expect(enregistreur.enCours.value).toBe(false);
    expect(await enregistreur.demarrer()).toEqual({ ok: true });
  });

  it("contexte sans micro (navigator.mediaDevices absent) : meme message", async () => {
    delete navigator.mediaDevices;
    const { enregistreur } = monterHote();
    expect(await enregistreur.demarrer()).toEqual({ ok: false, erreur: MESSAGE_MICRO_REFUSE });
  });

  it("MediaRecorder qui leve : micro relache, message, bouton pas mort", async () => {
    vi.stubGlobal("MediaRecorder", class {
      constructor() {
        throw new Error("MediaRecorder non pris en charge");
      }
    });
    const { enregistreur } = monterHote();
    expect(await enregistreur.demarrer()).toEqual({ ok: false, erreur: MESSAGE_ENREGISTREUR_INDISPONIBLE });
    expect(piste.stop).toHaveBeenCalledTimes(1);
    expect(enregistreur.enCours.value).toBe(false);
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    expect(await enregistreur.demarrer()).toEqual({ ok: true });
  });
});

describe("useEnregistreur — arret et extrait", () => {
  it("arreter relache le micro et produit l'extrait", async () => {
    const { enregistreur } = monterHote();
    await enregistreur.demarrer();
    enregistreur.arreter();
    expect(piste.stop).toHaveBeenCalledTimes(1);
    expect(enregistreur.enCours.value).toBe(false);
    const extrait = enregistreur.extrait.value;
    expect(extrait.url).toBe("blob:extrait");
    expect(extrait.mime).toBe("audio/ogg;codecs=opus");
    expect(extrait.blob).toBeInstanceOf(Blob);
  });

  it("effacer revoque l'URL de l'extrait", async () => {
    const { enregistreur } = monterHote();
    await enregistreur.demarrer();
    enregistreur.arreter();
    enregistreur.effacer();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:extrait");
    expect(enregistreur.extrait.value).toBeNull();
  });

  it("un extrait pret bloque un nouveau demarrage", async () => {
    const { enregistreur } = monterHote();
    await enregistreur.demarrer();
    enregistreur.arreter();
    expect(await enregistreur.demarrer()).toEqual({ ok: false });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });
});

describe("useEnregistreur — demontage", () => {
  it("pendant l'enregistrement : micro relache, aucun extrait cree", async () => {
    const { wrapper, enregistreur } = monterHote();
    await enregistreur.demarrer();
    wrapper.unmount();
    expect(piste.stop).toHaveBeenCalledTimes(1);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(enregistreur.extrait.value).toBeNull();
  });

  it("pendant l'attente du micro : le flux obtenu ensuite est relache aussitot", async () => {
    let liberer;
    getUserMedia.mockImplementation(() => new Promise((r) => (liberer = r)));
    const { wrapper, enregistreur } = monterHote();
    const demarrage = enregistreur.demarrer();
    wrapper.unmount();
    liberer({ getTracks: () => [piste] });
    expect(await demarrage).toEqual({ ok: false });
    await flushPromises();
    expect(piste.stop).toHaveBeenCalledTimes(1);
    expect(FakeMediaRecorder.instances).toHaveLength(0);
  });

  it("« Arrêter » puis demontage avant que onstop tire : aucune URL creee apres", async () => {
    vi.stubGlobal("MediaRecorder", DeferredMediaRecorder);
    const { wrapper, enregistreur } = monterHote();
    await enregistreur.demarrer();
    enregistreur.arreter(); // etat « inactive », evenements encore en vol
    wrapper.unmount();
    FakeMediaRecorder.instances[0].tirer();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(enregistreur.extrait.value).toBeNull();
  });

  it("apres le demontage, demarrer n'ouvre plus jamais le micro", async () => {
    let liberer;
    getUserMedia.mockImplementation(() => new Promise((r) => (liberer = r)));
    const { wrapper, enregistreur } = monterHote();
    const demarrage = enregistreur.demarrer();
    wrapper.unmount();
    liberer({ getTracks: () => [piste] });
    await demarrage;
    expect(await enregistreur.demarrer()).toEqual({ ok: false });
    expect(getUserMedia).toHaveBeenCalledTimes(1);
  });

  it("avec un extrait pret : son URL est revoquee", async () => {
    const { wrapper, enregistreur } = monterHote();
    await enregistreur.demarrer();
    enregistreur.arreter();
    wrapper.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:extrait");
  });
});
