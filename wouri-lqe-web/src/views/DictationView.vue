<script setup>
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import EnregistreurVoix from "../components/EnregistreurVoix.vue";
import { useEnregistreur } from "../composables/useEnregistreur.js";

// Front (lqe.*) et API (lqe-api.*) sur des origines distinctes : l'export (binaire) passe
// par fetch credentials + Blob (le helper api() ne gère que du JSON).
const API_BASE = import.meta.env.VITE_API_BASE || "";

const me = ref({ user: "", language: "", roles: [] });
const isAdmin = computed(() => (me.value.roles || []).includes("admin"));
const isSpeaker = computed(() => me.value.language && me.value.language !== "*");

const msg = ref("");
const err = ref("");

// ----- locuteur : file de dictée -----
const queue = ref([]); // phrases à lire (status todo)
const idx = ref(0);
const prog = ref({ total: 0, recorded: 0, todo: 0 });
// Enregistreur partagé avec la fiche de relecture (ADR-0045, révision du 2026-11-24).
const enregistreur = useEnregistreur();
const audio = enregistreur.extrait; // { blob, url, mime }
const recording = enregistreur.enCours;
const clearAudio = enregistreur.effacer;

const current = computed(() => queue.value[idx.value] || null);
const donePct = computed(() =>
  prog.value.total ? Math.round((prog.value.recorded / prog.value.total) * 100) : 0
);

// ----- admin : import / stats / export -----
const langs = ref([]); // [{code, name}]
const adminLang = ref("");
const adminStats = ref(null);
const importInfo = ref("");

async function loadSpeaker() {
  prog.value = await api("/dictation/progress");
  const d = await api("/dictation/prompts?status=todo");
  queue.value = d.prompts || [];
  idx.value = 0;
  clearAudio();
}

async function loadAdmin() {
  const c = await api("/coverage");
  langs.value = (c.languages || []).map((l) => ({ code: l.code, name: l.name }));
  if (!adminLang.value && langs.value.length) adminLang.value = langs.value[0].code;
  await refreshStats();
}

async function refreshStats() {
  if (!adminLang.value) return;
  try {
    adminStats.value = await api("/dictation/stats?language=" + adminLang.value);
  } catch (e) {
    adminStats.value = null;
    err.value = String(e.message || e);
  }
}

onMounted(async () => {
  try {
    me.value = await api("/auth/me");
    if (isAdmin.value) await loadAdmin();
    else if (isSpeaker.value) await loadSpeaker();
  } catch (e) {
    if (e.status !== 401) err.value = String(e.message || e);
  }
});

// --- enregistrement : le cycle vit dans useEnregistreur, l'écran garde ses messages ---
function onDemarrage() {
  err.value = "";
  msg.value = "";
}

function onRefus(message) {
  err.value = message;
}

function skip() {
  if (idx.value < queue.value.length - 1) idx.value++;
  clearAudio();
  msg.value = "";
}

async function submit() {
  if (!current.value || !audio.value) return;
  const ext = audio.value.mime.includes("ogg") ? "ogg" : "webm";
  const fd = new FormData();
  fd.append("audio", audio.value.blob, "dictee." + ext);
  err.value = "";
  try {
    await api("/dictation/" + current.value.id + "/audio", { method: "POST", body: fd });
    prog.value = {
      ...prog.value,
      recorded: prog.value.recorded + 1,
      todo: Math.max(0, prog.value.todo - 1),
    };
    queue.value.splice(idx.value, 1); // la phrase enregistrée quitte la file
    if (idx.value >= queue.value.length) idx.value = Math.max(0, queue.value.length - 1);
    clearAudio();
    msg.value = "Enregistré ✓";
  } catch (e) {
    err.value = String(e.message || e);
  }
}

