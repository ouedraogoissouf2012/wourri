#!/bin/bash

# Script de déploiement automatique pour cPanel
# Usage: ./deploy.sh

echo "🚀 Préparation du déploiement cPanel..."

# Créer un package de déploiement
echo "📦 Création de l'archive de déploiement..."

# Exclure les fichiers non nécessaires
tar -czf whatsapp-server-deploy.tar.gz \
    --exclude=node_modules \
    --exclude=.wwebjs_auth \
    --exclude=.wwebjs_cache \
    --exclude=.git \
    --exclude=*.log \
    --exclude=sessions \
    --exclude=deploy.sh \
    --exclude=*.bat \
    .

echo "✅ Archive créée : whatsapp-server-deploy.tar.gz"

# Afficher les instructions
echo ""
echo "📋 Instructions de déploiement :"
echo "1. Connectez-vous à votre cPanel"
echo "2. File Manager → dossier de votre sous-domaine"
echo "3. Upload → whatsapp-server-deploy.tar.gz"
echo "4. Extract → décompresser l'archive"
echo "5. Software → Node.js → Create Application"
echo "6. Startup file : app.js"
echo "7. Environment : production"
echo ""
echo "📖 Guide complet : DEPLOIEMENT-CPANEL.md"

# Calculer la taille
size=$(du -h whatsapp-server-deploy.tar.gz | cut -f1)
echo "📏 Taille de l'archive : $size"

echo ""
echo "🎯 Fichiers inclus dans le déploiement :"
tar -tzf whatsapp-server-deploy.tar.gz | head -10
echo "... et plus"

echo ""
echo "✨ Prêt pour le déploiement !"