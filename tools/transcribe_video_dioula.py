"""
WOURRI - Transcription vidéo Dioula via MMS-1B-ALL
Découpe l'audio en segments de 30s et transcrit chaque segment via l'API locale.

Usage:
    python tools/transcribe_video_dioula.py "C:/chemin/vers/video-DIOULA-Audio.mp4"
"""

import sys
import os
import subprocess
import requests
import json
import tempfile
import time

# ============================================================
# CONFIGURATION
# ============================================================
API_URL    = "http://localhost:8000/api/asr/transcribe"
LANGUAGE   = "dyi"          # Dioula (MMS-1B-ALL)
SEGMENT_S  = 25             # secondes par segment
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# FONCTIONS
# ============================================================

def get_audio_duration(audio_path: str) -> float:
    """Retourne la durée du fichier audio en secondes."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def split_audio(audio_path: str, segment_s: int, tmp_dir: str) -> list:
    """Découpe l'audio en segments WAV de segment_s secondes."""
    duration = get_audio_duration(audio_path)
    total = int(duration // segment_s) + 1
    segments = []

    print(f"[INFO] Durée totale : {duration:.0f}s → {total} segments de {segment_s}s")

    for i in range(total):
        start = i * segment_s
        out_path = os.path.join(tmp_dir, f"seg_{i:04d}.wav")
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", audio_path,
            "-ss", str(start),
            "-t",  str(segment_s),
            "-ar", "16000",
            "-ac", "1",
            out_path
        ]
        subprocess.run(cmd, check=True)
        segments.append((i, start, out_path))

    return segments


def transcribe_segment(seg_path: str, index: int) -> str:
    """Envoie un segment WAV à l'API ASR et retourne la transcription."""
    with open(seg_path, "rb") as f:
        files = {"audio": ("segment.wav", f, "audio/wav")}
        data  = {"language": LANGUAGE}
        try:
            resp = requests.post(API_URL, files=files, data=data, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            text = result.get("transcription", "").strip()
            return text
        except Exception as e:
            print(f"  [ERREUR seg {index}] {e}")
            return ""


# ============================================================
# MAIN
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python transcribe_video_dioula.py <chemin_audio.mp4>")
        sys.exit(1)

    audio_path = sys.argv[1]
    if not os.path.exists(audio_path):
        print(f"[ERREUR] Fichier introuvable : {audio_path}")
        sys.exit(1)

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    output_file = os.path.join(OUTPUT_DIR, f"{base_name}_TRANSCRIPTION_DYI.txt")

    print(f"[INFO] Fichier  : {audio_path}")
    print(f"[INFO] Langue   : {LANGUAGE} (Dioula — MMS-1B-ALL)")
    print(f"[INFO] API      : {API_URL}")
    print(f"[INFO] Sortie   : {output_file}")
    print()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Découper
        print("[ÉTAPE 1] Découpage audio...")
        segments = split_audio(audio_path, SEGMENT_S, tmp_dir)

        # 2. Transcrire chaque segment
        print(f"[ÉTAPE 2] Transcription de {len(segments)} segments...\n")
        transcriptions = []

        for idx, start, seg_path in segments:
            minutes = int(start // 60)
            seconds = int(start % 60)
            print(f"  [{minutes:02d}:{seconds:02d}] Segment {idx+1}/{len(segments)}...", end=" ")

            text = transcribe_segment(seg_path, idx)
            transcriptions.append({
                "segment": idx,
                "start_s": start,
                "time":    f"{minutes:02d}:{seconds:02d}",
                "text":    text
            })

            print(f"→ {text[:80] if text else '(vide)'}")
            time.sleep(0.5)  # pause entre requêtes

        # 3. Sauvegarder
        print(f"\n[ÉTAPE 3] Sauvegarde → {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# Transcription Dioula — {base_name}\n")
            f.write(f"# Langue: {LANGUAGE} | Modèle: MMS-1B-ALL\n")
            f.write(f"# Segments: {len(segments)} × {SEGMENT_S}s\n\n")
            for t in transcriptions:
                if t["text"]:
                    f.write(f"[{t['time']}] {t['text']}\n")

        # 4. Résumé
        non_vides = sum(1 for t in transcriptions if t["text"])
        print(f"\n[DONE] {non_vides}/{len(segments)} segments transcrits.")
        print(f"[DONE] Fichier : {output_file}")

        # Aperçu
        print("\n--- APERÇU (100 premiers caractères/ligne) ---")
        for t in transcriptions[:10]:
            if t["text"]:
                print(f"[{t['time']}] {t['text'][:100]}")


if __name__ == "__main__":
    main()
