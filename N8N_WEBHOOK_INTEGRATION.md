# Lucentive Club — n8n Welcome Webhook Integration

## Purpose

This webhook triggers a new welcome conversation for a lead on WhatsApp.
It is called by the backend whenever a `/reset` command is processed (dev mode),
but can also be called directly by any external system (CRM, landing page, ad platform)
to kick off the welcome flow for a brand-new lead.

---

## Endpoint

| Field  | Value |
|--------|-------|
| Method | `POST` |
| URL    | `https://wlog.app.n8n.cloud/webhook/lucentiveclub-production-welcome-lead` |

---

## Headers

| Header         | Value              |
|----------------|--------------------|
| `Content-Type` | `application/json` |

No authentication headers are required — the webhook URL itself is the secret.
Do not share it publicly.

---

## Request Body

The body must be a **JSON array** containing **one object** with the lead's details.
Wrap the object in `[…]` — n8n expects an array even for a single lead.

```json
[
  {
    "full_name": "John Smith",
    "phone_number": "+15551234567",
    "email": "john.smith@example.com",
    "country": "Canada",
    "investment_goal": "saving_for_the_future"
  }
]
```

### Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `full_name` | string | Yes | Lead's full name as it should appear in the conversation. |
| `phone_number` | string | Yes | WhatsApp-reachable number in E.164 format (e.g. `+15551234567`). This is used to identify and message the lead. |
| `email` | string | Yes | Lead's email address. |
| `country` | string | Yes | Lead's country name in English (e.g. `"Australia"`, `"Canada"`, `"United Kingdom"`). Used by the onboarding agent to recommend the correct bots and brokers. |
| `investment_goal` | string | No | Reason for investing. Defaults to `"saving_for_the_future"` if omitted. |

### `investment_goal` known values

The field is a free string, but the default value seen in production is:

| Value | Meaning |
|---|---|
| `saving_for_the_future` | Default — used when the source system does not specify a goal. |

If your lead source captures a different goal (e.g. from a form dropdown), pass it through
as-is; the n8n workflow will receive whatever string you send.

---

## Example — curl

```bash
curl -X POST \
  "https://wlog.app.n8n.cloud/webhook/lucentiveclub-production-welcome-lead" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "full_name": "Maria Garcia",
      "phone_number": "+447911123456",
      "email": "maria@example.com",
      "country": "United Kingdom",
      "investment_goal": "saving_for_the_future"
    }
  ]'
```

## Example — Python

```python
import httpx

payload = [{
    "full_name": "Maria Garcia",
    "phone_number": "+447911123456",
    "email": "maria@example.com",
    "country": "United Kingdom",
    "investment_goal": "saving_for_the_future",
}]

response = httpx.post(
    "https://wlog.app.n8n.cloud/webhook/lucentiveclub-production-welcome-lead",
    json=payload,
    timeout=10.0,
)
response.raise_for_status()
```

## Example — JavaScript (fetch)

```js
await fetch(
  "https://wlog.app.n8n.cloud/webhook/lucentiveclub-production-welcome-lead",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify([
      {
        full_name: "Maria Garcia",
        phone_number: "+447911123456",
        email: "maria@example.com",
        country: "United Kingdom",
        investment_goal: "saving_for_the_future",
      },
    ]),
  }
);
```

---

## Notes

- **Phone number format:** Always use E.164 format with the `+` prefix and country code.
  The number must be reachable on WhatsApp, as the n8n workflow sends the opening message there.
- **Country name:** Use the full English country name. The onboarding agent maps this to
  available bots and brokers, so spelling matters (e.g. `"Australia"` not `"AUS"`).
- **One lead per call:** Send one object per POST. Do not batch multiple leads in the same array.
- **What n8n does with this data:** n8n sends Perry's welcome message to the lead on WhatsApp
  and registers the lead so the AI agent can handle the reply when it arrives.
