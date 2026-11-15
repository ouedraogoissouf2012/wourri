import { computed, ref, watch } from "vue";

/** Nombre d'elements par page. Vingt fiches tiennent dans un ecran sans defilement
 *  interminable, et laissent la barre de pagination visible sans la chercher. */
export const TAILLE_PAGE = 20;

/**
 * Decoupe une liste en pages.
 *
 * `source` est un `ref` ou un `computed` sur un tableau. La tranche affichee suit
 * automatiquement la source : filtrer, recharger ou traiter une fiche met la page
 * a jour sans que l'appelant ait a y penser.
 *
 * Deux garde-fous :
 *  - une liste qui RETRECIT ne laisse jamais l'utilisateur sur une page devenue
 *    vide : il est ramene sur la derniere page existante ;
 *  - `allerA` borne la page demandee, donc aucun appelant ne peut sortir des pages.
 *
 * La remise a la page 1 lors d'un changement de contexte (recherche, onglet, langue)
 * reste a la charge de l'appelant, via `reinitialiser()` : c'est lui qui sait ce qui
 * constitue un nouveau contexte, et un retour automatique a la page 1 a chaque
 * rechargement ferait perdre sa place au locuteur apres chaque fiche traitee.
 */
export function usePagination(source, taille = TAILLE_PAGE) {
  const page = ref(1);

  const total = computed(() => (source.value || []).length);
  const pages = computed(() => Math.max(1, Math.ceil(total.value / taille)));

  watch(pages, (n) => {
    if (page.value > n) page.value = n;
  });

  const debut = computed(() => (page.value - 1) * taille);
  const tranche = computed(() => (source.value || []).slice(debut.value, debut.value + taille));
  const premier = computed(() => (total.value ? debut.value + 1 : 0));
  const dernier = computed(() => Math.min(debut.value + taille, total.value));

  function allerA(n) {
    page.value = Math.min(Math.max(1, Number(n) || 1), pages.value);
  }
  function reinitialiser() {
    page.value = 1;
  }

  return { page, pages, total, tranche, premier, dernier, allerA, reinitialiser };
}
