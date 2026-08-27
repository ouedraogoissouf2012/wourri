// Tests de la gestion des comptes locuteurs (dette #492).
//
// L'issue #492 situe « l'assignation par lot » dans AdminView ; elle vit en fait dans
// AssignView (cf. AssignView.test.js). AdminView gere les comptes — ce qui casse en
// silence ici : le garde admin (un non-admin verrait la gestion des comptes), les
// roles coches qui ne suivent pas jusqu'au POST, et les noms d'utilisateur non
// encodes dans l'URL. Voir src/views/AdminView.vue.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import AdminView from "./AdminView.vue";

const { apiMock, push } = vi.hoisted(() => ({ apiMock: vi.fn(), push: vi.fn() }));
vi.mock("../api.js", () => ({ api: apiMock }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));

const ROLES = ["ingest", "review", "promote", "admin"];
const LANGS = ["dyu", "bci"];
// Un nom avec espace et accent : il doit survivre a l'encodage de l'URL.
const ACCOUNTS = [
  { user: "aya", language: "dyu", roles: ["ingest", "review"], active: true },
  { user: "kouamé n'da", language: "bci", roles: ["ingest"], active: false },
];

const ADMIN = { user: "admin", language: "*", roles: ["admin"] };

function useApi({ me = ADMIN } = {}) {
  apiMock.mockImplementation((path, opt) => {
    if (path === "/auth/me") {
      return me instanceof Error ? Promise.reject(me) : Promise.resolve(me);
    }
    if (path === "/accounts" && !opt) {
      return Promise.resolve({
        accounts: ACCOUNTS.map((a) => ({ ...a })),
        languages: [...LANGS],
        roles: [...ROLES],
      });
    }
    if (path === "/accounts" && opt && opt.method === "POST") return Promise.resolve({ ok: true });
    if (path.startsWith("/accounts/") && opt && opt.method === "PATCH") {
      return Promise.resolve({ ok: true });
    }
    return Promise.reject(new Error("appel API inattendu : " + path));
  });
}

async function mountAdmin() {
  const wrapper = mount(AdminView);
  await flushPromises();
  return wrapper;
}

function btn(wrapper, label) {
  const all = wrapper.findAll("button");
  const found = all.find((b) => b.text().includes(label));
  if (!found) {
    const presents = all.map((b) => b.text()).join(" | ");
    throw new Error('bouton "' + label + '" absent — presents : ' + presents);
  }
  return found;
}

/** Case a cocher d'un role du formulaire de creation, retrouvee par son libelle. */
function roleBox(wrapper, role) {
  const label = wrapper.findAll("label").find((l) => l.text().trim() === role);
  if (!label) throw new Error('role "' + role + '" absent du formulaire');
  return label.find('input[type="checkbox"]');
}

function callsTo(path, method) {
  return apiMock.mock.calls.filter(([p, o]) => p === path && (o ? o.method : undefined) === method);
}

beforeEach(() => {
  useApi();
});

describe("AdminView — garde admin", () => {
  it("liste les comptes pour un admin", async () => {
    const w = await mountAdmin();

    expect(push).not.toHaveBeenCalled();
    expect(w.text()).toContain("aya");
    expect(w.text()).toContain("ingest, review");
    expect(w.text()).toContain("kouamé n'da");
    expect(w.text()).toContain("(inactif)");
  });

  it("renvoie un non-admin vers l'atelier sans charger les comptes", async () => {
    useApi({ me: { user: "aya", language: "dyu", roles: ["ingest", "review"] } });

    const w = await mountAdmin();

    expect(push).toHaveBeenCalledWith("/");
    expect(callsTo("/accounts", undefined)).toHaveLength(0);
    expect(w.text()).not.toContain("aya");
  });

  it("renvoie vers /login quand la session est invalide", async () => {
    useApi({ me: new Error("session") });

    await mountAdmin();

    expect(push).toHaveBeenCalledWith("/login");
  });
});

describe("AdminView — creation de compte", () => {
  it("poste les roles reellement coches et recharge la liste", async () => {
    const w = await mountAdmin();

    await w.find('input[placeholder="utilisateur"]').setValue("fanta");
    await w.find('input[type="password"]').setValue("motdepasse8");
    await roleBox(w, "promote").setValue(true); // s'ajoute au "review" par defaut

    await w.find("form").trigger("submit");
    await flushPromises();

    const post = callsTo("/accounts", "POST");
    expect(post).toHaveLength(1);
    expect(JSON.parse(post[0][1].body)).toEqual({
      user: "fanta",
      password: "motdepasse8",
      language: "dyu", // premiere langue disponible, prise au chargement
      roles: ["review", "promote"],
    });

    expect(w.text()).toContain("Compte créé");
    expect(callsTo("/accounts", undefined)).toHaveLength(2); // liste rechargee
    expect(w.find('input[placeholder="utilisateur"]').element.value).toBe("");
  });

  it("retire un role deja coche au lieu de l'envoyer deux fois", async () => {
    const w = await mountAdmin();

    await w.find('input[placeholder="utilisateur"]').setValue("fanta");
    await w.find('input[type="password"]').setValue("motdepasse8");
    await roleBox(w, "review").setValue(false); // decoche le role par defaut
    await roleBox(w, "ingest").setValue(true);

    await w.find("form").trigger("submit");
    await flushPromises();

    expect(JSON.parse(callsTo("/accounts", "POST")[0][1].body).roles).toEqual(["ingest"]);
  });

  it("affiche l'erreur de l'API sans recharger la liste", async () => {
    const w = await mountAdmin();
    await w.find('input[placeholder="utilisateur"]').setValue("fanta");
    await w.find('input[type="password"]').setValue("motdepasse8");
    apiMock.mockImplementationOnce(() => Promise.reject(new Error("utilisateur_existe")));

    await w.find("form").trigger("submit");
    await flushPromises();

    expect(w.text()).toContain("utilisateur_existe");
    expect(callsTo("/accounts", undefined)).toHaveLength(1);
  });
});

describe("AdminView — activation d'un compte", () => {
  it("encode le nom d'utilisateur dans l'URL du PATCH", async () => {
    const w = await mountAdmin();

    // deuxieme compte de la liste : "kouamé n'da", inactif
    const activer = w.findAll("button").filter((b) => b.text() === "Activer");
    expect(activer).toHaveLength(1);
    await activer[0].trigger("click");
    await flushPromises();

    const patch = apiMock.mock.calls.find(([, o]) => o && o.method === "PATCH");
    expect(patch, "aucun PATCH emis").toBeTruthy();
    expect(patch[0]).toBe("/accounts/" + encodeURIComponent("kouamé n'da"));
    expect(JSON.parse(patch[1].body)).toEqual({ active: true });
    expect(callsTo("/accounts", undefined)).toHaveLength(2); // liste rechargee
  });

  it("desactive un compte actif", async () => {
    const w = await mountAdmin();

    await btn(w, "Désactiver").trigger("click");
    await flushPromises();

    const patch = apiMock.mock.calls.find(([, o]) => o && o.method === "PATCH");
    expect(patch[0]).toBe("/accounts/aya");
    expect(JSON.parse(patch[1].body)).toEqual({ active: false });
  });
});
