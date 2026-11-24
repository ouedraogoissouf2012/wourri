<script setup>
// Correction d'une fiche dans « À accepter », voix comprise (ADR-0045, révision du
// 2026-11-24). Sortie de StudioView, qui était au plafond de 300 lignes logiques.
//
// Le texte part d'abord, la voix ensuite : le serveur attache la voix à la réponse
// TELLE QU'ELLE EST EN BASE au moment de l'envoi, donc à la réponse corrigée.
// Dans cet écran où l'on enregistre sa voix, « Enregistrer » ne désigne que la voix :
// la sauvegarde s'appelle « Valider la correction ».
import { ref } from "vue";
import { api } from "../api.js";
import { useEnregistreur } from "../composables/useEnregistreur.js";
import EnregistreurVoix from "./EnregistreurVoix.vue";

const props = defineProps({
  fiche: { type: Object, required: true },
  audioSrc: { type: String, default: null }, // audio existant de la fiche, déjà résolu
});
const emit = defineEmits(["fini", "annule"]);

const meta = props.fiche.meta || {};
const paire = (props.fiche.kind || "contenu") === "paire_qr"; // une paire se corrige en entier
const local = ref(props.fiche.text_local);
const fr = ref(props.fiche.text_fr);
const repBci = ref(meta.reponse_bci || "");
const repFr = ref(meta.reponse_fr || "");
const erreur = ref("");
const enregistreur = useEnregistreur();

function message(e) {
  return String(e.message || e);
}

async function envoyerVoix() {
  const extrait = enregistreur.extrait.value;
  const fd = new FormData();
  fd.append("audio", extrait.blob, "voix." + (extrait.mime.includes("ogg") ? "ogg" : "webm"));
  await api("/tasks/" + props.fiche.id + "/voix", { method: "POST", body: fd });
}

async function valider() {
  erreur.value = "";
  try {
    await api("/tasks/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: props.fiche.id, text_local: local.value, text_fr: fr.value,
        ...(paire ? { reponse_bci: repBci.value, reponse_fr: repFr.value } : {}),
      }),
    });
  } catch (e) {
    erreur.value = message(e);
    return;
  }
  if (!enregistreur.extrait.value) {
    emit("fini", "Correction validée.");
    return;
  }
  try {
    await envoyerVoix();
  } catch (e) {
    // le texte est sauvé ; on garde l'extrait pour que le locuteur n'ait pas à redire
    erreur.value = "Correction validée, mais ta voix n'est pas partie (" + message(e) + ") : réessaie.";
    return;
  }
  emit("fini", "Correction validée, avec ta voix.");
}
</script>

<template>
  <div>
    <label class="block text-xs text-stone-500">{{ paire ? "Question (langue locale)" : "Texte (langue locale)" }}</label>
    <input v-model="local" class="w-full border rounded p-1 mb-2 font-semibold" />
    <label class="block text-xs text-stone-500">{{ paire ? "Question en français" : "Traduction française" }}</label>
    <input v-model="fr" class="w-full border rounded p-1 text-stone-600" />
    <template v-if="paire">
      <label class="block text-xs text-stone-500 mt-2">Réponse (langue locale)</label>
      <textarea v-model="repBci" data-champ="reponse_bci" class="w-full border rounded p-1 mb-2 font-semibold" rows="3" />
      <label class="block text-xs text-stone-500">Réponse en français</label>
      <textarea v-model="repFr" data-champ="reponse_fr" class="w-full border rounded p-1 text-stone-600" rows="2" />
      <p class="text-xs text-stone-500 mt-2">Tu as changé la réponse ? Redis-la : elle sera servie avec ta voix. Sinon, elle partira en texte seul.</p>
      <EnregistreurVoix :enregistreur="enregistreur" libelle="🎙️ Redire la réponse"
        @demarrage="erreur = ''" @refus="(m) => (erreur = m)" />
    </template>
    <audio v-if="audioSrc" :src="audioSrc" crossorigin="use-credentials" controls class="mt-2 h-8"></audio>
    <p v-if="erreur" class="mt-2 text-red-700 text-sm" data-erreur>{{ erreur }}</p>
    <div class="mt-2">
      <button class="mr-2 bg-wouri-700 text-white px-2 py-1 rounded" type="button" @click="valider">Valider la correction</button>
      <button class="border px-2 py-1" type="button" @click="emit('annule')">Annuler</button>
    </div>
  </div>
</template>
