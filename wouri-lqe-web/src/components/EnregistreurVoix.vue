<script setup>
// Presentation de l'enregistreur partage (ADR-0045, revision du 2026-11-24) : le cycle
// vit dans useEnregistreur, l'ecran parent garde ce qui lui est propre (envoi, messages).
// La racine reprend a l'identique le bloc de DictationView : meme HTML qu'avant
// l'extraction (DictationView.caracterisation.test.js).

const props = defineProps({
  enregistreur: { type: Object, required: true },
  libelle: { type: String, default: "🎙️ Enregistrer" },
});
const emit = defineEmits(["demarrage", "refus"]);

const { enCours, extrait } = props.enregistreur;

async function lancer() {
  emit("demarrage");
  const resultat = await props.enregistreur.demarrer();
  if (resultat.erreur) emit("refus", resultat.erreur);
}
</script>

<template>
  <div class="mt-4 flex items-center gap-2 flex-wrap">
    <button v-if="!enCours && !extrait" type="button"
      class="border px-3 py-1 rounded" @click="lancer">{{ libelle }}</button>
    <button v-if="enCours" type="button"
      class="border px-3 py-1 rounded bg-red-600 text-white" @click="enregistreur.arreter">⏹️ Arrêter</button>
    <template v-if="extrait">
      <audio :src="extrait.url" controls class="h-8"></audio>
      <button type="button" class="underline text-sm" @click="enregistreur.effacer">Refaire</button>
    </template>
  </div>
</template>
