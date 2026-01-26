# WOURI API

## Assistant Agricole IA - Backend Python FastAPI

**Version:** 1.0.0
**Langage:** Python 3.10+
**Framework:** FastAPI

---

## Description

WOURI API est le backend principal de l'assistant agricole WOURI. Il fournit les services d'intelligence artificielle, de traduction, de synthese vocale et de meteo pour les agriculteurs ivoiriens.

---

## Architecture

```
wouri-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # Point d'entree FastAPI
│   ├── config.py            # Configuration (.env)
│   ├── data/
│   │   └── cities.py        # 59 villes de Cote d'Ivoire
│   ├── models/
│   │   └── schemas.py       # Schemas Pydantic
│   ├── routers/
│   │   ├── chat.py          # /api/chat/ - Chat principal
│   │   ├── weather.py       # /api/weather/ - Meteo
│   │   ├── tts.py           # /api/tts/ - Text-to-Speech
│   │   ├── stt.py           # /api/stt/ - Speech-to-Text
│   │   └── rag.py           # /api/rag/ - Knowledge base
│   └── services/
│       ├── deepseek.py      # Service IA DeepSeek
│       ├── weather.py       # Service meteo OpenWeatherMap
│       ├── tts_bambara.py   # TTS Bambara + Traduction
│       ├── tts_french.py    # TTS Francais (Edge-TTS)
│       ├── tts_ivoirian.py  # TTS Multi-langues ivoiriennes (NOUVEAU)
│       ├── stt_whisper.py   # STT Whisper
│       └── rag_knowledge.py # RAG connaissances agricoles
├── modeles_manuels/         # Modeles ML (~1.5 GB total)
├── static/audio/            # Fichiers audio generes
├── templates/               # Templates HTML
├── requirements.txt         # Dependances Python
├── telecharger_modeles.py   # Script telechargement ML
└── .env                     # Configuration (non commite)
```

---

## Installation

### 1. Prerequis

```bash
python --version  # >= 3.10
pip --version
```

### 2. Cloner le projet

```bash
git clone -b API_wourri https://github.com/ouedraogoissouf2012/wourri.git wouri-api
cd wouri-api
```

### 3. Installer les dependances

```bash
pip install -r requirements.txt
```

### 4. Telecharger les modeles ML

```bash
python telecharger_modeles.py
```

**Modeles telecharges:**
| Modele | Taille | Usage |
|--------|--------|-------|
| facebook/mms-tts-bam | ~139 MB | TTS Bambara/Dioula |
| facebook/mms-tts-ati | ~139 MB | TTS Attie |
| facebook/mms-tts-dyi | ~139 MB | TTS Senoufo Djimini |
| facebook/mms-tts-myk | ~139 MB | TTS Senoufo Mamara |
| facebook/mms-tts-gud | ~139 MB | TTS Dida Yocoboue |
| facebook/mms-tts-adj | ~139 MB | TTS Adioukrou |
| facebook/mms-tts-dnj | ~139 MB | TTS Dan/Yacouba |
| facebook/mms-tts-wob | ~139 MB | TTS Wobe |
| facebook/nllb-200-distilled-600M | ~600 MB | Traduction FR→Bambara |
| paraphrase-multilingual-MiniLM-L12-v2 | ~470 MB | RAG embeddings |

### 5. Installer ffmpeg

**Windows:**
```bash
winget install Gyan.FFmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

### 6. Configurer l'environnement

Creer le fichier `.env`:

```env
# DeepSeek API (obligatoire)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Configuration optionnelle
DEBUG=True
DEFAULT_CITY=Abidjan
```

---

## Demarrage

```bash
# Mode developpement (avec reload)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Mode production
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**URLs:**
- API: http://localhost:8000
- Documentation Swagger: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## API Endpoints

### Chat Principal

#### POST /api/chat/

Endpoint principal pour le chat bilingue.

**Request:**
```json
{
  "message": "Comment planter du manioc?",
  "city": "Abidjan",
  "language": "both",
  "include_audio": true
}
```

**Response:**
```json
{
  "response": "Pour planter du manioc, il faut d'abord preparer le sol...",
  "response_dioula": "Manioc siri ka, a ka kan ka dugukoloko labɛn...",
  "audio_url": "/static/audio/bm_xxx.ogg",
  "city": "Abidjan",
  "language": "both"
}
```

