# LeadFlow CRM — PRD

## Original problem statement
> "I want to create a application where i can freely send WhatsApp messages to students and then follow up using AI caller in native language and maintain dashboard for all lead status to follow up again manually and also clear cut dashboard where I can [see] all work going on lead enter till made into successful business."

## User choices (gathered)
- WhatsApp messaging: **MOCKED** for MVP
- AI Voice Caller: **MOCKED** for MVP
- Languages: **Hindi + English**
- Auth: **JWT-based custom auth**
- Pipeline: New → Contacted → Interested → Demo Scheduled → Negotiation → Enrolled / Lost

## Personas
- **Counsellor / Admission Sales Rep** — sends outreach, follows up, moves leads through stages, takes notes.
- **Admin / Owner** — monitors funnel & conversion analytics, oversees team activity.

## Architecture
- **Backend**: FastAPI + Motor (MongoDB), JWT cookies + Bearer fallback, bcrypt password hashing, pandas + openpyxl/xlsxwriter for Excel.
- **Frontend**: React 19 + React Router v7 + shadcn/ui + Tailwind + Recharts + sonner toasts. Manrope + IBM Plex Sans fonts.

## Implemented (Feb 2026)
- JWT auth (register, login, logout, /me) — admin seeded on startup (admin@leadflow.com / admin123).
- Leads CRUD: create, list (search + stage filter), detail, update, delete; auto stage advance on first outreach.
- **Bulk import via Excel/CSV** + .xlsx template download + .xlsx export of all leads.
- WhatsApp mock: 6 message templates (EN + HI), per-lead conversation stream, placeholder substitution.
- AI Caller mock: per-lead transcript reveal (animated), Hindi/English language toggle, call summary + outcome.
- Activity timeline per lead, manual notes.
- Pipeline Kanban: 7 columns, drag-and-drop to change stage.
- Dashboard: 4 KPI cards + funnel chart + recent leads list.
- Analytics: stage bar chart, source pie chart, daily new-leads line chart, conversion + win rate KPIs.

## Implemented (Jun 2026)
- **Bulk Outreach — multi-category selection:** the dialog now lets you pick **multiple stage groups at once** (checkbox grid with per-stage counts + "Select all/Clear all"); combined count preview. Backend bulk endpoints (`/bulk/whatsapp`, `/bulk/whatsapp-template`, `/bulk/calls`) accept a `stages: []` array (query via `$in`) while staying backward-compatible with single `stage`. Verified via curl + UI.
- **Integration Module — P2 polish:** Audit Logs paginated + provider/action filters; Health chart per-provider filter.
- **Integration Module — Phase 2 + P0 Meta templates** (57/57 tests):
  - Health Dashboard tab (status grid, last-verified, response time, last error, "Run all tests") + recharts response-time chart.
  - Audit Logs tab (masked old/new values, action badges, updated_by, IP).
  - Connection/version **history** (`GET /api/admin/integrations/history`) feeding the chart.
  - **Import/Export** config (`/export`, `/import`) — secrets exported in ENCRYPTED form (portable on same JWT_SECRET, never plaintext).
  - **P0 Meta-approved WhatsApp templates:** `GET /api/whatsapp/meta-templates` (fetch approved from Meta), `POST /api/leads/{id}/whatsapp-template`, `POST /api/bulk/whatsapp-template` (type:"template" send for cold first-touch outside 24h window). Wired into both the per-lead WhatsApp panel and Bulk Outreach (mode toggle + param mapping). NEEDS REAL META CREDS to deliver live — graceful 400 otherwise.
- **Integration Settings Module — Phase 1**: DB-backed encrypted credentials (Fernet), masked responses, DB→.env→empty priority with one-time .env auto-migration, admin-only APIs, 5 provider cards, .env never edited again.

## Backlog (prioritized)
- **P1** — verify Meta template + email + WhatsApp delivery live once real keys are entered.
- **P2** — pagination/filters on audit logs; per-provider response-time history view.
  - Integrations: status-only view (Configured / Not configured) for WhatsApp, FB/IG, Resend email, Meta verify, LLM. Keys stay in backend/.env per user choice.
  - Auto-search: search keywords (chips), RSS source URL templates ({q}), schedule interval (1–24h), enable toggle, auto-publish toggle — drives a background scheduler in social_posts.py.
  - Templates: WhatsApp templates (add/edit/delete, EN/HI) + AI call opening scripts (EN/HI), DB-backed and used by send/bulk/call endpoints.
  - Team: round-robin assignment toggle.
- **P1 features:** in-app follow-up reminders (Follow-ups page + Schedule dialog, overdue badges); role-based access (admin sees all, counsellor sees only own leads/tasks; admin-only Team/Settings nav); Team management (users CRUD); lead assignment + round-robin distribution; dedup on bulk import (phone, `dtype=str` preserves `+`); Email channel via Resend (LeadDetail Email tab; needs RESEND_API_KEY in .env).
- Cleaned a duplicated startup/router block in server.py.
- Verified: 21/21 backend tests pass; Settings UI rendered & functional.

## Implemented earlier (Jun 2026)
- **Bulk Outreach** (Leads page): single-stage-group bulk WhatsApp send (template-based) + bulk AI calls (EN/HI) via `POST /api/bulk/whatsapp` and `POST /api/bulk/calls`. Dialog shows live per-stage lead counts and a confirmation preview; auto-advances stages (mock send logic).

## Backlog (prioritized)
- **P0** — Real WhatsApp send (Twilio WhatsApp Business or Meta Cloud API).
- **P0** — Real AI Caller (Twilio Voice + ElevenLabs or OpenAI Realtime, with multilingual TTS/STT).
- **P1** — Scheduled follow-up tasks with email/in-app reminders.
- **P1** — Multi-user team with role-based access (admin vs counsellor scoped leads).
- **P1** — Lead assignment & round-robin distribution.
- **P2** — Webhook ingestion (incoming WhatsApp replies, missed calls).
- **P2** — Deduplication on phone during bulk import.
- **P2** — Email channel (SendGrid / Resend) parallel to WhatsApp.

## Test credentials
- See `/app/memory/test_credentials.md` (admin@leadflow.com / admin123).
