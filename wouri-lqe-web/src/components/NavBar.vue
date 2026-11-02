<script setup>
// Barre de navigation commune a tous les ecrans de l'atelier.
//
// Avant, chaque vue codait sa propre liste : « Atelier » n'avait aucun lien vers
// « Assigner » ni « Couverture », « Comptes » n'en avait qu'un. On y arrivait en
// tapant l'adresse a la main. Une seule source evite que cela recommence —
// ajouter un ecran = une ligne ici.
const props = defineProps({
  roles: { type: Array, default: () => [] },
  // Chemin de l'ecran courant : il s'affiche sans lien, pour situer l'utilisateur.
  actif: { type: String, default: "" },
});

// Meme regle que dans les vues : « admin » ouvre tout.
const peut = (r) => props.roles.includes("admin") || props.roles.includes(r);

const LIENS = [
  { href: "/", texte: "Atelier", role: "review" },
  { href: "/demandes", texte: "Mes demandes", role: "ingest" },
  { href: "/dictee", texte: "Dictée ASR", role: "ingest" },
  { href: "/dashboard", texte: "Tableau de bord", role: "admin" },
  { href: "/assign", texte: "Assigner", role: "admin" },
  { href: "/coverage", texte: "Couverture", role: "admin" },
  { href: "/admin", texte: "Comptes", role: "admin" },
];
</script>

<template>
  <nav class="text-sm mb-4 flex flex-wrap gap-x-3 gap-y-1" data-nav>
    <template v-for="(l, i) in LIENS" :key="l.href">
      <span v-if="peut(l.role)" class="flex items-center gap-3">
        <span v-if="i > 0" aria-hidden="true" class="text-stone-300">·</span>
        <span v-if="l.href === actif" class="font-semibold text-wouri-700"
              :data-actif="l.href" aria-current="page">{{ l.texte }}</span>
        <a v-else :href="l.href" class="underline">{{ l.texte }}</a>
      </span>
    </template>
  </nav>
</template>