**Parametres:**
| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| message | string | - | Message de l'utilisateur |
| city | string | "Abidjan" | Ville pour la meteo |
| language | string | "both" | "french", "dioula", ou "both" |
| include_audio | bool | true | Inclure l'audio vocal |
| audio_language | string | "bam" | Langue audio (bam, ati, dyi, myk, gud, adj, dnj, wob) |

**Langues audio ivoiriennes disponibles:**
| Code | Langue | Region |
|------|--------|--------|
| bam | Bambara/Dioula | Mali, CI |
| ati | Attie | Sud-Est CI |
| dyi | Senoufo Djimini | Nord CI |
| myk | Senoufo Mamara | Nord CI |
| gud | Dida Yocoboue | Sud-Ouest CI |
| adj | Adioukrou | Sud CI |
| dnj | Dan/Yacouba | Ouest CI |
| wob | Wobe | Ouest CI |

---

### Meteo

#### GET /api/weather/{city}

Obtenir la meteo d'une ville.

**Response:**
```json
{
  "city": "Abidjan",
  "region": "Lagunes",
  "temperature": 28.5,
  "humidity": 78,
  "precipitation": 0.0,
  "wind_speed": 12.5,
  "weather_code": 3,
  "weather_description": "Nuageux",
  "advice": "Bon moment pour planter, humidite adequate."
}
```

#### GET /api/weather/cities/list

Liste des 59 villes disponibles.

---

### Text-to-Speech (TTS)

#### POST /api/tts/synthesize

Generer un fichier audio a partir de texte.

**Request:**
```json
{
  "text": "Bonjour, comment allez-vous?",
  "language": "french"
}
```

**Response:**
```json
{
  "audio_url": "/static/audio/fr_xxx.mp3",
  "text": "Bonjour, comment allez-vous?",
  "language": "french"
}
```

#### POST /api/tts/translate

Traduire du francais vers le Bambara.

**Request:**
```json
{
  "text": "Bonjour, comment allez-vous?",
  "source": "fra_Latn",
  "target": "bam_Latn"
}
```

---

### TTS Langues Ivoiriennes (NOUVEAU)

#### GET /api/tts/ivorian/languages

Liste toutes les langues ivoiriennes disponibles.

**Response:**
```json
{
  "languages": {
    "bam": "Bambara/Dioula",
    "ati": "Attie",
    "dyi": "Senoufo Djimini",
    "myk": "Senoufo Mamara",
    "gud": "Dida Yocoboue",
    "adj": "Adioukrou",
    "dnj": "Dan/Yacouba",
    "wob": "Wobe"
  },
  "total": 8
}
```

#### POST /api/tts/ivorian/{language_code}

TTS pour une langue ivoirienne specifique.

**Exemple:**
```bash
curl -X POST "http://localhost:8000/api/tts/ivorian/ati?text=Bonjour"
```

#### POST /api/tts/ivorian

TTS avec detection automatique par alias.

**Alias supportes:**
- `bambara`, `dioula`, `jula` → `bam`
- `attie` → `ati`
- `senoufo` → `dyi`
- `dan`, `yacouba` → `dnj`

---

### Speech-to-Text (STT)

#### POST /api/stt/transcribe

Transcrire un fichier audio en texte.

**Request:** (multipart/form-data)
- `audio`: Fichier audio (mp3, wav, ogg, webm)
- `language`: Code langue (fr, en, bam) - defaut: fr

**Response:**
```json
{
  "success": true,
  "text": "Texte transcrit...",
  "language": "fr",
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "Texte..."}
  ]
}
```

#### GET /api/stt/languages

Liste des langues supportees pour la transcription.

---

### RAG (Knowledge Base)

#### POST /api/rag/search

Rechercher dans la base de connaissances agricoles.

**Request:**
```json
{
  "query": "culture du cacao",
  "top_k": 5
}
```

---

## Services

### 1. DeepSeek (deepseek.py)

Service d'intelligence artificielle pour generer les reponses.

**Configuration:**
```python
DEEPSEEK_API_KEY = "sk-xxx"
DEEPSEEK_MODEL = "deepseek-chat"
```

**Fonctions:**
- `generate_response(message, context)` - Genere une reponse IA

### 2. TTS Bambara (tts_bambara.py)

Synthese vocale en Bambara et traduction.

**Modeles utilises:**
- `facebook/mms-tts-bam` - TTS Bambara
- `facebook/nllb-200-distilled-600M` - Traduction FR→Bambara

