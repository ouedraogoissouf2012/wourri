#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WOURI — Outil de validation batch TTS (Axe 5)

Analyse toutes les phrases du corpus IVR et génère un rapport HTML interactif :
  - Découpage prévu par _split_sentences() avec durées de pause
  - Indicateur visuel : 🟢 ≤12 mots / 🟡 13-20 mots / 🔴 >20 mots
  - Lecteur audio si l'option --generate-audio est utilisée
  - Export JSON des phrases à réécrire en priorité

Usage :
    python tools/test_tts_batch.py                    # analyse seule (rapide)
    python tools/test_tts_batch.py --generate-audio   # + génère les audios TTS
    python tools/test_tts_batch.py --generate-audio --max 20  # limiter à 20
    python tools/test_tts_batch.py --culture CULTURE_RIZ      # filtrer par culture
    python tools/test_tts_batch.py --out rapport_tts.html     # nom du fichier HTML
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── Chemins ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CORPUS_PATH = ROOT / "dictionnaires" / "corpus_ivr.json"
AUDIO_DIR = ROOT / "static" / "audio"
REPORT_DIR = ROOT / "tools" / "reports"

# ── Reproduction locale de _split_sentences() ────────────────────────────────
# (sans importer torch pour que l'outil reste rapide)

_BAMBARA_DISCOURSE_MARKERS = [
    (r'\bnka\b', 0.30),
    (r'\bnɔ\b',  0.30),
    (r'\bfɔlɔ\b', 0.25),
    (r'\bkɔ\b',  0.25),
]


def _split_on_bambara_markers(text):
    result = [(text, 0.0)]
    for pattern, pause in _BAMBARA_DISCOURSE_MARKERS:
        new_result = []
        for seg, seg_pause in result:
            parts = re.split(r'(?=\s+' + pattern + r')', seg, maxsplit=2)
            if len(parts) > 1 and all(len(p.strip().split()) >= 4 for p in parts if p.strip()):
                for i, p in enumerate(parts):
                    p = p.strip()
                    if not p:
                        continue
                    new_result.append((p, seg_pause if i == len(parts) - 1 else pause))
            else:
                new_result.append((seg, seg_pause))
        result = new_result
    return result


def _force_split_long(text, pause, max_words=12):
    words = text.split()
    if len(words) <= max_words:
        return [(text, pause)]
    mid = len(words) // 2
    return [(' '.join(words[:mid]), 0.25), (' '.join(words[mid:]), pause)]


def split_sentences(text):
    """Retourne list[(segment, pause_s)] — miroir de tts_dioula._split_sentences."""
    text = re.sub(r'\{\{[^}]+\}\}', '', text).strip()
    if not text:
        return []
    results = []
    for part in re.split(r'(?<=[.!?])\s+', text):
        part = part.strip()
        if not part:
            continue
        end_pause = 0.50 if part[-1] in '!?' else (0.45 if part[-1] == '.' else 0.40)
        comma_parts = re.split(r',\s*', part)
        for ci, sub in enumerate(comma_parts):
            sub = sub.strip()
            if not sub:
                continue
            comma_pause = end_pause if ci == len(comma_parts) - 1 else 0.20
            marker_segs = _split_on_bambara_markers(sub)
            for mi, (seg, _) in enumerate(marker_segs):
                seg_pause = comma_pause if mi == len(marker_segs) - 1 else 0.30
                results.extend(_force_split_long(seg, seg_pause))
    cleaned = []
    for s, p in results:
        s = s.strip()
        if not s:
            continue
        if len(s.split()) < 3 and cleaned:
            prev_s, _ = cleaned[-1]
            cleaned[-1] = (prev_s + ' ' + s, p)
        elif len(s.split()) >= 2 or (len(s.split()) == 1 and len(s) > 3):
            cleaned.append((s, p))
    return cleaned


# ── Analyse ──────────────────────────────────────────────────────────────────

def word_count(text):
    return len(re.sub(r'\{\{[^}]+\}\}', '', text).split())


def total_badge(total_words):
    """Niveau basé sur le TOTAL de mots (indicateur de réécriture nécessaire).

    La coupure forcée (_force_split_long) garantit mécaniquement des segments ≤12 mots,
    mais les longues phrases restent peu naturelles même découpées.
    Critère :
      ≤ 18 mots → 🟢 naturellement lisible à l'oral
      19-28 mots → 🟡 acceptable, idéalement à raccourcir
      > 28 mots  → 🔴 trop long, réécriture fortement recommandée
    """
    if total_words <= 18:
        return "🟢", "ok"
    elif total_words <= 28:
        return "🟡", "warn"
    else:
        return "🔴", "bad"


