# 🔧 Fix: Strava OAuth Connection

## Problème

**Erreur**: `Unable to connect - localhost:5000`

**Cause**: Le redirect URI dans l'app Strava ne correspond pas au port Streamlit

## Solution Rapide

### Étape 1: Configurer l'App Strava

1. Va sur https://www.strava.com/settings/api
2. Trouve ton application (ou crée-en une)
3. Dans "Authorization Callback Domain", mets: **`localhost`**
4. Sauvegarde

### Étape 2: Vérifier le .env

Ouvre ton fichier `.env` et assure-toi que tu as:

```env
STRAVA_CLIENT_ID=ton_client_id
STRAVA_CLIENT_SECRET=ton_client_secret
STRAVA_REDIRECT_URI=http://localhost:8501/Analytics
```

⚠️ **IMPORTANT**: Change le redirect URI pour pointer vers `/Analytics` (la page Streamlit)

### Étape 3: Mise à Jour du Code

J'ai déjà mis à jour le code pour utiliser les query params correctement.

## Nouveau Flow OAuth

### Comment ça marche maintenant:

1. **Tu cliques sur "Connect with Strava"**
2. **Strava te demande d'autoriser**
3. **Strava redirige vers**: `http://localhost:8501/Analytics?code=XXXXX&scope=...`
4. **L'app détecte le code dans l'URL et se connecte automatiquement**

### Si ça marche pas:

**Fallback manuel** - L'app te demande de coller l'URL complète et extrait le code automatiquement.

## Test

1. **Lance Streamlit**:
   ```bash
   streamlit run Home.py
   ```

2. **Va sur Analytics**

3. **Clique "Connect with Strava"**
   - Nouvel onglet s'ouvre
   - Autorise l'app
   - **Redirection automatique vers Analytics avec le code**
   - Connexion se fait toute seule!

## Si Tu Vois Encore "localhost:5000"

C'est que le redirect URI dans ton fichier `.env` pointe encore vers `:5000`.

**Fix**:
1. Ouvre `.env`
2. Change:
   ```
   STRAVA_REDIRECT_URI=http://localhost:8501/Analytics
   ```
3. Redémarre Streamlit

## Alternative: Sans Redirect (Plus Simple)

Si tu veux éviter les problèmes de redirect, utilise cette config dans `.env`:

```env
STRAVA_REDIRECT_URI=http://localhost:8501/Analytics
```

Et dans l'app Strava sur strava.com:
- Authorization Callback Domain: `localhost`

Ça devrait marcher!

## Debug

Si ça marche toujours pas, vérifie:

```bash
# 1. Vérifie les variables d'env
python -c "from config import settings; print(f'Redirect URI: {settings.strava_redirect_uri}')"

# 2. Vérifie que Streamlit tourne sur le bon port
# Regarde l'URL dans ton navigateur, ça devrait être localhost:8501
```

## Status

✅ Code mis à jour pour gérer les query params
✅ Upsert activités pour éviter les duplicates
⚠️ À faire: Configurer Strava redirect URI sur strava.com

---

**Date**: 2026-02-15
**Fix**: OAuth redirect + Activity upsert
