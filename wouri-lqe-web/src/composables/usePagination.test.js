// Decoupage d'une liste en pages (atelier et assignation).
//
// Ce qui casse en silence ici : rester sur une page devenue vide apres qu'une
// fiche a ete traitee ou qu'un filtre a reduit la liste, et croire qu'il n'y a
// plus rien a faire. Voir src/composables/usePagination.js.

import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { TAILLE_PAGE, usePagination } from "./usePagination.js";

const liste = (n) => Array.from({ length: n }, (_, i) => ({ id: i + 1 }));

describe("usePagination", () => {
  it("affiche la premiere page et compte les pages", () => {
    const src = ref(liste(45));
    const p = usePagination(src, 20);

    expect(p.page.value).toBe(1);
    expect(p.pages.value).toBe(3);
    expect(p.total.value).toBe(45);
    expect(p.tranche.value).toHaveLength(20);
    expect(p.tranche.value[0].id).toBe(1);
    expect(p.premier.value).toBe(1);
    expect(p.dernier.value).toBe(20);
  });

  it("donne la bonne tranche sur une page intermediaire", () => {
    const p = usePagination(ref(liste(45)), 20);

    p.allerA(2);

    expect(p.tranche.value[0].id).toBe(21);
    expect(p.tranche.value).toHaveLength(20);
    expect(p.premier.value).toBe(21);
    expect(p.dernier.value).toBe(40);
  });

  it("la derniere page n'est pas complete et le dit", () => {
    const p = usePagination(ref(liste(45)), 20);

    p.allerA(3);

    expect(p.tranche.value).toHaveLength(5);
    expect(p.premier.value).toBe(41);
    expect(p.dernier.value).toBe(45);
  });

  it("borne la page demandee au lieu de sortir de la liste", () => {
    const p = usePagination(ref(liste(45)), 20);

    p.allerA(99);
    expect(p.page.value).toBe(3);

    p.allerA(0);
    expect(p.page.value).toBe(1);

    p.allerA(-5);
    expect(p.page.value).toBe(1);
  });

  it("ramene sur la derniere page quand la liste retrecit", async () => {
    // Le cas reel : le locuteur est page 3, traite des fiches, la liste tombe a 10.
    const src = ref(liste(45));
    const p = usePagination(src, 20);
    p.allerA(3);

    src.value = liste(10);
    await nextTick();

    expect(p.page.value).toBe(1);
    expect(p.tranche.value).toHaveLength(10);
  });

  it("ne bouge pas la page quand la liste reste assez longue", async () => {
    const src = ref(liste(45));
    const p = usePagination(src, 20);
    p.allerA(2);

    src.value = liste(44);
    await nextTick();

    expect(p.page.value).toBe(2);
  });

  it("une liste vide reste coherente", () => {
    const p = usePagination(ref([]), 20);

    expect(p.pages.value).toBe(1);
    expect(p.total.value).toBe(0);
    expect(p.tranche.value).toEqual([]);
    expect(p.premier.value).toBe(0);
    expect(p.dernier.value).toBe(0);
  });

  it("une source absente ne fait pas planter", () => {
    const p = usePagination(ref(null), 20);

    expect(p.total.value).toBe(0);
    expect(p.tranche.value).toEqual([]);
  });

  it("reinitialiser ramene a la page 1", () => {
    const p = usePagination(ref(liste(100)), 20);
    p.allerA(4);

    p.reinitialiser();

    expect(p.page.value).toBe(1);
  });

  it("la taille par defaut est celle du module", () => {
    const p = usePagination(ref(liste(TAILLE_PAGE + 1)));

    expect(p.pages.value).toBe(2);
    expect(p.tranche.value).toHaveLength(TAILLE_PAGE);
  });
});