def analyze_entry(entry):
    text = entry.get("reponse_bambara", "")
    total_words = word_count(text)
    segments = split_sentences(text)
    max_seg = max((len(s.split()) for s, _ in segments), default=0)
    # Nombre de segments issus du découpage forcé (indique manque de naturalité)
    forced_splits = sum(1 for s, _ in segments if len(s.split()) == 6 or len(s.split()) == 7)
    badge, level = total_badge(total_words)
    return {
        "id": entry.get("id", ""),
        "intent": entry.get("intent", ""),
        "cultures": entry.get("cultures", ["*"]),
        "reponse_bambara": text,
        "total_words": total_words,
        "segments": [(s, round(p * 1000)) for s, p in segments],
        "max_seg_words": max_seg,
        "n_segments": len(segments),
        "badge": badge,
        "level": level,
        "audio_path": None,
    }


# ── Génération audio ─────────────────────────────────────────────────────────

def generate_audio_for_entry(entry_analysis):
    """Appelle synthesize_dioula_text() et retourne le chemin relatif OGG."""
    try:
        sys.path.insert(0, str(ROOT))
        from app.services.tts_dioula import synthesize_dioula_text
        path = synthesize_dioula_text(entry_analysis["reponse_bambara"])
        return path  # ex: "/static/audio/dyu_xxxx.ogg"
    except Exception as e:
        print(f"  [ERREUR TTS] {e}")
        return None


# ── HTML ─────────────────────────────────────────────────────────────────────

_CSS = """
body { font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; margin: 0; padding: 16px; }
h1 { color: #f6c90e; margin-bottom: 4px; }
.stats { color: #94a3b8; margin-bottom: 24px; font-size: 14px; }
.legend { display:flex; gap:16px; margin-bottom:20px; font-size:13px; }
.legend span { padding:3px 10px; border-radius:20px; }
.ok   { background:#14532d; color:#86efac; }
.warn { background:#713f12; color:#fde68a; }
.bad  { background:#7f1d1d; color:#fca5a5; }
.filter-bar { display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap; }
.filter-bar button { padding:6px 14px; border-radius:6px; border:1px solid #334155;
    background:#1e293b; color:#cbd5e1; cursor:pointer; font-size:13px; }
.filter-bar button.active { background:#f6c90e; color:#0f1117; border-color:#f6c90e; }
.card { background:#1e293b; border-radius:10px; padding:16px; margin-bottom:14px;
    border-left:4px solid #334155; }
.card.bad  { border-left-color:#ef4444; }
.card.warn { border-left-color:#f59e0b; }
.card.ok   { border-left-color:#22c55e; }
.card-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.intent { font-size:12px; color:#64748b; font-weight:600; letter-spacing:.05em; }
.cultures { font-size:11px; color:#475569; margin-top:2px; }
.bambara { font-size:15px; color:#f1f5f9; margin:10px 0; line-height:1.6; }
.segments { margin:8px 0; }
.seg { display:inline-block; background:#0f172a; border-radius:5px; padding:4px 8px;
    margin:3px 4px 3px 0; font-size:12px; }
.seg .n { font-weight:700; margin-right:4px; }
.seg.ok-seg   .n { color:#86efac; }
.seg.warn-seg .n { color:#fde68a; }
.seg.bad-seg  .n { color:#fca5a5; }
.pause-badge { font-size:10px; color:#64748b; margin-left:4px; }
.total { font-size:12px; color:#64748b; margin-top:6px; }
audio { margin-top:10px; width:100%; height:32px; filter:invert(1) hue-rotate(180deg); }
.star-rating { display:flex; gap:4px; margin-top:10px; }
.star-rating button { background:none; border:none; font-size:20px; cursor:pointer; padding:0; }
.note-display { font-size:12px; color:#94a3b8; margin-left:8px; align-self:center; }
.rewrite-flag { font-size:11px; color:#f87171; margin-top:6px; }
"""

