<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const langs = ref([]);
const rolesAvail = ref([]);
const rows = ref([]);
const form = ref({ user: "", password: "", language: "", roles: ["review"] });
const msg = ref("");
const err = ref("");

async function load() {
  const d = await api("/accounts");
  rows.value = d.accounts || [];
  langs.value = d.languages || [];
  rolesAvail.value = d.roles || [];
  if (!form.value.language && langs.value[0]) form.value.language = langs.value[0];
}

onMounted(async () => {
  try {
    const me = await api("/auth/me");
    if (!(me.roles || []).includes("admin")) {
      router.push("/");
      return;
    }
    await load();
  } catch {
    router.push("/login");
  }
});

function toggleRole(r) {
  const i = form.value.roles.indexOf(r);
  if (i >= 0) form.value.roles.splice(i, 1);
  else form.value.roles.push(r);
}

async function create() {
  err.value = "";
  try {
    await api("/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form.value),
    });
    msg.value = "Compte créé";
    form.value = { user: "", password: "", language: langs.value[0] || "", roles: ["review"] };
    await load();
  } catch (e) {
    err.value = String(e.message || e);
  }
}

async function setActive(u, active) {
  await api("/accounts/" + encodeURIComponent(u), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  await load();
}
</script>
<template>
  <div class="max-w-3xl mx-auto p-6">
    <p class="text-sm mb-4"><a href="/" class="underline">← Atelier</a></p>
    <h1 class="text-xl font-semibold text-wouri-700">Comptes locuteurs</h1>
    <p class="text-sm text-stone-600">Langue = donnée du compte. Rôles : ingest, review, promote, admin.</p>
    <p v-if="msg" class="text-green-800 text-sm mt-2">{{ msg }}</p>
    <p v-if="err" class="text-red-700 text-sm mt-2">{{ err }}</p>

    <form class="mt-4 grid gap-2 border rounded p-3 bg-white" @submit.prevent="create">
      <input v-model="form.user" class="border rounded px-2 py-1" placeholder="utilisateur" required />
      <input v-model="form.password" type="password" class="border rounded px-2 py-1" placeholder="mot de passe (min 8)" required minlength="8" />
      <select v-model="form.language" class="border rounded px-2 py-1">
        <option v-for="l in langs" :key="l" :value="l">{{ l }}</option>
      </select>
      <div class="flex flex-wrap gap-3 text-sm">
        <label v-for="r in rolesAvail" :key="r" class="flex items-center gap-1">
          <input type="checkbox" :checked="form.roles.includes(r)" @change="toggleRole(r)" /> {{ r }}
        </label>
      </div>
      <button class="bg-wouri-700 text-white px-3 py-1 rounded w-fit" type="submit">Créer</button>
    </form>

    <ul class="mt-6 space-y-2">
      <li v-for="a in rows" :key="a.user" class="border rounded p-3 bg-white flex justify-between gap-2">
        <div>
          <strong>{{ a.user }}</strong> · {{ a.language }} · {{ (a.roles || []).join(", ") }}
          <span class="text-xs">{{ a.active ? "" : " (inactif)" }}</span>
        </div>
        <button class="text-sm underline" type="button" @click="setActive(a.user, !a.active)">
          {{ a.active ? "Désactiver" : "Activer" }}
        </button>
      </li>
    </ul>
  </div>
</template>
