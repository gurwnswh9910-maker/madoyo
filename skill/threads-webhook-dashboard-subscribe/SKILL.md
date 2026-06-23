---
name: threads-webhook-dashboard-subscribe
description: Connect a Threads app to an HTTPS webhook endpoint through the Meta Developers Dashboard when a user has already logged into Chrome and provides the app Dashboard or Use Cases URL. Use for Meta/Threads webhook subscription work, especially replies webhook setup, localtunnel or cloud callback verification, Dashboard-only subscription flows, and handoff-safe evidence capture without exposing verify tokens, app secrets, or access tokens.
---

# Threads Webhook Dashboard Subscribe

## Core Contract

Use this skill when the user says they have opened a logged-in Chrome window for a Meta Developers app and gives the URL. The job is to connect that app's Threads Webhooks `replies` topic to an existing HTTPS callback endpoint, then leave evidence another agent can trust.

Treat this as a live account/browser operation. Do not open OAuth login URLs, do not change app mode, do not create permissions requests, and do not touch unrelated Meta settings. Work only inside the user-provided app.

## Secret Rules

- Never print, screenshot, commit, or summarize the verify token, app secret, access token, page access token, or long-lived token.
- It is usually acceptable to store placeholder Dashboard URLs and app IDs in a private repo, but do not store a live verify token. App IDs and business IDs are identifiers, not credentials, but still avoid putting them in public docs unless necessary.
- A callback URL is not a secret, but a live localtunnel/ngrok URL is public and temporary. Put it in local run status files when needed; use placeholders in reusable repo docs.
- Do not capture screenshots while the verify token is visible in an input field. If this happens by accident, delete the screenshot immediately and take a new after-save screenshot.

## Required Inputs

Confirm or discover these before touching the Dashboard:

- User-provided Meta Developers URL for the exact app.
- HTTPS callback URL, for example from a runtime JSON or cloud deployment output.
- Verify token from local/cloud environment, never from chat unless the user intentionally provides it.
- Local receiver or cloud endpoint that responds to Meta challenge requests.

For the Madoyo local receiver, common locations are:

- Receiver: `D:\madoyo\tools\threads_webhook_receiver.py`
- Local tunnel starter: `D:\madoyo\tools\start_threads_webhook_localtunnel.ps1`
- Runtime JSON: `D:\산출물\안전\threads_webhook_moderation_YYYYMMDD\threads_webhook_localtunnel_runtime.json`
- Verify token env key: `THREADS_WEBHOOK_VERIFY_TOKEN`

If any path differs, search for `threads_webhook_receiver.py`, `start_threads_webhook_localtunnel.ps1`, and `THREADS_WEBHOOK_VERIFY_TOKEN`.

## Preflight

1. Verify the receiver/tunnel or cloud endpoint is alive.
2. Send a Meta challenge probe before opening or saving anything:

```powershell
$callbackUrl = "<https callback url>"
$verifyToken = "<read from env; do not print>"
$challenge = "probe-" + (Get-Date -Format "yyyyMMddHHmmss")
$uri = $callbackUrl + "?hub.mode=subscribe&hub.verify_token=" + [uri]::EscapeDataString($verifyToken) + "&hub.challenge=" + [uri]::EscapeDataString($challenge)
$r = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 20
[pscustomobject]@{ status=[int]$r.StatusCode; body_matches=($r.Content -eq $challenge) } | ConvertTo-Json -Compress
```

3. Continue only if status is `200` and `body_matches` is `true`.
4. Check that the browser is already logged into the intended Meta account. If login is missing, ask the user to log in; do not collect credentials.
5. Identify the app id and app name from the URL/page. Do not assume the current app is the same as a previous run.

## Dashboard Flow

Use visual/browser control cautiously. If using Computer Use or OS-level input, keep clicks scoped to the visible Meta Dashboard window.

Preferred Dashboard path:

1. Open or focus the user-provided app URL.
2. Enter the app's Threads API use case customization page.
   - Korean UI labels may include `이용 사례`, `맞춤 설정`, `이 이용 사례에 더 추가`, `Threads를 사용한 Webhooks`.
   - English UI labels may include `Use cases`, `Customize`, `Add more to this use case`, `Get real-time notifications with Threads Webhooks`.
3. Add the Threads Webhooks sub-use-case if it is not already present.
4. Open the Threads Webhooks settings area.
5. Click `Subscribe to this object` or the equivalent edit/subscribe button.
6. Enter:
   - Callback URL: the verified HTTPS callback URL.
   - Verify token: the env/token value, without exposing it in chat or screenshots.
7. Save.
8. Confirm the table shows `replies` with an `Unsubscribe` button. This is the Dashboard evidence that `replies` is subscribed.
9. If `delete` also shows `Unsubscribe`, record it as observed. Do not unsubscribe it unless the user explicitly asks.

Do not repeat old Graph API `POST /{app_id}/subscriptions` attempts if Dashboard subscription is available. Threads Webhooks may not mirror cleanly through the legacy `/subscriptions` read surface; use Dashboard state plus live event delivery as operating evidence.

## Evidence To Leave

After saving, run the challenge probe again. Then create a local status JSON under a safe output directory. Include only non-secret evidence:

```json
{
  "checked_at_kst": "YYYY-MM-DDTHH:MM:SS+09:00",
  "app_id": "<app id>",
  "app_name": "<app name>",
  "dashboard_result": "subscribed",
  "callback_url": "<callback url or redacted if committing>",
  "callback_challenge_after_subscribe": {
    "status": 200,
    "body_matches_challenge": true
  },
  "subscribed_fields_seen_in_dashboard": ["delete", "replies"],
  "intended_live_field": "replies",
  "apply_hide": false,
  "require_signature": true,
  "next_verification": "Create or wait for a real Threads reply event and confirm a new row is appended to the webhook event log."
}
```

If updating shared repo docs, use placeholders for callback URL and omit tokens. If updating a local KB/run note, a live callback URL is acceptable when it is needed for operations, but never include the verify token.

Safe screenshot rule:

- Capture only the post-save state where fields like `replies` show `Unsubscribe`.
- Save screenshots under the run output directory, not in reusable skill docs.
- Delete any screenshot that includes a token input field.

## Completion Criteria

Report success only when all are true:

- Pre-save challenge returned `200` and matched the challenge.
- Dashboard save completed without error.
- Dashboard shows `replies` as `Unsubscribe`.
- Post-save challenge returned `200` and matched the challenge.
- Status JSON and optional after-save screenshot were saved.

Call out remaining work clearly:

- A real Threads reply/test event still needs to arrive before live delivery is proven.
- Report-only moderation stays safer until account/post/token mapping is confirmed.
- Auto-hide should stay off unless the user explicitly asks and the mapping has been verified.

## Failure Handling

- If the callback challenge fails, stop and fix the endpoint first.
- If the Dashboard cannot be operated because browser control is blocked, tell the user the exact visible page and next click needed.
- If Meta shows an OAuth/login screen, stop and ask the user to log in.
- If Graph API subscription reads return an empty list after Dashboard success, do not treat that alone as failure. Prefer Dashboard `Unsubscribe` state and live event log evidence.
- If the UI language differs, search the page for Webhooks, Threads, Subscribe, replies, callback, or verify token equivalents.
