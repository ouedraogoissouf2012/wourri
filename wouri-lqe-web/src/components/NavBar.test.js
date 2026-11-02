// Barre de navigation commune (ADR-0047).
//
// Avant, chaque écran codait sa propre liste : « Atelier » n'avait aucun lien vers
// « Assigner », on y arrivait en tapant l'adresse. Une seule source évite que cela
// recommence.

import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import NavBar from "./NavBar.vue";

const liens = (w) => w.findAll("a").map((a) => a.text());

describe("NavBar", () => {
  it("un locuteur ne voit que ses écrans", () => {
    const w = mount(NavBar, { props: { roles: ["review", "ingest"] } });
    expect(liens(w)).toEqual(["Atelier", "Mes demandes", "Dictée ASR"]);
    expect(w.text()).not.toContain("Comptes");
  });

  it("un admin voit tout, dont « Assigner »", () => {
    const w = mount(NavBar, { props: { roles: ["admin"] } });
    const l = liens(w);
    expect(l).toContain("Assigner");
    expect(l).toContain("Couverture");
    expect(l).toContain("Comptes");
  });

  it("l'écran courant est marqué, sans lien vers lui-même", () => {
    const w = mount(NavBar, { props: { roles: ["admin"], actif: "/assign" } });
    expect(w.find('[data-actif="/assign"]').exists()).toBe(true);
    // on ne propose pas d'aller là où l'on est déjà
    expect(liens(w)).not.toContain("Assigner");
  });

  it("sans rôle, aucun lien", () => {
    expect(liens(mount(NavBar, { props: { roles: [] } }))).toEqual([]);
  });
});
