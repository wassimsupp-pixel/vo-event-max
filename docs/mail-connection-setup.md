# Mail connection setup (Gmail / Outlook OAuth)

The Communications tab can connect a real Gmail or Outlook mailbox and pull
incoming participant emails through the Email Agent (which produces
human-validated update proposals). This guide covers the one-time OAuth setup.

## Overview of the flow

1. User clicks **Connect** on Gmail/Outlook in the Communications tab.
2. Frontend calls `GET /api/events/{id}/mail/authorize?provider=…` → gets the
   provider consent URL and redirects the browser to it.
3. After the user consents, the provider redirects to
   `GET /api/mail/oauth/callback?code=…&state=…` (this API).
4. The API exchanges the code for tokens (kept in memory) and bounces the
   browser back to the Communications page with `?mail_connected=<provider>`.
5. User clicks **Sync** → `POST /api/events/{id}/mail/sync?provider=…` fetches
   recent inbox messages and runs each through `EmailAgentService.analyze_email`.

## 1. Register the OAuth apps

### Google (Gmail)
1. Google Cloud Console → create/select a project.
2. **APIs & Services → Library** → enable **Gmail API**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   (type: Web application).
4. Add the **Authorized redirect URI** — must equal `MAIL_OAUTH_REDIRECT_URI`,
   e.g. `https://<api-host>/api/mail/oauth/callback`.
5. On the OAuth consent screen, add the scope
   `https://www.googleapis.com/auth/gmail.readonly`.
6. Copy the **Client ID** and **Client secret** into `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`.

### Microsoft (Outlook)
1. Entra ID (Azure AD) → **App registrations → New registration**.
2. Redirect URI (Web): same `MAIL_OAUTH_REDIRECT_URI`.
3. **API permissions** → Microsoft Graph → delegated → `Mail.Read` and
   `offline_access`.
4. **Certificates & secrets** → new client secret.
5. Copy Application (client) ID and the secret into `MICROSOFT_CLIENT_ID` /
   `MICROSOFT_CLIENT_SECRET`. Set `MICROSOFT_TENANT_ID` (`common` or a specific
   tenant).

## 2. Set the environment variables

See `apps/api/.env.example` (Mail connection section). The key ones:

| Var | Purpose |
|-----|---------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Gmail OAuth app |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` / `MICROSOFT_TENANT_ID` | Outlook OAuth app |
| `MAIL_OAUTH_REDIRECT_URI` | Must match the registered redirect URIs exactly |
| `WEB_APP_URL` | Frontend base URL for the post-callback bounce |
| `MAIL_SYNC_MAX_MESSAGES` | Messages pulled per sync (default 20) |

A provider with empty id/secret shows as **Not configured** in the UI and is
simply skipped — the feature degrades gracefully.

## Security notes / production TODOs

This is a first iteration built around env-var configuration (no secrets in the
DB). Before using with real participant data, address the TODOs marked in
`apps/api/services/mail_connection_service.py`:

- **Token persistence**: access/refresh tokens are currently held **in process
  memory**, keyed by `(event_id, provider)`. They are lost on restart and not
  shared across API instances. Persist the refresh token in an encrypted store.
- **CSRF on `state`**: the OAuth `state` round-trips the event/provider/locale
  but is not yet signed. Sign/verify it to prevent callback forgery.
- **RGPD**: pulling a real mailbox ingests personal data — only enable after the
  RGPD validation noted in the root `README.md`.