// --- admin ---
async function importFile(ev) {
  const f = ev.target.files?.[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("language", adminLang.value);
  fd.append("file", f);
  err.value = "";
  importInfo.value = "";
  try {
    const r = await api("/dictation/import", { method: "POST", body: fd });
    importInfo.value = `Importées : ${r.inserted} · déjà présentes : ${r.skipped}`;
    await refreshStats();
  } catch (e) {
    err.value = String(e.message || e);
  }
  ev.target.value = "";
}

function downloadExport() {
  err.value = "";
  msg.value = "";
  if (!adminLang.value) {
    err.value = "Choisis une langue.";
    return;
  }
  if (adminStats.value && adminStats.value.recorded === 0) {
    err.value = "Aucun audio enregistré pour cette langue.";
    return;
  }
  // Téléchargement DIRECT (streaming) plutôt que fetch->blob : le backend renvoie
  // Content-Disposition: attachment et le cookie de session (SameSite=lax) part
  // sur cette navigation GET top-level. Évite (1) de charger tout le ZIP en
  // mémoire (30+ Mo sur un gros dataset) et (2) le blocage du téléchargement
  // déclenché APRÈS un await (geste utilisateur perdu) — la cause du bug à 217 clips.
  const a = document.createElement("a");
  a.href = API_BASE + "/dictation/export?language=" + adminLang.value;
  document.body.appendChild(a);
  a.click();
  a.remove();
  msg.value = "Téléchargement lancé…";
}
</script>

<template>
  <div class="max-w-3xl mx-auto p-6">
    <header class="flex justify-between items-start gap-4">
      <div>
        <h1 class="text-xl font-semibold text-wouri-700">Dictée ASR</h1>
        <p class="text-sm text-stone-600">
          {{ me.user }} · langue <code>{{ me.language }}</code>
        </p>
      </div>
      <a :href="isAdmin ? '/dashboard' : '/'" class="underline text-sm">← Retour</a>
    </header>

    <p v-if="msg" class="mt-3 text-green-800 text-sm">{{ msg }}</p>
    <p v-if="err" class="mt-3 text-red-700 text-sm">{{ err }}</p>

    <!-- ===================== ADMIN ===================== -->
    <section v-if="isAdmin" class="mt-5 space-y-5">
      <p class="text-sm text-stone-600">
        Importe le lot de phrases à lire, suis la progression du locuteur, puis exporte le
        dataset (ZIP <code>audio/</code> + <code>metadata.csv</code>) prêt pour l'entraînement.
      </p>

      <div class="flex items-center gap-2">
        <label class="text-sm text-stone-600">Langue</label>
        <select v-model="adminLang" class="border rounded p-1 text-sm" @change="refreshStats">
          <option v-for="l in langs" :key="l.code" :value="l.code">{{ l.name }} ({{ l.code }})</option>
        </select>
      </div>

      <div v-if="adminStats" class="border rounded p-3 bg-white text-sm">
        <p>
          Enregistrées : <strong>{{ adminStats.recorded }}</strong> / {{ adminStats.total }}
          · restantes : {{ adminStats.todo }}
        </p>
      </div>

      <div class="border rounded p-3 bg-white space-y-2">
        <p class="text-sm font-medium">1. Importer les phrases (CSV / XLSX / JSON)</p>
        <p class="text-xs text-stone-500">Colonnes : filière, français, {{ adminLang || "langue" }}.</p>
        <input type="file" accept=".csv,.xlsx,.json" @change="importFile" />
        <p v-if="importInfo" class="text-green-800 text-sm">{{ importInfo }}</p>
      </div>

      <div class="border rounded p-3 bg-white space-y-2">
        <p class="text-sm font-medium">2. Exporter le dataset ASR</p>
        <button type="button" class="bg-wouri-700 text-white px-3 py-1 rounded"
          @click="downloadExport">⬇️ Télécharger le ZIP</button>
      </div>
    </section>

    <!-- ===================== LOCUTEUR ===================== -->
    <section v-else-if="isSpeaker" class="mt-5">
      <div class="flex items-center justify-between text-sm text-stone-600">
        <span>Progression : <strong>{{ prog.recorded }}</strong> / {{ prog.total }}</span>
        <span>{{ donePct }}%</span>
      </div>
      <div class="mt-1 h-2 bg-stone-200 rounded overflow-hidden">
        <div class="h-full bg-wouri-700" :style="{ width: donePct + '%' }"></div>
      </div>

      <div v-if="current" class="mt-5 border rounded p-4 bg-white">
        <p v-if="current.filiere" class="inline-block text-xs bg-stone-100 rounded px-2 py-0.5 text-stone-600">
          {{ current.filiere }}
        </p>
        <p class="mt-3 text-lg font-semibold leading-snug">{{ current.text_local }}</p>
        <p v-if="current.text_fr" class="mt-1 text-sm text-stone-500">{{ current.text_fr }}</p>

        <EnregistreurVoix :enregistreur="enregistreur" @demarrage="onDemarrage" @refus="onRefus" />

        <div class="mt-4 flex items-center gap-2">
          <button type="button"
            class="bg-wouri-700 text-white px-3 py-1 rounded disabled:opacity-50"
            :disabled="recording || !audio" @click="submit">Valider & suivante</button>
          <button type="button" class="underline text-sm text-stone-600"
            :disabled="recording" @click="skip">Passer</button>
        </div>
      </div>

      <div v-else class="mt-6 border rounded p-6 bg-white text-center">
        <p class="text-lg">🎉 Terminé</p>
        <p class="text-sm text-stone-600 mt-1">Toutes les phrases disponibles sont enregistrées. Merci !</p>
      </div>
    </section>

    <section v-else class="mt-6 text-sm text-stone-500">
      Ce compte n'a pas de langue de collecte assignée.
    </section>
  </div>
</template>
