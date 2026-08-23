<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";

const router = useRouter();
const rows = ref([]);
const err = ref("");

onMounted(async () => {
  try {
    const me = await api("/auth/me");
    if (!(me.roles || []).includes("admin")) {
      router.push("/");
      return;
    }
    const d = await api("/coverage");
    rows.value = d.languages || [];
  } catch (e) {
    if (e.status !== 401) err.value = String(e.message || e);
  }
});

function pct(r) {
  return r.total ? Math.round((r.covered / r.total) * 100) : 0;
}
</script>
<template>
  <div class="max-w-3xl mx-auto p-6">
    <p class="text-sm mb-4">
      <a href="/" class="underline">← Atelier</a> ·
      <a href="/admin" class="underline">Comptes</a>
    </p>
    <h1 class="text-xl font-semibold text-wouri-700">Couverture par langue</h1>
    <p class="text-sm text-stone-600">
      Concepts couverts (promus) par langue, sur le corpus de référence.
    </p>
    <p v-if="err" class="text-red-700 text-sm mt-2">{{ err }}</p>

    <table class="mt-4 w-full text-sm border bg-white">
      <thead>
        <tr class="bg-stone-100 text-left">
          <th class="p-2">Langue</th>
          <th class="p-2">Couverts</th>
          <th class="p-2">Manquants</th>
          <th class="p-2">%</th>
          <th class="p-2">À jour</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.code" class="border-t">
          <td class="p-2"><strong>{{ r.name }}</strong> <code>{{ r.code }}</code></td>
          <td class="p-2">{{ r.covered }} / {{ r.total }}</td>
          <td class="p-2">{{ r.missing }}</td>
          <td class="p-2">{{ pct(r) }}%</td>
          <td class="p-2">{{ r.up_to_date ? "✅" : "—" }}</td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="5" class="p-2 text-stone-500">Aucune langue active.</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
