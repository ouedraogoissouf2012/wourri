<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const me = ref({ user: "", language: "", roles: [] });
const items = ref([]);
const drafts = ref({});
const msg = ref("");
const err = ref("");

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

async function produce(a) {
  err.value = "";
  msg.value = "";
  const text = (drafts.value[a.concept_id] || "").trim();
  if (!text) {
    err.value = "Saisis l'équivalent dans ta langue.";
    return;
  }
  try {
    const r = await api("/ingest/json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify([{ text_local: text, text_fr: a.source_fr, concept_id: a.concept_id }]),
    });
    msg.value = `Envoyé en Bronze (${r.accepted}). Visible dans la couverture après promotion.`;
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
      Concepts à produire dans ta langue. La consigne est en français ; la référence dioula est indicative.
    </p>
    <p v-if="msg" class="mt-3 text-green-800 text-sm">{{ msg }}</p>
    <p v-if="err" class="mt-3 text-red-700 text-sm">{{ err }}</p>

    <div class="mt-4 space-y-3">
      <article v-for="a in items" :key="a.concept_id" class="border rounded p-3 bg-white">
        <p class="font-medium">{{ a.source_fr }}</p>
        <p class="text-xs text-stone-500"><code>{{ a.concept_id }}</code></p>
        <input v-model="drafts[a.concept_id]" type="text"
          :placeholder="'Équivalent en ' + me.language"
          class="mt-2 w-full border rounded p-2 text-sm" />
        <button type="button" class="mt-2 bg-wouri-700 text-white px-3 py-1 rounded" @click="produce(a)">
          Produire
        </button>
      </article>
      <p v-if="!items.length" class="text-stone-500 text-sm">Aucune demande ouverte.</p>
    </div>
  </div>
</template>
