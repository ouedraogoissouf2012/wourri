<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const langs = ref([]);
const lang = ref("");
const concepts = ref([]);
const selected = ref(new Set());
const loading = ref(false);
const msg = ref("");
const err = ref("");

onMounted(async () => {
  try {
    const me = await api("/auth/me");
    if (!(me.roles || []).includes("admin")) {
      router.push("/");
      return;
    }
    const d = await api("/coverage");
    langs.value = d.languages || [];
    if (langs.value.length) {
      lang.value = langs.value[0].code;
      await loadMissing();
    }
  } catch (e) {
    if (e.status !== 401) err.value = String(e.message || e);
  }
});

const currentLang = computed(() => langs.value.find((l) => l.code === lang.value) || null);

async function loadMissing() {
  err.value = "";
  msg.value = "";
  selected.value = new Set();
  concepts.value = [];
  if (!lang.value) return;
  loading.value = true;
  try {
    const d = await api("/assignments/missing?language=" + encodeURIComponent(lang.value));
    concepts.value = d.concepts || [];
  } catch (e) {
    err.value = String(e.message || e);
  } finally {
    loading.value = false;
  }
}

function toggle(cid) {
  const s = new Set(selected.value);
  s.has(cid) ? s.delete(cid) : s.add(cid);
  selected.value = s;
}
function selectAll() {
  selected.value = new Set(concepts.value.map((c) => c.concept_id));
}
function clearAll() {
  selected.value = new Set();
}

async function assign() {
  err.value = "";
  msg.value = "";
  const ids = [...selected.value];
  if (!ids.length) {
    err.value = "Sélectionne au moins un concept.";
    return;
  }
  try {
    const r = await api("/assignments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_language: lang.value, concept_ids: ids }),
    });
    msg.value = `Assignés: ${r.assigned} · déjà: ${r.already} · ignorés: ${r.skipped.length}`;
    await loadMissing();
  } catch (e) {
    err.value = String(e.message || e);
  }
}
</script>
<template>
  <div class="max-w-3xl mx-auto p-6">
    <p class="text-sm mb-4">
      <a href="/" class="underline">← Atelier</a> ·
      <a href="/coverage" class="underline">Couverture</a> ·
      <a href="/admin" class="underline">Comptes</a>
    </p>
    <h1 class="text-xl font-semibold text-wouri-700">Assigner des concepts</h1>
    <p class="text-sm text-stone-600">
      Choisis une langue, coche les concepts manquants à faire produire, envoie le lot.
    </p>
    <p v-if="err" class="text-red-700 text-sm mt-2">{{ err }}</p>
    <p v-if="msg" class="text-green-800 text-sm mt-2">{{ msg }}</p>

    <div class="mt-4 flex items-center gap-3">
      <label class="text-sm">Langue cible</label>
      <select v-model="lang" class="border rounded p-1 text-sm" @change="loadMissing">
        <option v-for="l in langs" :key="l.code" :value="l.code">
          {{ l.name }} ({{ l.code }}) — {{ l.covered }}/{{ l.total }} {{ l.up_to_date ? "✅" : "" }}
        </option>
      </select>
      <span v-if="currentLang" class="text-sm text-stone-600">{{ currentLang.missing }} manquant(s)</span>
    </div>

    <div v-if="concepts.length" class="mt-3 text-sm space-x-3">
      <button type="button" class="underline" @click="selectAll">Tout cocher</button>
      <button type="button" class="underline" @click="clearAll">Tout décocher</button>
      <span class="text-stone-600">{{ selected.size }} sélectionné(s)</span>
    </div>

    <div class="mt-3 space-y-2">
      <label v-for="c in concepts" :key="c.concept_id"
        class="flex items-start gap-2 border rounded p-3 bg-white cursor-pointer">
        <input type="checkbox" class="mt-1" :checked="selected.has(c.concept_id)"
          @change="toggle(c.concept_id)" />
        <span>
          <span class="font-medium">{{ c.source_fr }}</span>
          <span class="block text-xs text-stone-500">
            <code>{{ c.concept_id }}</code>
            <template v-if="c.ref_dyu"> · réf. dioula : {{ c.ref_dyu }}</template>
          </span>
        </span>
      </label>
      <p v-if="loading" class="text-stone-500 text-sm">Chargement…</p>
      <p v-else-if="!concepts.length" class="text-stone-500 text-sm">
        Aucun concept à assigner (langue à jour ou tout déjà assigné).
      </p>
    </div>

    <button v-if="concepts.length" type="button"
      class="mt-4 bg-wouri-700 text-white px-3 py-1 rounded" @click="assign">
      Assigner {{ selected.size }} concept(s) à {{ lang }}
    </button>
  </div>
</template>
