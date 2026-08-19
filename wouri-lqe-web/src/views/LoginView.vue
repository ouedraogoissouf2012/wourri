<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const user = ref("");
const password = ref("");
const err = ref("");

async function submit() {
  err.value = "";
  try {
    await api("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user: user.value, password: password.value }),
    });
    router.push("/");
  } catch (e) {
    err.value = "Identifiants incorrects";
  }
}
</script>
<template>
  <main class="max-w-sm mx-auto mt-24 p-6 bg-white rounded-lg shadow">
    <h1 class="text-xl font-semibold text-wouri-700">WOURI — Atelier langues</h1>
    <p class="text-sm text-stone-600 mt-1">Compte lié à une langue (dyu, bci, …).</p>
    <form class="mt-6 space-y-3" @submit.prevent="submit">
      <label class="block text-sm">Utilisateur
        <input v-model="user" class="mt-1 w-full border rounded px-3 py-2" required />
      </label>
      <label class="block text-sm">Mot de passe
        <input v-model="password" type="password" class="mt-1 w-full border rounded px-3 py-2" required minlength="8" />
      </label>
      <p v-if="err" class="text-red-700 text-sm">{{ err }}</p>
      <button class="bg-wouri-700 text-white px-4 py-2 rounded" type="submit">Se connecter</button>
    </form>
  </main>
</template>
