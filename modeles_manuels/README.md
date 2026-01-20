# Modeles ML pour WOURI

Les modeles ML sont trop volumineux pour GitHub. Telechargez-les manuellement.

## Modeles requis

### 1. TTS Bambara (VITS)
**Taille:** ~139 MB

```bash
# Telecharger depuis Hugging Face
pip install huggingface_hub

python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='facebook/mms-tts-bam',
    local_dir='./modeles_manuels',
    local_dir_use_symlinks=False
)
"
```

Ou manuellement: https://huggingface.co/facebook/mms-tts-bam

### 2. Sentence Transformer (RAG)
**Taille:** ~470 MB

```bash
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
model.save('./modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2')
"
```

Ou manuellement: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

## Structure attendue

```
modeles_manuels/
├── config.json
├── model.safetensors          # TTS Bambara (~139 MB)
├── tokenizer_config.json
├── vocab.json
├── special_tokens_map.json
└── paraphrase-multilingual-MiniLM-L12-v2/
    ├── config.json
    ├── model.safetensors      # Sentence Transformer (~449 MB)
    ├── tokenizer.json
    └── ...
```

## Script de telechargement automatique

Executez ce script Python pour telecharger tous les modeles:

```python
# telecharger_modeles.py
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
import os

# Creer le dossier
os.makedirs('modeles_manuels', exist_ok=True)

print("Telechargement du modele TTS Bambara...")
snapshot_download(
    repo_id='facebook/mms-tts-bam',
    local_dir='./modeles_manuels',
    local_dir_use_symlinks=False
)

print("Telechargement du modele Sentence Transformer...")
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
model.save('./modeles_manuels/paraphrase-multilingual-MiniLM-L12-v2')

print("Telechargement termine!")
```
