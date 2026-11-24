// Caracterisation de DictationView AVANT l'extraction de l'enregistreur (ADR-0045,
// revision du 2026-11-24).
//
// Ce test fige le HTML complet de l'ecran du locuteur dans six etats du cycle
// d'enregistrement. Il est ecrit et vert sur le code d'AVANT l'extraction ; le code
// d'APRES doit produire exactement le meme HTML. Son fichier d'instantanes
// (__snapshots__/DictationView.caracterisation.test.js.snap) ne doit donc JAMAIS
// changer dans la PR d'extraction : un `git diff` vide sur ce fichier est la preuve
// que l'ecran se comporte comme avant.

import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import DictationView from "./DictationView.vue";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));

// Phrases reprises du corpus reel (dictionnaires/corpus_ivr.json) : aucun dioula invente.
const PROMPTS = [
  { id: 11, filiere: "riz", text_local: "Aw ye malo sɛnɛ", text_fr: "Plantez le riz" },
  { id: 12, filiere: "riz", text_local: "Aw ye foro labɛn", text_fr: "Preparez le champ" },
];

class FakeMediaRecorder {
  constructor(stream) {
    this.stream = stream;
    this.state = "inactive";
    this.mimeType = "audio/webm;codecs=opus";
    this.ondataavailable = null;
    this.onstop = null;
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

let getUserMedia;

function bouton(wrapper, libelle) {
  const trouve = wrapper.findAll("button").find((b) => b.text().includes(libelle));
  if (!trouve) throw new Error('bouton "' + libelle + '" absent');
  return trouve;
}

async function cliquer(wrapper, libelle) {
  await bouton(wrapper, libelle).trigger("click");
  await flushPromises();
}

async function monter() {
  const wrapper = mount(DictationView);
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  const piste = { stop: vi.fn() };
  getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [piste] });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    writable: true,
    value: { getUserMedia },
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  // URL d'extrait fixe : l'instantane ne doit pas dependre d'un identifiant aleatoire.
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:extrait-fixe");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

  apiMock.mockImplementation((path) => {
    if (path === "/auth/me") return Promise.resolve({ user: "aya", language: "dyu", roles: [] });
    if (path === "/dictation/progress") return Promise.resolve({ total: 10, recorded: 4, todo: 6 });
    if (path.startsWith("/dictation/prompts")) return Promise.resolve({ prompts: PROMPTS.map((p) => ({ ...p })) });
    if (path.endsWith("/audio")) return Promise.resolve({ ok: true });
    return Promise.reject(new Error("appel API inattendu : " + path));
  });
});

afterEach(() => {
  delete navigator.mediaDevices;
  vi.restoreAllMocks();
});

describe("DictationView — caracterisation du cycle d'enregistrement", () => {
  it("1. au repos", async () => {
    const w = await monter();
    expect(w.html()).toMatchSnapshot();
  });

  it("2. enregistrement en cours", async () => {
    const w = await monter();
    await cliquer(w, "Enregistrer");
    expect(w.html()).toMatchSnapshot();
  });

  it("3. extrait pret a valider", async () => {
    const w = await monter();
    await cliquer(w, "Enregistrer");
    await cliquer(w, "Arrêter");
    expect(w.html()).toMatchSnapshot();
  });

  it("4. micro refuse", async () => {
    getUserMedia.mockRejectedValue(new DOMException("Permission denied", "NotAllowedError"));
    const w = await monter();
    await cliquer(w, "Enregistrer");
    expect(w.html()).toMatchSnapshot();
  });

  it("5. apres « Refaire »", async () => {
    const w = await monter();
    await cliquer(w, "Enregistrer");
    await cliquer(w, "Arrêter");
    await cliquer(w, "Refaire");
    expect(w.html()).toMatchSnapshot();
  });

  it("6. apres l'envoi de l'extrait", async () => {
    const w = await monter();
    await cliquer(w, "Enregistrer");
    await cliquer(w, "Arrêter");
    await cliquer(w, "Valider");
    expect(w.html()).toMatchSnapshot();
  });
});
