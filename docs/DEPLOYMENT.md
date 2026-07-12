# Guide de Déploiement et Configuration SSO — VO Event Max

Ce guide décrit les étapes nécessaires pour déployer la plateforme VO Event Max en production et configurer l'authentification unique (SSO) pour l'organisation VO Group.

---

## 1. Architecture de Production

La plateforme est conçue pour être hébergée de manière distribuée et sécurisée :
* **Base de données** : Supabase (PostgreSQL managé) hébergé à **Paris (eu-west-3)**.
* **Backend API (FastAPI)** : Railway hébergé sur la zone **Amsterdam EU (am1)** pour assurer une faible latence vers la base de données.
* **Frontend Web (Next.js)** : Vercel (Edge Network).

---

## 2. Étape 1 : Initialisation de la Base de Données Supabase

1. Connectez-vous sur votre console **Supabase** et créez un nouveau projet.
2. Choisissez la région **Paris (eu-west-3)**.
3. Allez dans le **SQL Editor** et exécutez successivement les fichiers SQL d'initialisation dans cet ordre :
   * `docs/schema.sql` (Schéma principal de la Phase 1)
   * `docs/schema_phase2.sql` (Tables logistiques de la Phase 2 : Vols, Hôtels, Transferts, Activités)
   * `docs/schema_email_agent.sql` (Table de l'Email Agent IA de la Phase 3)

---

## 3. Étape 2 : Configuration du SSO (Single Sign-On)

La plateforme utilise **Supabase Auth** qui intègre le support natif pour les protocoles SAML 2.0 et OpenID Connect (OIDC). Pour configurer le SSO professionnel pour VO Communication Group :

### Option A : SAML 2.0 (Azure AD / Google Workspace)
1. Dans la console Supabase, allez dans **Authentication** > **Providers** > **SAML 2.0**.
2. Récupérez les URLs d'assertion générées par Supabase :
   * **Assertion Consumer Service (ACS) URL**
   * **Entity ID**
3. Configurez une application d'entreprise dans votre fournisseur d'identité (IdP) VO Group (Azure Active Directory / Okta / Google Workspace) avec ces URLs.
4. Mappez les attributs utilisateurs requis :
   * `email` -> identifiant utilisateur professionnel.
   * `name` -> nom complet.
5. Exportez les métadonnées xml de votre IdP ou copiez l'URL des métadonnées.
6. Collez l'URL des métadonnées ou le certificat dans la configuration SAML de Supabase.

### Option B : OpenID Connect (OIDC / OAuth2)
1. Dans **Authentication** > **Providers**, activez le fournisseur de votre IdP (ex. **Azure Active Directory** ou **Google**).
2. Fournissez l'**ID Client** et le **Secret Client** obtenus auprès de votre service informatique VO Group.
3. Configurez les redirections autorisées dans le portail d'administration de votre IdP vers :
   `https://<your-supabase-project-id>.supabase.co/auth/v1/callback`

---

## 4. Étape 3 : Déploiement du Backend sur Railway

1. Installez la CLI Railway et connectez-vous (`railway login`).
2. Créez un nouveau projet sur Railway dans la région **Amsterdam (EU)**.
3. Ajoutez un service basé sur le répertoire `apps/api` de votre dépôt.
4. Configurez les variables d'environnement suivantes dans Railway :
   * `SUPABASE_URL` : L'URL de votre projet Supabase.
   * `SUPABASE_SERVICE_ROLE_KEY` : Clé de rôle de service Supabase (bypasse les RLS pour permettre le matching).
   * `SECRET_KEY` : Clé secrète de chiffrement (générée aléatoirement).
   * `ALLOWED_ORIGINS` : L'URL finale de votre frontend Vercel (ex: `https://vo-event-max.vercel.app`).
   * `GEMINI_API_KEY` : Votre clé d'API Google Gemini (nécessaire pour l'Email Agent IA).
5. Railway déploiera automatiquement à chaque nouveau commit sur la branche principale.

---

## 5. Étape 4 : Déploiement du Frontend sur Vercel

1. Connectez votre dépôt Git à **Vercel**.
2. Créez un nouveau projet et liez le sous-dossier `apps/web`.
3. Configurez les variables d'environnement suivantes dans Vercel :
   * `NEXT_PUBLIC_SUPABASE_URL` : L'URL publique de votre projet Supabase.
   * `NEXT_PUBLIC_SUPABASE_ANON_KEY` : La clé anonyme publique de Supabase.
   * `NEXT_PUBLIC_API_URL` : L'URL publique de votre backend déployé sur Railway.
4. Lancez le déploiement. Vercel optimisera la compilation en mode Turbopack.