_JS = """
function filterCards(level) {
    document.querySelectorAll('.filter-bar button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.card').forEach(c => {
        c.style.display = (level === 'all' || c.dataset.level === level) ? '' : 'none';
    });
}
function rateStar(entryId, stars) {
    const key = 'wourri_tts_rating_' + entryId;
    localStorage.setItem(key, stars);
    updateStars(entryId, stars);
}
function updateStars(entryId, stars) {
    const row = document.getElementById('stars_' + entryId);
    if (!row) return;
    row.querySelectorAll('button').forEach((b, i) => {
        b.textContent = i < stars ? '⭐' : '☆';
    });
    const nd = document.getElementById('note_' + entryId);
    if (nd) nd.textContent = stars + '/5';
}
window.addEventListener('load', () => {
    document.querySelectorAll('.card').forEach(card => {
        const eid = card.dataset.id;
        const saved = localStorage.getItem('wourri_tts_rating_' + eid);
        if (saved) updateStars(eid, parseInt(saved));
    });
});
function exportRatings() {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k.startsWith('wourri_tts_rating_')) out[k.replace('wourri_tts_rating_', '')] = parseInt(localStorage.getItem(k));
    }
    const blob = new Blob([JSON.stringify(out, null, 2)], {type:'application/json'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'tts_ratings.json'; a.click();
}
"""


def _render_stars(eid_safe):
    """Génère les 5 boutons étoiles pour l'id donné."""
    buttons = []
    for i in range(5):
        onclick = f"rateStar('{eid_safe}', {i + 1})"
        buttons.append(f'<button onclick="{onclick}">☆</button>')
    return "".join(buttons)


def _seg_class(n_words):
    if n_words <= 12:
        return "ok-seg"
    elif n_words <= 20:
        return "warn-seg"
    return "bad-seg"


def render_card(a, audio_base_url="http://localhost:8000"):
    eid = a["id"] or f"{a['intent']}_{a['cultures'][0]}"
    eid_safe = re.sub(r'[^a-zA-Z0-9_]', '_', eid)
    cultures_str = ", ".join(a["cultures"])

    segs_html = ""
    for seg, pause_ms in a["segments"]:
        n = len(seg.split())
        cls = _seg_class(n)
        segs_html += (
            f'<span class="seg {cls}">'
            f'<span class="n">{n}w</span>{seg}'
            f'<span class="pause-badge">→{pause_ms}ms</span>'
            f'</span>'
        )

    audio_html = ""
    if a.get("audio_path"):
        url = audio_base_url.rstrip("/") + a["audio_path"]
        audio_html = f'<audio controls preload="none" src="{url}"></audio>'

    rewrite_html = ""
    if a["level"] == "bad":
        rewrite_html = '<div class="rewrite-flag">⚠️ À réécrire en priorité — segments trop longs</div>'
    elif a["level"] == "warn":
        rewrite_html = '<div class="rewrite-flag" style="color:#fbbf24">⚡ À améliorer</div>'

    return f"""
<div class="card {a['level']}" data-level="{a['level']}" data-id="{eid_safe}">
  <div class="card-header">
    <div>
      <div class="intent">{a['badge']} {a['intent']}</div>
      <div class="cultures">{cultures_str}</div>
    </div>
    <div class="total">{a['total_words']} mots · {a['n_segments']} seg · max {a['max_seg_words']}w/seg</div>
  </div>
  <div class="bambara">{a['reponse_bambara']}</div>
  <div class="segments">{segs_html}</div>
  {audio_html}
  {rewrite_html}
  <div class="star-rating">
    <span style="font-size:12px;color:#64748b;align-self:center">Qualité :</span>
    <span id="stars_{eid_safe}">{_render_stars(eid_safe)}</span>
    <span class="note-display" id="note_{eid_safe}">-/5</span>
  </div>
</div>"""


def build_html(analyses, audio_base_url="http://localhost:8000"):
    total = len(analyses)
    n_ok   = sum(1 for a in analyses if a["level"] == "ok")
    n_warn = sum(1 for a in analyses if a["level"] == "warn")
    n_bad  = sum(1 for a in analyses if a["level"] == "bad")

    cards = "\n".join(render_card(a, audio_base_url) for a in analyses)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WOURI — Rapport TTS Batch</title>
<style>{_CSS}</style>
</head>
<body>
<h1>🎙️ WOURI — Rapport TTS Batch</h1>
<div class="stats">
  {total} phrases · <span class="ok" style="padding:2px 8px;border-radius:10px">{n_ok} ok</span>
  <span class="warn" style="padding:2px 8px;border-radius:10px">{n_warn} à améliorer</span>
  <span class="bad" style="padding:2px 8px;border-radius:10px">{n_bad} à réécrire</span>
