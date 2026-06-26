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