**Fonctions:**
- `translate_to_bambara(french_text)` - Traduire FR→Bambara
- `synthesize_bambara_text(bambara_text)` - Generer audio Bambara
- `synthesize_bambara(french_text)` - Traduire + Audio
- `convert_wav_to_ogg(wav_path, ogg_path)` - Conversion pour WhatsApp

### 3. TTS Francais (tts_french.py)

Synthese vocale en francais avec Microsoft Edge-TTS.

**Voix disponibles:**
- `fr-FR-DeniseNeural` (Femme, defaut)
- `fr-FR-HenriNeural` (Homme)
- `fr-FR-EloiseNeural` (Femme, jeune)

**Fonctions:**
- `synthesize_french(text)` - Generer audio MP3

### 4. TTS Ivoirien (tts_ivoirian.py) - NOUVEAU

Synthese vocale multi-langues ivoiriennes avec Facebook MMS.

**Langues supportees:**
| Code | Langue | Modele |
|------|--------|--------|
| bam | Bambara/Dioula | facebook/mms-tts-bam |
| ati | Attie | facebook/mms-tts-ati |
| dyi | Senoufo Djimini | facebook/mms-tts-dyi |
| myk | Senoufo Mamara | facebook/mms-tts-myk |
| gud | Dida Yocoboue | facebook/mms-tts-gud |
| adj | Adioukrou | facebook/mms-tts-adj |
| dnj | Dan/Yacouba | facebook/mms-tts-dnj |
| wob | Wobe | facebook/mms-tts-wob |

**Fonctions:**
- `synthesize_ivorian_text(text, language)` - Generer audio dans une langue
- `synthesize_ivorian(text, language)` - Async avec nom de langue
- `get_supported_languages()` - Liste des langues
- `resolve_language_code(language)` - Resoudre alias vers code

### 5. STT Whisper (stt_whisper.py)

Reconnaissance vocale avec OpenAI Whisper.

**Modele:** `whisper-base` (~139 MB)

**Langues supportees:**
- Francais (fr)
- Anglais (en)
- Bambara (bam)
- Wolof (wo)
- Fulfulde (ff)

**Fonctions:**
- `transcribe_audio(audio_path, language)` - Transcrire fichier
- `transcribe_audio_bytes(audio_bytes, filename, language)` - Transcrire bytes

### 5. Meteo (weather.py)

Service meteo avec Open-Meteo (gratuit, pas de cle API).

**Fonctions:**
- `get_weather(city)` - Obtenir meteo d'une ville
- `get_weather_advice(weather_data)` - Conseil agricole

### 6. RAG Knowledge (rag_knowledge.py)

Base de connaissances agricoles avec Sentence Transformers.

**Modele:** `paraphrase-multilingual-MiniLM-L12-v2`

---

## Variables d'Environnement

| Variable | Obligatoire | Defaut | Description |
|----------|-------------|--------|-------------|
| DEEPSEEK_API_KEY | Oui | - | Cle API DeepSeek |
| DEBUG | Non | True | Mode debug |
| DEFAULT_CITY | Non | Abidjan | Ville par defaut |

---

## Formats Audio

| Service | Format Entree | Format Sortie |
|---------|---------------|---------------|
| TTS Francais | - | MP3 |
| TTS Bambara | - | OGG (Opus) |
| STT Whisper | mp3, wav, ogg, webm | Texte |

**Note:** Le format OGG (Opus) est utilise pour la compatibilite WhatsApp mobile.

---

## Dependances Principales

```
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
httpx>=0.25.0
torch>=2.0.0
transformers>=4.35.0
sentence-transformers>=2.2.0
openai-whisper>=20230918
edge-tts>=6.1.0
scipy>=1.11.0
pydub>=0.25.1
```

---

## Maintenance

### Logs

Les logs s'affichent dans le terminal avec les prefixes:
- `[STT]` - Speech-to-Text
- `[TTS]` - Text-to-Speech
- `[API]` - Appels API
- `[ERREUR]` - Erreurs

### Nettoyage des fichiers audio

```bash
# Supprimer les fichiers audio de plus de 24h
find static/audio -mtime +1 -delete
```

### Mise a jour des modeles

```bash
python telecharger_modeles.py
```

---

## Contact

**Projet:** WOURI - Assistant Agricole IA
**GitHub:** https://github.com/ouedraogoissouf2012/wourri
