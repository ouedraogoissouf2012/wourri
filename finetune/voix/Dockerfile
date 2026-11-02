# Serveur voix baoulé sur processeur (ADR-0048) : même serveur que sur le GPU loué
# (serveur_voix_bci.py, ADR-0045), sans carte graphique.
#
# Contexte de construction : le dossier finetune/ (modules du serveur, pas le dépôt entier).
#     docker build -f finetune/voix/Dockerfile -t wourri-voix-bci finetune
#
# Le modèle (3,9 Go, dépôt Hugging Face privé) n'est PAS dans l'image : il est monté dans
# /modele (variable BCI_VOIX_MODELE). Les réponses lues par le locuteur (ogg) sont montées
# dans /donnees/reponses_ogg, le modèle de langue facultatif dans /donnees/lm_bci.pkl.
# Étage 1 : compilation. omnilingual-asr exige kenlm, compilé à l'installation (pas de
# roue précompilée) : compilateur et en-têtes ici seulement, pas dans l'image servie.
FROM python:3.12-slim-bookworm AS construction
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake zlib1g-dev libbz2-dev liblzma-dev \
    && rm -rf /var/lib/apt/lists/*
# fairseq2 0.6 exige la variante de fairseq2n qui correspond EXACTEMENT à PyTorch :
# torch 2.8.0 « +cpu » et fairseq2n « 0.6+cpu » (index officiel, tableau des variantes).
# La contrainte empêche pip de remplacer torch par la version CUDA de PyPI.
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/voix
ENV PATH=/opt/voix/bin:$PATH
COPY voix/requirements-voix-bci.txt /tmp/requirements-voix-bci.txt
RUN printf 'torch==2.8.0+cpu\ntorchaudio==2.8.0+cpu\n' > /tmp/contraintes.txt \
    && pip install torch==2.8.0+cpu torchaudio==2.8.0+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install -c /tmp/contraintes.txt -r /tmp/requirements-voix-bci.txt \
       --extra-index-url https://download.pytorch.org/whl/cpu \
       --extra-index-url https://fair.pkg.atmeta.com/fairseq2/whl/pt2.8.0/cpu

# Étage 2 : image servie, sans compilateur.
FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=construction /opt/voix /opt/voix
ENV PATH=/opt/voix/bin:$PATH
RUN python -c "import torch, fairseq2n, kenlm, omnilingual_asr; assert not torch.cuda.is_available(); print('torch', torch.__version__, '| fairseq2n', fairseq2n.__version__)"

RUN useradd --create-home --uid 1000 voix
WORKDIR /app
COPY dictee_to_parquet.py prepare_bci_dataset.py eval_bci_cer.py cv27_split.py lm_bci.py \
     serveur_voix_bci.py mesure_lm_bci.py mesure_cpu_bci.py voix/demarrer.py ./
RUN mkdir -p /donnees && chown voix:voix /donnees
USER voix

# BCI_VOIX_PROCESSEUR=1 : float32 + int8 (mesuré le 2026-10-27 : CER identique au GPU,
# vocal de 10 s en 4,8 s sur 4 cœurs ; le bfloat16 du GPU est bien plus lent ici).
ENV BCI_VOIX_PROCESSEUR=1 BCI_VOIX_MODELE=/modele BCI_VOIX_STEP=step_3000 BCI_VOIX_AUDIO=/donnees/reponses_ogg \
    FAIRSEQ2_USER_ASSET_DIR=/tmp/fairseq2_assets PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["python", "demarrer.py"]
