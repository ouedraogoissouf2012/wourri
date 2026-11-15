<script setup>
// Barre de pagination partagee (atelier et assignation). Elle ne s'affiche pas
// quand tout tient sur une page : une liste de dix fiches n'a pas besoin de
// commandes de navigation.
defineProps({
  page: { type: Number, required: true },
  pages: { type: Number, required: true },
  premier: { type: Number, required: true },
  dernier: { type: Number, required: true },
  total: { type: Number, required: true },
});
defineEmits(["aller"]);
</script>
<template>
  <nav v-if="pages > 1" data-pagination
    class="mt-3 flex flex-wrap items-center gap-3 text-sm text-stone-600">
    <button type="button" data-prec
      class="border rounded px-2 py-1 disabled:opacity-40 disabled:cursor-default"
      :disabled="page <= 1" @click="$emit('aller', page - 1)">Précédent</button>
    <button type="button" data-suiv
      class="border rounded px-2 py-1 disabled:opacity-40 disabled:cursor-default"
      :disabled="page >= pages" @click="$emit('aller', page + 1)">Suivant</button>
    <span data-plage>{{ premier }}–{{ dernier }} sur {{ total }}</span>
    <span class="text-stone-500">page {{ page }} / {{ pages }}</span>
  </nav>
</template>
