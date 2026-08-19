(() => {
  const list = document.getElementById("list");
  const keyInput = document.getElementById("key");

  async function api(path, opt) {
    const headers = Object.assign(
      { "X-API-Key": keyInput.value },
      (opt && opt.headers) || {}
    );
    const r = await fetch(path, Object.assign({}, opt, { headers }));
    const data = await r.json().catch(() => ({}));
    if (r.status === 401 || r.status === 403) {
      throw new Error("Clé refusée — utilise API_SECRET_KEY de wouri-api");
    }
    if (!r.ok) throw new Error(data.detail || "Erreur " + r.status);
    return data;
  }

  async function refresh() {
    list.textContent = "Chargement…";
    const data = await api("/admin/lqe/tasks");
    const tasks = data.tasks || [];
    if (!tasks.length) {
      list.textContent = "Aucune tâche Bronze dyu.";
      return;
    }
    list.innerHTML = tasks
      .map(
        (t) => `
      <article class="card" data-id="${t.id}">
        <div><strong>${t.intent || "—"}</strong> · ${t.source || ""}</div>
        <p class="excerpt">${String(t.excerpt || "").replace(/</g, "")}</p>
        <button type="button" data-d="admin_accepted">Accepter (file admin)</button>
        <button type="button" data-d="admin_rejected">Rejeter</button>
      </article>`
      )
      .join("");
  }

  document.getElementById("load").addEventListener("click", () => {
    refresh().catch((e) => {
      list.textContent = e.message;
    });
  });

  list.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-d]");
    if (!btn) return;
    const id = btn.closest("[data-id]").dataset.id;
    try {
      await api("/admin/lqe/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, decision: btn.dataset.d }),
      });
      await refresh();
    } catch (e) {
      list.textContent = e.message;
    }
  });
})();