</div>
<div class="legend">
  <span class="ok">🟢 segment ≤ 12 mots</span>
  <span class="warn">🟡 segment 13-20 mots</span>
  <span class="bad">🔴 segment &gt; 20 mots</span>
</div>
<div class="filter-bar">
  <button class="active" onclick="filterCards('all')">Tout ({total})</button>
  <button onclick="filterCards('bad')">🔴 À réécrire ({n_bad})</button>
  <button onclick="filterCards('warn')">🟡 À améliorer ({n_warn})</button>
  <button onclick="filterCards('ok')">🟢 OK ({n_ok})</button>
  <button onclick="exportRatings()" style="margin-left:auto;background:#1e3a5f">
    💾 Exporter mes notes
  </button>
</div>
{cards}
<script>{_JS}</script>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Rapport TTS batch WOURI")
    parser.add_argument("--generate-audio", action="store_true",
                        help="Générer les audios TTS (nécessite torch/modèle chargé)")
    parser.add_argument("--max", type=int, default=0,
                        help="Limiter la génération audio à N entrées (0=toutes)")
    parser.add_argument("--culture", default="",
                        help="Filtrer par culture (ex: CULTURE_RIZ)")
    parser.add_argument("--level", choices=["ok", "warn", "bad", "all"], default="all",
                        help="Filtrer par niveau de qualité")
    parser.add_argument("--out", default="rapport_tts.html",
                        help="Fichier HTML de sortie")
    parser.add_argument("--api-url", default="http://localhost:8000",
                        help="URL base de l'API pour les fichiers audio")
    args = parser.parse_args()

    # Charger le corpus
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])

    # Filtres
    if args.culture:
        entries = [e for e in entries if args.culture in e.get("cultures", ["*"]) or "*" in e.get("cultures", [])]
    if args.level != "all":
        pass  # filtrage fait côté HTML avec JS, mais on peut aussi filtrer ici

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"[INFO] {len(entries)} entrees chargees")

    # Analyse
    analyses = [analyze_entry(e) for e in entries]

    # Tri : bad d'abord, puis warn, puis ok
    order = {"bad": 0, "warn": 1, "ok": 2}
    analyses.sort(key=lambda a: (order[a["level"]], -a["max_seg_words"]))

    # Stats console
    n_bad  = sum(1 for a in analyses if a["level"] == "bad")
    n_warn = sum(1 for a in analyses if a["level"] == "warn")
    n_ok   = sum(1 for a in analyses if a["level"] == "ok")
    print(f"  [BAD]  A reecrire    : {n_bad}")
    print(f"  [WARN] A ameliorer   : {n_warn}")
    print(f"  [OK]   OK            : {n_ok}")

    # Lister les priorités
    print("\n[PRIORITES] Phrases a reecrire en priorite (total > 28 mots) :")
    for a in analyses:
        if a["level"] == "bad":
            print(f"  {a['total_words']}mots  {a['n_segments']}segs  {a['intent']:<35} {a['cultures']}")

    # Génération audio optionnelle
    if args.generate_audio:
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        limit = args.max if args.max > 0 else len(analyses)
        print(f"\n[TTS] Génération audio pour {min(limit, len(analyses))} entrées...")
        for i, a in enumerate(analyses[:limit]):
            print(f"  [{i+1}/{limit}] {a['intent']} {a['cultures'][0][:20]}", end=" ", flush=True)
            path = generate_audio_for_entry(a)
            a["audio_path"] = path
            print("✓" if path else "✗")

    # Générer le rapport HTML
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / args.out
    html = build_html(analyses, audio_base_url=args.api_url)
    out_path.write_text(html, encoding="utf-8")

    print(f"\n[OK] Rapport généré : {out_path}")
    print(f"     Ouvrir dans le navigateur : file:///{out_path.as_posix()}")

    # Export JSON des phrases à réécrire
    rewrite_list = [
        {"intent": a["intent"], "cultures": a["cultures"],
         "reponse_bambara": a["reponse_bambara"], "max_seg_words": a["max_seg_words"]}
        for a in analyses if a["level"] in ("bad", "warn")
    ]
    json_path = REPORT_DIR / "phrases_a_reecrire.json"
    json_path.write_text(json.dumps(rewrite_list, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Phrases à réécrire : {json_path} ({len(rewrite_list)} entrées)")


if __name__ == "__main__":
    main()
