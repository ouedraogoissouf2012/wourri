(() => {
  const uploadMsg = document.getElementById("uploadMsg");
  const jsonArea = document.getElementById("json");
  const toast = document.getElementById("toast");
  const cache = { bronze: [], accepted: [], corpus: [] };

  function showToast(msg, isErr) {
    if (!toast) return;
    toast.hidden = false;
    toast.style.background = isErr ? "#fdecea" : "#e8f5e9";
    toast.style.borderColor = isErr ? "#c62828" : "#2e7d32";
    toast.textContent = msg;
    setTimeout(() => {
      toast.hidden = true;
    }, 5000);
  }

  async function api(path, opt) {
    const r = await fetch(path, Object.assign({ credentials: "same-origin" }, opt || {}));
    if (r.status === 401) {
      location.href = "/admin/baoule/";
      throw new Error("Session expirée");
    }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const d = data.detail;
      throw new Error(
        (typeof d === "string" ? d : data.reason) ||
          (data.errors && data.errors.join("; ")) ||
          "Erreur " + r.status
      );
    }
    return data;
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function card(t, mode) {
    const audio = t.audio_url
      ? `<p class="meta">Audio : ${esc(t.audio_url)}</p>`
      : `<p class="meta">⚠ Pas d'audio</p>`;
    let actions = "";
    if (mode === "bronze") {
      actions = `<button type="button" data-d="admin_accepted">Accepter → à promouvoir</button>
        <button type="button" data-d="admin_rejected">Rejeter</button>`;
    } else if (mode === "accepted") {
      actions = `<button type="button" data-p="1">Promouvoir au corpus baoulé</button>`;
    }
    return `<article class="card" data-id="${esc(t.id)}">
      <div class="meta"><strong>${esc(t.intent || "—")}</strong> · ${esc(t.source || "")} · ${esc(t.status || "")}</div>
      <p class="local"><strong>Baoulé :</strong> ${esc(t.text_local || t.excerpt || "")}</p>
      <p><strong>FR :</strong> ${esc(t.text_fr || "")}</p>
      ${audio}${actions}
    </article>`;
  }

  function renderLists() {
    const b = cache.bronze || [];
    const a = cache.accepted || [];
    const c = cache.corpus || [];
    const setN = (id, n) => {
      const el = document.getElementById(id);
      if (el) el.textContent = n ? "(" + n + ")" : "";
    };
    setN("nBronze", b.length);
    setN("nAccepted", a.length);
    setN("nCorpus", c.length);
    document.getElementById("listBronze").innerHTML = b.length
      ? b.map((t) => card(t, "bronze")).join("")
      : "<p class='hint'>Aucune phrase Bronze.</p>";
    document.getElementById("listAccepted").innerHTML = a.length
      ? a.map((t) => card(t, "accepted")).join("")
      : "<p class='hint'>Rien à promouvoir. Accepte d'abord dans l'onglet Bronze.</p>";
    document.getElementById("listCorpus").innerHTML = c.length
      ? c
          .slice()
          .reverse()
          .map(
            (t) => `
        <article class="card">
          <div class="meta">production · ${esc(t.promoted_at || "")}</div>
          <p class="local"><strong>Baoulé :</strong> ${esc(t.text_local || "")}</p>
          <p><strong>FR :</strong> ${esc(t.text_fr || "")}</p>
          <p class="meta">${t.audio_url ? "Audio: " + esc(t.audio_url) : "Sans audio"}</p>
        </article>`
          )
          .join("")
      : "<p class='hint'>Corpus baoulé vide.</p>";
  }

  async function refresh() {
    const data = await api("/admin/baoule/api/tasks");
    const who = document.getElementById("who");
    if (who) who.textContent = data.user || "—";
    cache.bronze = data.bronze || [];
    cache.accepted = data.accepted || [];
    const corp = await api("/admin/baoule/api/corpus");
    cache.corpus = corp.entries || [];
    renderLists();
  }

  function switchTab(name) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    const btn = document.querySelector('.tab[data-tab="' + name + '"]');
    const panel = document.getElementById("panel-" + name);
    if (btn) btn.classList.add("active");
    if (panel) panel.classList.add("active");
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  async function afterUpload(data, label) {
    const dup = data.duplicates_skipped || 0;
    uploadMsg.className = "ok";
    uploadMsg.textContent =
      "OK — nouvelles: " +
      (data.accepted || 0) +
      (dup ? " · doublons ignorés: " + dup : "") +
      (label ? " (" + label + ")" : "");
    await refresh();
    switchTab("bronze");
  }

  document.querySelectorAll("[data-refresh]").forEach((btn) => {
    btn.addEventListener("click", () => refresh().catch((e) => showToast(e.message, true)));
  });

  document.getElementById("sendJson").addEventListener("click", () => {
    try {
      const payload = JSON.parse(jsonArea.value);
      uploadMsg.textContent = "Envoi…";
      api("/admin/baoule/api/upload-json", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then((d) => afterUpload(d))
        .catch((e) => {
          uploadMsg.className = "err";
          uploadMsg.textContent = e.message;
        });
    } catch (e) {
      uploadMsg.className = "err";
      uploadMsg.textContent = "JSON invalide: " + e.message;
    }
  });

  document.getElementById("sendFile").addEventListener("click", async () => {
    const f = document.getElementById("file").files[0];
    if (!f) {
      uploadMsg.className = "err";
      uploadMsg.textContent = "Choisis un fichier";
      return;
    }
    const fd = new FormData();
    fd.append("file", f);
    uploadMsg.textContent = "Envoi…";
    try {
      const data = await api("/admin/baoule/api/upload", { method: "POST", body: fd });
      await afterUpload(data, f.name);
    } catch (e) {
      uploadMsg.className = "err";
      uploadMsg.textContent = e.message;
    }
  });

  document.body.addEventListener("click", async (ev) => {
    const btnD = ev.target.closest("button[data-d]");
    const btnP = ev.target.closest("button[data-p]");
    if (!btnD && !btnP) return;
    const art = ev.target.closest("[data-id]");
    if (!art) return;
    const id = art.dataset.id;
    try {
      if (btnD) {
        await api("/admin/baoule/api/decision", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id, decision: btnD.dataset.d }),
        });
        showToast(
          btnD.dataset.d === "admin_accepted"
            ? "Acceptée → onglet À promouvoir"
            : "Rejetée"
        );
        if (btnD.dataset.d === "admin_accepted") switchTab("accepted");
      } else {
        await api("/admin/baoule/api/promote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id }),
        });
        showToast("Promue au corpus baoulé");
        switchTab("corpus");
      }
      await refresh();
    } catch (e) {
      showToast("Erreur: " + e.message, true);
      refresh().catch(() => {});
    }
  });

  refresh().catch((e) => showToast(e.message, true));
})();
