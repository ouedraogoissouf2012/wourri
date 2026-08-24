<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const me = ref({ user: "", language: "", roles: [] });
const tab = ref("upload");
const bronze = ref([]);
const accepted = ref([]);
const corpus = ref([]);
const jsonText = ref('[{"text_local":"","text_fr":""}]');
const msg = ref("");
const err = ref("");

const can = (r) => {
  const rs = me.value.roles || [];
  return rs.includes("admin") || rs.includes(r);
};

// En prod, front (lqe.*) et API (lqe-api.*) sont sur des origines distinctes : l'URL
// media doit viser l'API (VITE_API_BASE), pas le front (sinon nginx renvoie index.html).
const API_BASE = import.meta.env.VITE_API_BASE || "";
const mediaSrc = (r) => (r.audio_url ? API_BASE + "/media/" + r.audio_url.split("/").pop() : null);

const tabs = computed(() => {
  const out = [];
  if (can("ingest")) out.push(["upload", "Ajouter"]);
  if (can("review")) out.push(["bronze", "À accepter (" + bronze.value.length + ")"]);
  if (can("promote")) out.push(["accepted", "À promouvoir (" + accepted.value.length + ")"]);
  out.push(["corpus", "Corpus (" + corpus.value.length + ")"]);
  return out;
});

async function refresh() {
  const t = await api("/tasks");
  bronze.value = t.bronze || [];
  accepted.value = t.accepted || [];
  const c = await api("/corpus");
  corpus.value = c.entries || [];
}

onMounted(async () => {
  try {
    me.value = await api("/auth/me");
    if ((me.value.roles || []).includes("admin")) {
      router.push("/dashboard"); // l'admin orchestre, il n'opère pas l'atelier de production
      return;
    }
    if (tabs.value.length && !tabs.value.some((x) => x[0] === tab.value)) {
      tab.value = tabs.value[0][0];
    }
    await refresh();
  } catch {
    router.push("/login");
  }
});

async function logout() {
  await api("/auth/logout", { method: "POST" });
  router.push("/login");
}

async function sendJson() {
  err.value = "";
  try {
    const payload = JSON.parse(jsonText.value);
    const r = await api("/ingest/json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    msg.value = `Nouvelles: ${r.accepted} · doublons: ${r.duplicates_skipped || 0}`;
    await refresh();
  } catch (e) {
    err.value = String(e.message || e);
  }
}

async function sendFile(ev) {
  const f = ev.target.files?.[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  err.value = "";
  try {
    const r = await api("/ingest/file", { method: "POST", body: fd });
    msg.value = `Nouvelles: ${r.accepted} · doublons: ${r.duplicates_skipped || 0} (${f.name})`;
    await refresh();
  } catch (e) {
    err.value = String(e.message || e);
  }
}

async function decide(id, decision) {
  await api("/tasks/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, decision }),
  });
  await refresh();
}

async function promote(id) {
  await api("/corpus/promote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  await refresh();
}
</script>
<template>
  <div class="max-w-3xl mx-auto p-6">
    <header class="flex justify-between items-start gap-4">
      <div>
        <h1 class="text-xl font-semibold text-wouri-700">Atelier langues</h1>
        <p class="text-sm text-stone-600">
          {{ me.user }} · langue <code>{{ me.language }}</code>
        </p>
      </div>
      <div class="text-sm space-x-3">
        <a v-if="can('ingest')" href="/demandes" class="underline">Mes demandes</a>
        <a v-if="can('admin')" href="/admin" class="underline">Comptes</a>
        <button class="underline" type="button" @click="logout">Déconnexion</button>
      </div>
    </header>

    <nav class="flex flex-wrap gap-2 mt-6">
      <button v-for="t in tabs" :key="t[0]" type="button"
        class="px-3 py-1 rounded border"
        :class="tab===t[0] ? 'bg-wouri-700 text-white border-wouri-700' : 'bg-white'"
        @click="tab=t[0]">{{ t[1] }}</button>
    </nav>

    <p v-if="msg" class="mt-3 text-green-800 text-sm">{{ msg }}</p>
    <p v-if="err" class="mt-3 text-red-700 text-sm">{{ err }}</p>

    <section v-show="tab==='upload' && can('ingest')" class="mt-4 space-y-3">
      <p class="text-sm text-stone-600">JSON / CSV / XLSX. text_local + text_fr. Bronze. Doublons ignorés.</p>
      <input type="file" accept=".json,.csv,.xlsx" @change="sendFile" />
      <textarea v-model="jsonText" class="w-full h-32 border rounded p-2 font-mono text-sm" />
      <button class="bg-wouri-700 text-white px-3 py-1 rounded" type="button" @click="sendJson">Envoyer JSON</button>
    </section>

    <section v-show="tab==='bronze' && can('review')" class="mt-4 space-y-3">
      <article v-for="r in bronze" :key="r.id" class="border rounded p-3 bg-white">
        <p><strong>{{ r.text_local }}</strong></p>
        <p class="text-stone-600">{{ r.text_fr }}</p>
        <audio v-if="r.audio_url" :src="mediaSrc(r)" crossorigin="use-credentials" controls class="mt-2 h-8"></audio>
        <button class="mr-2 mt-2 border px-2 py-1" type="button" @click="decide(r.id,'admin_accepted')">Accepter</button>
        <button class="mt-2 border px-2 py-1" type="button" @click="decide(r.id,'admin_rejected')">Rejeter</button>
      </article>
      <p v-if="!bronze.length" class="text-stone-500 text-sm">Aucune phrase Bronze.</p>
    </section>

    <section v-show="tab==='accepted' && can('promote')" class="mt-4 space-y-3">
      <article v-for="r in accepted" :key="r.id" class="border rounded p-3 bg-white">
        <p><strong>{{ r.text_local }}</strong></p>
        <p class="text-stone-600">{{ r.text_fr }}</p>
        <audio v-if="r.audio_url" :src="mediaSrc(r)" crossorigin="use-credentials" controls class="mt-2 h-8"></audio>
        <button class="mt-2 bg-wouri-700 text-white px-2 py-1 rounded" type="button" @click="promote(r.id)">Promouvoir</button>
      </article>
      <p v-if="!accepted.length" class="text-stone-500 text-sm">Rien à promouvoir.</p>
    </section>

    <section v-show="tab==='corpus'" class="mt-4 space-y-3">
      <article v-for="r in corpus" :key="r.id" class="border rounded p-3 bg-white">
        <p><strong>{{ r.text_local }}</strong></p>
        <p class="text-stone-600">{{ r.text_fr }}</p>
        <audio v-if="r.audio_url" :src="mediaSrc(r)" crossorigin="use-credentials" controls class="mt-2 h-8"></audio>
        <p v-else class="text-xs text-stone-500">Sans audio</p>
      </article>
      <p v-if="!corpus.length" class="text-stone-500 text-sm">Corpus atelier vide.</p>
    </section>
  </div>
</template>
