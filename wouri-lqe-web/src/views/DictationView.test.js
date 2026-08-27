// Tests du cycle d'enregistrement audio de la dictee ASR (dette #492, ADR-0035).
//
// Ce qui casse en silence ici : le micro reste ouvert si les pistes ne sont pas
// arretees, un double-clic ouvre deux flux orphelins, un refus de permission laisse
// l'ecran muet, et une mauvaise extension de fichier fait rejeter l'upload cote API.
// Voir src/views/DictationView.vue.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import DictationView from "./DictationView.vue";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));

// Phrases reprises du corpus reel (dictionnaires/corpus_ivr.json) : aucun dioula invente.
const PROMPTS = [
  { id: 11, filiere: "riz", text_local: "Aw ye malo sɛnɛ", text_fr: "Plantez le riz" },
  { id: 12, filiere: "riz", text_local: "Aw ye foro labɛn", text_fr: "Preparez le champ" },
];

class FakeMediaRecorder {
  static instances = [];

  constructor(stream) {
    this.stream = stream;
    this.state = "inactive";
    this.mimeType = "audio/webm;codecs=opus";
    this.ondataavailable = null;
    this.onstop = null;
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = "recording";
  }

  // Le vrai MediaRecorder emet dataavailable puis stop de facon asynchrone ; on les
  // declenche ici de maniere synchrone pour que le test reste deterministe.
  stop() {
    this.state = "inactive";
    if (this.ondataavailable) {
      this.ondataavailable({ data: new Blob(["audio"], { type: this.mimeType }) });
    }
    if (this.onstop) this.onstop();
  }
}

let getUserMedia;
let micTrack;
let micStream;

/** Bouton retrouve par son libelle, avec un message clair s'il a disparu. */
function btn(wrapper, label) {
  const all = wrapper.findAll("button");
  const found = all.find((b) => b.text().includes(label));
  if (!found) {
    const presents = all.map((b) => b.text()).join(" | ");
    throw new Error('bouton "' + label + '" absent — presents : ' + presents);
  }
  return found;
}

function hasBtn(wrapper, label) {
  return wrapper.findAll("button").some((b) => b.text().includes(label));
}

async function mountSpeaker() {
  const wrapper = mount(DictationView);
  await flushPromises();
  return wrapper;
}

/** Enregistre puis arrete : etat « extrait pret a valider ». */
async function recordOnce(wrapper) {
  await btn(wrapper, "Enregistrer").trigger("click");
  await flushPromises();
  await btn(wrapper, "Arrêter").trigger("click");
  await flushPromises();
}

beforeEach(() => {
  FakeMediaRecorder.instances = [];
  micTrack = { stop: vi.fn() };
  micStream = { getTracks: () => [micTrack] };
  getUserMedia = vi.fn().mockResolvedValue(micStream);

  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    writable: true,
    value: { getUserMedia },
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);

  apiMock.mockImplementation((path) => {
    if (path === "/auth/me") return Promise.resolve({ user: "aya", language: "dyu", roles: [] });
    if (path === "/dictation/progress") {
      return Promise.resolve({ total: 10, recorded: 4, todo: 6 });
    }
    if (path.startsWith("/dictation/prompts")) {
      return Promise.resolve({ prompts: PROMPTS.map((p) => ({ ...p })) });
    }
    if (path.endsWith("/audio")) return Promise.resolve({ ok: true });
    return Promise.reject(new Error("appel API inattendu : " + path));
  });
});

afterEach(() => {
  delete navigator.mediaDevices;
});

describe("DictationView — demarrage de l'enregistrement", () => {
  it("demande le micro, lance MediaRecorder et bascule l'UI en mode enregistrement", async () => {
    const w = await mountSpeaker();
    expect(w.text()).toContain("Aw ye malo sɛnɛ");

    await btn(w, "Enregistrer").trigger("click");
    await flushPromises();

    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(FakeMediaRecorder.instances).toHaveLength(1);

    const rec = FakeMediaRecorder.instances[0];
    expect(rec.stream).toBe(micStream);
    expect(rec.state).toBe("recording");

    expect(hasBtn(w, "Arrêter")).toBe(true);
    expect(hasBtn(w, "Enregistrer")).toBe(false);
  });

  it("n'ouvre qu'un seul flux micro malgre un double-clic pendant getUserMedia", async () => {
    let release;
    getUserMedia.mockImplementation(() => new Promise((resolve) => (release = resolve)));
    const w = await mountSpeaker();
    const b = btn(w, "Enregistrer");

    await Promise.all([b.trigger("click"), b.trigger("click")]);

    expect(getUserMedia).toHaveBeenCalledTimes(1);

    release(micStream);
    await flushPromises();
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });
});

