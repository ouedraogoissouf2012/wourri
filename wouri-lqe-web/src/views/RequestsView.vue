<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const me = ref({ user: "", language: "", roles: [] });
const items = ref([]);
const drafts = ref({});          // concept_id -> texte optionnel
const audios = ref({});          // concept_id -> { blob, url, mime }
const recordingFor = ref(null);  // concept_id en cours d'enregistrement
const msg = ref("");
const err = ref("");
let recorder = null;
let stream = null;

async function load() {
  const d = await api("/assignments");
  items.value = d.assignments || [];
}

onMounted(async () => {
  try {
    me.value = await api("/auth/me");
    await load();
  } catch (e) {
    if (e.status !== 401) err.value = String(e.message || e);
  }
});

async function startRec(cid) {
  err.value = "";
  msg.value = "";
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    err.value = "Micro non autorisé — autorise l'accès au micro dans le navigateur.";
    return;
  }
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data);
  };
  recorder.onstop = () => {
    const mime = (recorder && recorder.mimeType) || "audio/webm";
    const blob = new Blob(chunks, { type: mime });
    audios.value = { ...audios.value, [cid]: { blob, url: URL.createObjectURL(blob), mime } };
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  };
  recorder.start();
  recordingFor.value = cid;
}

function stopRec() {
  if (recorder && recorder.state !== "inactive") recorder.stop();
  recordingFor.value = null;
}

function redo(cid) {
  const a = { ...audios.value };
  delete a[cid];
  audios.value = a;
}

async function produce(a) {
  err.value = "";
  msg.value = "";
  const rec = audios.value[a.concept_id];
  if (!rec) {
    err.value = "Enregistre d'abord ta voix (bouton 🎙️).";
    return;
  }
  const ext = rec.mime.includes("ogg") ? "ogg" : "webm";
  const fd = new FormData();
  fd.append("concept_id", a.concept_id);
  fd.append("text_fr", a.source_fr);
  fd.append("text_local", (drafts.value[a.concept_id] || "").trim());
  fd.append("audio", rec.blob, "reponse." + ext);
  try {
    const r = await api("/ingest/audio", { method: "POST", body: fd });
    msg.value = r.duplicate
      ? "Déjà enregistré pour ce concept."
      : "Envoyé ✓ — en attente d'acceptation.";
    redo(a.concept_id);
    drafts.value[a.concept_id] = "";
    await load();
  } catch (e) {
    err.value = String(e.message || e);
  }
}
</script>
<template>
  <div class="max-w-3xl mx-auto p-6">
    <header class="flex justify-between items-start gap-4">
      <div>
        <h1 class="text-xl font-semibold text-wouri-700">Mes demandes</h1>
        <p class="text-sm text-stone-600">{{ me.user }} · langue <code>{{ me.language }}</code></p>
      </div>
      <a href="/" class="underline text-sm">← Atelier</a>
    </header>
    <p class="text-sm text-stone-600 mt-2">
      Pour chaque demande : lis la consigne (français), puis <strong>enregistre ta voix</strong> dans ta langue.
      Le texte est facultatif.
    </p>
    <p v-if="msg" class="mt-3 text-green-800 text-sm">{{ msg }}</p>
    <p v-if="err" class="mt-3 text-red-700 text-sm">{{ err }}</p>

    <div class="mt-4 space-y-3">
      <article v-for="a in items" :key="a.concept_id" class="border rounded p-3 bg-white">
        <p class="font-medium">{{ a.source_fr }}</p>
        <p class="text-xs text-stone-500"><code>{{ a.concept_id }}</code></p>

        <input v-model="drafts[a.concept_id]" type="text"
          :placeholder="'Texte en ' + me.language + ' (facultatif)'"
          class="mt-2 w-full border rounded p-2 text-sm" />

        <div class="mt-2 flex items-center gap-2 flex-wrap">
          <button v-if="recordingFor !== a.concept_id && !audios[a.concept_id]" type="button"
            class="border px-3 py-1 rounded" @click="startRec(a.concept_id)">🎙️ Enregistrer</button>
          <button v-if="recordingFor === a.concept_id" type="button"
            class="border px-3 py-1 rounded bg-red-600 text-white" @click="stopRec">⏹️ Arrêter</button>
          <template v-if="audios[a.concept_id]">
            <audio :src="audios[a.concept_id].url" controls class="h-8"></audio>
            <button type="button" class="underline text-sm" @click="redo(a.concept_id)">Refaire</button>
          </template>
        </div>

        <button type="button" class="mt-2 bg-wouri-700 text-white px-3 py-1 rounded disabled:opacity-50"
          :disabled="recordingFor === a.concept_id || !audios[a.concept_id]"
          @click="produce(a)">Produire</button>
      </article>
      <p v-if="!items.length" class="text-stone-500 text-sm">Aucune demande ouverte.</p>
    </div>
  </div>
</template>
