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
- **Integration Settings Management Module (Phase 1)** — enterprise credential management, DB-backed, no .env edits after deploy:
  - MongoDB collections `integration_settings`, `integration_meta`, `integration_audit_logs`.
  - Fernet encryption (key derived from JWT_SECRET); secrets always masked in API responses.
  - Config priority DB → .env → empty; one-time .env→DB auto-migration on first startup.
  - Admin-only APIs: `GET/POST /api/admin/integrations`, `/test`, `/rotate-secret`, `DELETE /{provider}`, `/health`, `/audit`.
  - 5 providers: WhatsApp, Facebook, Instagram, Email (Resend), AI (OpenAI/Gemini/Claude/Groq/Emergent) — each with Save, Test Connection, status badge (🟢🟡🔴⚪), show/hide/copy/rotate secrets, last-verified/updated-by.
  - WhatsApp send + Resend email now read credentials from DB (graceful mock/400 fallback when unconfigured; never crashes).
  - Frontend: Settings → Integrations tab = responsive per-provider cards (`IntegrationsManager.jsx`).
  - Verified: 20/20 module tests + 21/21 regression pass.
- **Dashboard "Today's follow-ups" widget**, **Real WhatsApp send wiring** (DB creds), and earlier Settings/P1 work.

## Backlog (prioritized)
- **P1 — Integration Module Phase 2:** Health Dashboard UI tab, Audit Logs UI, Import/Export config, Version/Connection history, response-time monitoring chart.
- **P0** — Meta-approved WhatsApp template messages (for cold first-touch outside 24h window).
- **P0** — Real WhatsApp send (Twilio WhatsApp Business or Meta Cloud API).
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
