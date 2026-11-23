# LeadPilot AI — Deployment readiness (next milestone)

**Deployment has not been performed.** The current system is designed and tested primarily for localhost, using local SQLite, browser microphone input, Google Calendar OAuth and two separate backend services.

## Must address before exposing to the internet

- Decide hosting topology: one HTTPS domain for the React app and a reverse-proxied API; avoid public Vite development servers.
- Set production cookie flags (`Secure`, `HttpOnly`, `SameSite`) and exact `LP_AUTH_ORIGINS`; verify login, logout, session expiry and CSRF/origin defenses behind the reverse proxy.
- Audit **all** API and WebSocket routes for role authorization, including team CRUD, direct conversation IDs, audio endpoints, sales outcomes, admin views, `docs/openapi`, and the separate Twilio gateway.
- Store NVIDIA keys, Google OAuth credentials and Twilio secrets in the hosting platform's secret manager; never commit `.env` or raw tokens.
- Plan Google OAuth desktop-vs-server credentials and calendar account authorization carefully. Keep calendar bookings explicitly confirmed.
- Choose persistent storage and backup/restore strategy. SQLite on ephemeral server filesystem is unsafe; plan persistent volume or database migration and controlled migrations.
- Add request limits, file size limits, HTTPS and trusted proxy config, rate limiting across workers, monitoring, structured logs and incident alerting.
- Implement data privacy, customer consent for voice, retention/deletion, and organization access controls suitable for actual CRM data.
- Verify background follow-up behavior: current reminders only poll while a browser is open; no unattended notifications will arrive after browser closure.
- Assess Twilio callback exposure/signature verification and public base URLs separately. Full real-time NVIDIA telephony is not claimed.
- Run production end-to-end tests using synthetic records; validate logout/403/401, booking race/idempotency, voice response, and rollback.

## Practical phased rollout

1. **Demo hosting:** authenticated single-organization preview with synthetic data, SSL, and restricted API access.
2. **Private beta:** persistent database, secure domain, admin/test-sales accounts, calendar sandbox, diagnostics and backups.
3. **Production:** privacy, security audit, monitoring, test automation, operational runbook, supported regions and service budgets.

The planned `v1.0.0` tag represents a **local portfolio MVP release**, not public production readiness.