describe("DictationView — refus de permission micro", () => {
  it("affiche une consigne et ne demarre aucun enregistrement", async () => {
    getUserMedia.mockRejectedValue(new DOMException("Permission denied", "NotAllowedError"));
    const w = await mountSpeaker();

    await btn(w, "Enregistrer").trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Micro non autorisé");
    expect(FakeMediaRecorder.instances).toHaveLength(0);
    expect(w.find("audio").exists()).toBe(false);
  });

  it("laisse l'utilisateur reessayer apres avoir autorise le micro", async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException("Permission denied", "NotAllowedError"));
    const w = await mountSpeaker();

    await btn(w, "Enregistrer").trigger("click");
    await flushPromises();
    expect(hasBtn(w, "Enregistrer")).toBe(true);

    await btn(w, "Enregistrer").trigger("click");
    await flushPromises();

    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(FakeMediaRecorder.instances).toHaveLength(1);
    expect(hasBtn(w, "Arrêter")).toBe(true);
  });
});

describe("DictationView — arret de l'enregistrement", () => {
  it("relache le micro et propose l'extrait a la relecture", async () => {
    const w = await mountSpeaker();

    await recordOnce(w);

    expect(FakeMediaRecorder.instances[0].state).toBe("inactive");
    expect(micTrack.stop).toHaveBeenCalledTimes(1); // sans ca le voyant micro reste allume

    const audioEl = w.find("audio");
    expect(audioEl.exists()).toBe(true);
    expect(audioEl.attributes("src")).toMatch(/^blob:/);
    expect(hasBtn(w, "Arrêter")).toBe(false);
    expect(btn(w, "Valider & suivante").attributes("disabled")).toBeUndefined();
  });

  it("« Refaire » revoque l'Object URL et rearme l'enregistrement", async () => {
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    const w = await mountSpeaker();
    await recordOnce(w);
    const url = w.find("audio").attributes("src");

    await btn(w, "Refaire").trigger("click");
    await nextTick();

    expect(revoke).toHaveBeenCalledWith(url); // sinon le blob fuit en memoire
    expect(w.find("audio").exists()).toBe(false);
    expect(hasBtn(w, "Enregistrer")).toBe(true);
  });
});

describe("DictationView — envoi de l'extrait", () => {
  it("poste l'audio de la phrase courante et avance dans la file", async () => {
    const w = await mountSpeaker();
    await recordOnce(w);

    await btn(w, "Valider & suivante").trigger("click");
    await flushPromises();

    const call = apiMock.mock.calls.find(([path]) => path === "/dictation/11/audio");
    expect(call, "aucun POST sur la phrase courante").toBeTruthy();
    expect(call[1].method).toBe("POST");
    expect(call[1].body).toBeInstanceOf(FormData);

    const file = call[1].body.get("audio");
    expect(file).toBeInstanceOf(Blob);
    expect(file.name).toBe("dictee.webm");

    expect(w.text()).toContain("Enregistré ✓");
    expect(w.text()).toContain("5 / 10"); // progression incrementee
    expect(w.text()).toContain("Aw ye foro labɛn"); // phrase suivante
    expect(w.find("audio").exists()).toBe(false);
  });

  it("nomme le fichier en .ogg quand le navigateur enregistre en ogg", async () => {
    const w = await mountSpeaker();
    await btn(w, "Enregistrer").trigger("click");
    await flushPromises();
    FakeMediaRecorder.instances[0].mimeType = "audio/ogg;codecs=opus";
    await btn(w, "Arrêter").trigger("click");
    await flushPromises();

    await btn(w, "Valider & suivante").trigger("click");
    await flushPromises();

    const call = apiMock.mock.calls.find(([path]) => path === "/dictation/11/audio");
    expect(call[1].body.get("audio").name).toBe("dictee.ogg");
  });

  it("affiche l'erreur API et conserve l'extrait pour un nouvel essai", async () => {
    const w = await mountSpeaker();
    await recordOnce(w);
    apiMock.mockImplementationOnce(() => Promise.reject(new Error("fichier_trop_gros")));

    await btn(w, "Valider & suivante").trigger("click");
    await flushPromises();

    expect(w.text()).toContain("fichier_trop_gros");
    expect(w.find("audio").exists()).toBe(true);
    expect(w.text()).toContain("Aw ye malo sɛnɛ"); // toujours sur la meme phrase
  });
});
