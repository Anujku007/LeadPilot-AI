<div align="center">

# ✦ LeadPilot AI

### An AI-Powered Sales Copilot & Intelligent CRM

**From the first customer conversation to lead qualification, consultation scheduling, and sales follow-up—all in one workspace.**

A student-led **AI/ML + full-stack engineering portfolio project** built with **React, FastAPI, NVIDIA AI, and PostgreSQL**.

[![Live App](https://img.shields.io/badge/Live%20App-Vercel-000000?style=for-the-badge&logo=vercel)](https://leadpilot-ai-ysmi.vercel.app/)
[![React](https://img.shields.io/badge/React-19-149ECA?style=for-the-badge&logo=react&logoColor=white)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![NVIDIA AI](https://img.shields.io/badge/NVIDIA-AI%20Services-76B900?style=for-the-badge&logo=nvidia&logoColor=white)](https://build.nvidia.com/)
[![Neon](https://img.shields.io/badge/Database-Neon%20PostgreSQL-00E599?style=for-the-badge)](https://neon.tech/)

**[🚀 Open Live Application](https://leadpilot-ai-ysmi.vercel.app/)** · **[View Screenshots](#-interface-preview)** · **[Architecture](#-system-architecture)** · **[Run Locally](#-getting-started)** · **[Project Presentation](docs/PROJECT_PRESENTATION.md)**

</div>

---

## 📌 Project overview

**LeadPilot AI** is a conversational sales-automation prototype that turns customer interactions into structured, actionable CRM records. Instead of stopping at an AI-generated response, it connects **conversation → BANT qualification → lead scoring → appointment proposal → explicit booking → salesperson follow-up → sales analytics**.

The application combines a modern chat interface with an administrator dashboard, a lead-assignment-based salesperson workspace, optional browser voice interactions, appointment management, and sales pipeline reporting.

> **Deployment status (November 2026):** The React frontend and FastAPI service have been deployed together on **Vercel**, with **Neon PostgreSQL** configured for persistent cloud storage. The sign-in page and administrator bootstrap have been exercised on the deployed site, and the latest frontend production build succeeded. **This is a publicly accessible portfolio MVP—not a production-ready, multi-tenant SaaS.** External AI, voice, and calendar features depend on service credentials and runtime availability; do not assume every integration has passed cloud end-to-end verification.

### 🔗 Project links

| Resource | Link |
| --- | --- |
| **Live website** | **https://leadpilot-ai-ysmi.vercel.app/** |
| **Source code** | [Anujku007/LeadPilot-AI](https://github.com/Anujku007/LeadPilot-AI) |
| **Developer** | [@Anujku007](https://github.com/Anujku007) |
| **Technical presentation** | [Project presentation notes](docs/PROJECT_PRESENTATION.md) |
| **Deployment checklist** | [Deployment readiness](docs/DEPLOYMENT_READINESS.md) |

> **Public-preview access:** The current login UI displays visitor credentials. Those credentials belong to a **shared administrator workspace**; users do **not** receive isolated accounts. Treat the live website as a demonstration environment only. Never enter real customer data or connect personal production calendars or business telephony credentials. The public credentials must be replaced with a restricted demo account before handling sensitive data. The password is intentionally **not duplicated in this README**.

---

<a id="interface-preview"></a>

## 🖼️ Interface preview

The screenshots below are from the repository's demonstration workspaces and may contain fictional/sample records. They are not proof that every integration is active in the hosted environment.

| Administrator: AI copilot and CRM | Salesperson: assigned leads and insights |
| :---: | :---: |
| ![LeadPilot AI administrator workspace showing conversations and CRM](docs/screenshots/admin-workspace.png) | ![LeadPilot AI salesperson workspace showing assigned leads and sales insights](docs/screenshots/sales-workspace.png) |

**Try the hosted sign-in experience:** [Launch LeadPilot AI on Vercel](https://leadpilot-ai-ysmi.vercel.app/).

---

## 🎯 The problem and solution

Sales teams often lose context between customer conversations, manual qualification notes, scheduling tools, and CRM spreadsheets. The resulting handoffs are repetitive and error-prone.

LeadPilot AI explores a unified approach:

- **Converse** with prospective customers through typed messages and optional browser speech.
- **Extract** Budget, Authority, Need, and Timeline (BANT) signals from what the customer actually said.
- **Evaluate** leads using deterministic, explainable business rules.
- **Persist** conversations, profiles, appointments, and outcomes in a relational CRM.
- **Schedule** consultations with availability checks and a separately confirmed booking action.
- **Assign and follow up** through role-restricted sales views and a tracked pipeline.
- **Analyze** unique opportunities, meeting outcomes, and agreed deal values.

### Representative workflow

```mermaid
flowchart TD
    A[Customer inquiry] --> B{Input channel}
    B -->|Text| C[Conversation service]
    B -->|Browser voice| D[Parakeet speech-to-text]
    D --> C
    C --> E[NVIDIA Nemotron response and BANT extraction]
    E --> F[Deterministic BANT scoring]
    F --> G[(CRM: conversation + lead)]
    G --> H{Lead ready for consultation?}
    H -->|Not yet| C
    H -->|Yes| I[Check calendar availability]
    I --> J[Create unbooked proposal]
    J --> K{Customer explicitly confirms?}
    K -->|No| L[No booking created]
    K -->|Yes| M[Create calendar event and CRM appointment]
    M --> N[Assign salesperson and record meeting outcome]
    N --> O[Pipeline, reminders and analytics]
```

> **Booking safeguard:** A proposed slot is **not** an appointment. The application only saves a real booking after explicit confirmation and a successful calendar operation. The hosted preview does not currently claim a separate simulated-calendar booking mode.

---

## ✨ Key features

| Area | Implemented capability | Scope / status |
| --- | --- | --- |
| **AI conversations** | Multi-turn customer conversations, CRM history, contextual replies through NVIDIA language models | Implemented; hosted results require a working NVIDIA configuration |
| **Browser voice** | Record a short message, review audio, transcribe with **NVIDIA Parakeet**, edit the transcript, and play **NVIDIA Magpie** speech | Browser/local integration; cloud voice availability must be verified |
| **Lead intelligence** | Extract structured BANT signals; score each lead against explicit rules | Implemented |
| **Lead management** | Saved conversations, lead profiles, custom labels, history and qualification progress | Implemented; persisted with SQLAlchemy |
| **Appointment scheduling** | Google Calendar availability, 30-minute IST slots, expiring proposals, explicit confirmation and retry-safe booking | Implemented and tested locally; cloud OAuth availability not guaranteed |
| **Sales pipeline** | Meeting completion, notes, follow-up, Won/Lost outcomes and sales activities | Implemented |
| **Sales analytics** | Opportunity counts, conversion-related metrics, follow-up views, agreed deal value | Implemented; illustrative demo figures are not earned revenue |
| **Role-based access** | Admin and salesperson sessions, assigned-lead restrictions and team management | Implemented in FastAPI; single shared CRM, not multi-tenant |
| **Cloud deployment** | React/Vite frontend and FastAPI application routed by Vercel; Neon PostgreSQL database | Deployed portfolio preview |
| **Telephone integration** | Separate Twilio-compatible gateway and local telephony experiments | Prototype only; no verified deployed real-time NVIDIA telephone agent |

### BANT scoring — transparent business rules

The language model extracts *structured evidence*; application code applies the score. The model does **not** autonomously decide which deal is won.

| Dimension | Signal | Points |
| --- | --- | ---: |
| **Budget** | Confirmed / Limited / Unknown | 25 / 10 / 0 |
| **Authority** | Decision-maker / Influencer / Unknown | 25 / 10 / 0 |
| **Need** | Clear / Partial / Unknown | 25 / 10 / 0 |
| **Timeline** | Within 30 days / Within 90 days / Later / Unknown | 25 / 15 / 5 / 0 |

**Classification:** `Incomplete` when required details are unknown; otherwise `Hot` ≥ 75, `Warm` 40–74, `Cold` < 40. The scores are **heuristic qualification signals**, not statistically calibrated purchase probabilities.

---

<a id="system-architecture"></a>

## 🏗️ System architecture

LeadPilot AI uses a React single-page application and a Python API, with service-to-service integrations handled on the backend. Local development defaults to SQLite, while the deployed configuration connects to Neon PostgreSQL.

```mermaid
flowchart LR
    Visitor[Browser / recruiter / operator]

    subgraph Vercel[Vercel deployment]
        UI[React 19 + Vite frontend]
        API[FastAPI serverless service]
        Auth[HTTP-only session authentication + RBAC]
        CRM[Conversation / CRM / BANT / Sales APIs]
    end

    Visitor -->|HTTPS| UI
    UI -->|/api and /health| API
    API --> Auth
    Auth --> CRM
    CRM --> PG[(Neon PostgreSQL)]
    CRM --> LLM[NVIDIA Nemotron]
    CRM --> ASR[NVIDIA Parakeet ASR]
    CRM --> TTS[NVIDIA Magpie TTS]
    CRM -.->|Configured OAuth only| Google[Google Calendar API]

    Local[Local Twilio gateway prototype] -.->|Separately run; not deployed as full voice agent| CRM
```

### Deployment routing

The repository's [`vercel.json`](vercel.json) defines two services:

| Request path | Target | Implementation |
| --- | --- | --- |
| `/` and frontend routes | `frontend` | React/Vite static application |
| `/api/*` | `app` | FastAPI entry point: `leadpilot_api:app` |
| `/health` | `app` | API health response |

The API uses **SQLAlchemy**, **Pydantic** validation, and **HTTPX** for external HTTP requests. PostgreSQL URLs use **Psycopg 3**, with connection pooling delegated to the hosted Neon service. Local SQLite remains supported for development.

### Data model (core relationships)

```mermaid
erDiagram
    lp_conversations ||--o{ lp_messages : contains
    lp_conversations ||--o| lp_leads : qualifies
    lp_conversations ||--o{ lp_appointments : books
    lp_conversations ||--o{ lp_appointment_proposals : proposes
    lp_conversations ||--o| lp_conversation_labels : names
    lp_auth_operators ||--o{ lp_auth_sessions : signs_in
    lp_auth_operators ||--o| lp_team_roles : has_role
    lp_auth_operators ||--o{ lp_lead_assignments : receives
    lp_conversations ||--o{ lp_lead_assignments : assigned_as
    lp_appointments ||--o| lp_sales_outcomes : produces
    lp_appointments ||--o{ lp_sales_activities : records
```

These are the application's SQLAlchemy table names and conceptual relationships; refer to the model definitions for exact constraints and key types.

---

## 🧰 Technology stack

| Layer | Technology | Role |
| --- | --- | --- |
| **Frontend** | React 19, JavaScript/JSX, Vite 7, Tailwind CSS 4, Lucide React | Responsive dashboard, chat, login, salesperson views |
| **Backend** | Python 3.11, FastAPI, Uvicorn, Pydantic | APIs, input validation, workflow orchestration |
| **LLM / AI** | NVIDIA API / Nemotron-family language model | Contextual replies and structured lead extraction |
| **Speech AI** | NVIDIA Parakeet, NVIDIA Magpie | Speech-to-text and text-to-speech |
| **ORM / local database** | SQLAlchemy 2, SQLite | Relational persistence for local development |
| **Cloud database** | Neon PostgreSQL, Psycopg 3 | Persistent hosted CRM/auth data |
| **Calendar** | Google Calendar API, OAuth 2.0 | Verified availability and deliberate bookings |
| **Telephony experiments** | Twilio, WebSocket-based prototype modules | Isolated phone-call experiments, not a deployed live agent |
| **Deployment** | Vercel | Hosted React app and FastAPI service |
| **Testing & release** | Python `unittest`, Vite build, release validation scripts, GitHub | Regression checks and source control |

---

## 📁 Project structure

The following tree highlights actual files and directories in the repository (selected implementation files are grouped for readability):

```text
LeadPilot-AI/
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx                     # React entry point
│       ├── AuthGate.jsx                 # Session check, sign-in, role routing
│       ├── App.jsx                      # Administrator CRM and AI workspace
│       ├── TeamAdminPanel.jsx           # Sales accounts and lead assignments
│       ├── TeamSalesWorkspace.jsx       # Assigned salesperson workspace
│       ├── SalesPipelinePage.jsx        # Pipeline management
│       ├── SalesInsightsPanel.jsx       # Sales analytics UI
│       ├── CalendarBookingPicker.jsx    # In-chat slot picker
│       ├── ChatBookingCard.jsx          # Explicit confirmation card
│       ├── VoicePlayground.jsx          # Browser voice experience
│       ├── VoiceReviewPanel.jsx         # Recording/transcript review
│       ├── api.js                       # API client helpers
│       ├── browserAudio.js              # Browser audio utilities
│       ├── utils.js                     # Formatting and shared UI helpers
│       └── *.css                        # Scoped and shared styles
├── leadpilot_ai/
│   ├── auth_api.py                       # Password hashing and session cookies
│   ├── team_access.py                    # Role permissions and lead scoping
│   ├── crm_store.py                      # SQLAlchemy models and DB connection
│   ├── conversation_api.py               # CRM-backed chat operations
│   ├── nvidia_llm_service.py             # NVIDIA language model client
│   ├── nvidia_asr_service.py             # Parakeet transcription
│   ├── nvidia_tts_service.py             # Magpie speech generation
│   ├── lead_extraction.py                # AI-assisted structured BANT extraction
│   ├── lead_qualification.py             # Deterministic BANT scoring
│   ├── qualification_flow.py             # Stateful qualification behavior
│   ├── calendar_availability.py          # Available calendar slots
│   ├── appointment_booking.py            # Booking with confirmation checks
│   ├── appointment_confirmation.py       # Proposals and confirmation
│   ├── natural_language_scheduling.py    # Spoken/text date interpretation
│   ├── dashboard_api.py                  # CRM dashboard endpoints
│   ├── sales_pipeline_api.py             # Outcomes and activities
│   ├── sales_insights_api.py              # Sales summary metrics
│   ├── voice_api.py                      # Browser voice endpoints
│   └── twilio_*.py                       # Local telephony experiments
├── scripts/
│   ├── create_leadpilot_admin.py         # One-time local admin setup
│   ├── auth_smoke_tests.py               # Auth verification
│   ├── release_verify.py                 # Release/security checks
│   └── release_publish.ps1
├── tests/                                # Python regression test modules
├── docs/
│   ├── screenshots/
│   │   ├── admin-workspace.png
│   │   └── sales-workspace.png
│   ├── DEPLOYMENT_READINESS.md
│   ├── PROJECT_PRESENTATION.md
│   └── RELEASE_CHECKLIST.md
├── prompts/                              # AI prompts and sample scenarios
├── static/                               # Legacy local HTML tools
├── leadpilot_api.py                      # FastAPI app / health / routers
├── leadpilot_twilio_gateway.py           # Separate optional gateway
├── connect_google_calendar.py           # Local OAuth utility
├── requirements.txt                     # Lean Vercel dependencies
├── requirements-local.txt               # Extended local dependencies
├── .env.example                          # Empty secret placeholders
├── vercel.json                           # Vercel multi-service routing
├── LICENSE
└── README.md
```

---

<a id="getting-started"></a>

## 🚀 Getting started

### Prerequisites

- **Python 3.11** (recommended for this project) and **Node.js/npm**.
- A valid **NVIDIA API key** and an enabled NVIDIA model for live chat.
- Optional Google Calendar OAuth credentials for real booking functionality.
- Local **SQLite** is the default. Set `LEADPILOT_DATABASE_URL` for PostgreSQL/Neon.

### 1. Clone and install

```powershell
git clone https://github.com/Anujku007/LeadPilot-AI.git
cd LeadPilot-AI

py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd frontend
npm.cmd ci
cd ..
```

`npm.cmd` avoids Windows PowerShell's common `npm.ps1` execution-policy error. Some **local-only** voice/telephony experiments use additional packages from `requirements-local.txt`.

### 2. Set environment variables

Copy the template and add **your own** credentials locally:

```powershell
Copy-Item .env.example .env
```

Example entries (values below are placeholders, never real secrets):

```dotenv
NVIDIA_API_KEY=YOUR_NVIDIA_API_KEY
NVIDIA_MODEL=YOUR_ENABLED_NVIDIA_MODEL
# NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# Optional: SQLite is used when this variable is omitted.
# LEADPILOT_DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require

# For your HTTPS host, specify the exact origin.
LP_AUTH_ORIGINS=http://127.0.0.1:5173
LP_AUTH_COOKIE_SECURE=false
```

For a Vercel deployment, store actual values in **Vercel Project Settings → Environment Variables**, not in Git. Use the production URL for `LP_AUTH_ORIGINS` and `LP_AUTH_COOKIE_SECURE=true` over HTTPS. Never expose the database URL, NVIDIA API key, Google OAuth token, or Twilio credentials to frontend code.

### 3. Create a local administrator

In the repository root:

```powershell
& .\.venv\Scripts\python.exe .\scripts\create_leadpilot_admin.py
```

The CLI prompts for a **username and a strong password (12–128 characters)**; the current application does **not** provide public email registration. The command initializes an account in whichever database the environment selects. Do **not** point this command at a production database unless that operation is intentional.

### 4. Start the backend and frontend

**Terminal 1 — FastAPI**

```powershell
& .\.venv\Scripts\python.exe -m uvicorn leadpilot_api:app --host 127.0.0.1 --port 8001 --reload
```

**Terminal 2 — React/Vite**

```powershell
cd frontend
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. The development proxy forwards `/api` and `/health` to FastAPI on port `8001`.

For a quick backend check, visit **http://127.0.0.1:8001/health**. The optional Twilio gateway is a separate service and is not necessary for the main chat or CRM.

---

## ☁️ Hosting on Vercel + Neon

The project uses [Vercel's multi-service configuration](vercel.json): the frontend is built from `frontend/`, while FastAPI is served from `leadpilot_api:app`. The hosted database is **Neon PostgreSQL**, selected through `LEADPILOT_DATABASE_URL`.

**Configuration checklist:**

1. Connect the GitHub repository to a Vercel project that supports the included `vercel.json` service configuration.
2. Provision a Neon PostgreSQL database and keep its connection URL private.
3. Configure the backend environment: `LEADPILOT_DATABASE_URL`, `NVIDIA_API_KEY`, `NVIDIA_MODEL`, and any optional integration variables.
4. Set `LP_AUTH_ORIGINS` to **`https://leadpilot-ai-ysmi.vercel.app`** and `LP_AUTH_COOKIE_SECURE=true` for the current production domain.
5. Bootstrap the administrator account in the **same** Neon database used by Vercel.
6. Deploy and verify sign-in, `/health`, persistence, permissions, AI availability, and any integrations you intend to demonstrate.

> **Windows note:** Some managed Windows configurations block Psycopg's native DLLs. That affects local PostgreSQL administration, not necessarily the hosted Vercel runtime. A separately verified TLS-enabled `pg8000` helper was used for the one-time Neon admin bootstrap; it is not part of this tracked repository. Do not disable operating-system security protections to make a database driver load.

**Current live preview:** **[leadpilot-ai-ysmi.vercel.app](https://leadpilot-ai-ysmi.vercel.app/)**.

---

## 🧪 Testing and verification

```powershell
# From the repository root, with your local environment installed
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_leadpilot_*.py' -q

# Optional focused authorization checks
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_leadpilot_auth.py' -q
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_leadpilot_team_access.py' -q

# Release scan (review instructions before using --full)
& .\.venv\Scripts\python.exe .\scripts\release_verify.py --staged-scan

# Frontend production build
cd frontend
npm.cmd run build
```

**Verification record:** an earlier local regression run reported **150 passing Python tests**. The **frontend Vite production build also passed on 24 November 2026** after the responsive-login update. This README does **not** claim that the entire current backend regression suite or every hosted AI/calendar endpoint was re-tested at this revision.

Test modules cover authentication, team access, BANT logic, chat/dashboard behavior, calendar proposals and booking, sales outcomes, voice endpoints, and isolated Twilio gateway behavior. See [`tests/`](tests/) and [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md).

---

## 🔐 Security, data protection, and honest limitations

- **Public access is not equivalent to data isolation.** The current Vercel login page exposes credentials for a **shared administrator account**. Visitors can access and change the same workspace. This is acceptable only as an intentionally public, synthetic-data prototype—not a secure recruiter sandbox or multi-tenant SaaS.
- **Avoid real customer information.** Do not place personal leads, live customer conversations, private credentials, or sensitive calendar integrations in the public preview. Replace publicly shared administrator credentials with a restricted sandbox account and isolate its database before any wider real-world use.
- **Role-based authorization:** admin and salesperson roles are enforced by backend session checks. Salespeople are limited to explicitly assigned leads, but ordinary public visitor accounts and separate organization workspaces are **not implemented**.
- **Session design:** password hashing and HTTP-only session cookies are implemented. Production hardening still needs a thorough security review, cross-instance rate limiting, audit logs, monitoring, backups, and privacy controls.
- **Booking safety:** proposal and confirmation are separate. Live Google Calendar bookings require functioning OAuth credentials; don't imply that an event was created unless the API confirms it.
- **Browser voice:** microphone access requires consent and browser support. Voice services can fail independently due to network, provider, or deployment limitations.
- **Telephony:** a complete live NVIDIA-driven phone-call agent has **not** been deployed. Twilio gateway modules are isolated experimental/prototype paths.
- **Sales metrics:** pipeline value represents operator-entered **agreed deal value**, not payment collection or audited revenue.
- **Follow-up reminders:** the browser observer requires the workspace to remain open; unattended scheduled email/SMS follow-ups are not provided.

For the remaining production work, see [`docs/DEPLOYMENT_READINESS.md`](docs/DEPLOYMENT_READINESS.md). That document still contains older localhost-era status language; the live hosting status is updated here, but deployment hardening tasks remain relevant.

---

## 🗺️ Roadmap

- [ ] Replace public administrator credentials with a dedicated restricted recruiter demo and isolated sample database.
- [ ] Verify production AI chat, speech, CRM, and calendar integrations end to end.
- [ ] Introduce safe simulated calendar booking for public demonstrations, separate from real Google Calendar actions.
- [ ] Implement first-class user/organization isolation if evolving into SaaS.
- [ ] Add usage quotas, distributed rate limiting, observability, audit trails, and recovery/backups.
- [ ] Improve deployment-safe OAuth credential handling and privacy/data lifecycle controls.
- [ ] Validate real-time NVIDIA-connected telephony before advertising it as available.

---

## 👤 Developer, acknowledgments, and license

**Developer & maintainer:** [@Anujku007](https://github.com/Anujku007)

LeadPilot AI is a student-led personal AI/ML and full-stack project. The work represented here includes the product workflow, React interfaces, FastAPI integration, conversational AI and speech integration, BANT/CRM logic, scheduling safeguards, authentication and role-based views, and testing. It integrates third-party frameworks and services; no claim is made that every dependency or inherited component was authored from scratch.

The project incorporates/adapts initial scaffolding and some legacy Twilio-oriented material from [Starter Agent — Inbound/Outbound Twilio Speech Assistant](https://github.com/aymalkhalid/Starter-Agent-InBound-OutBound-Twilio-Speech-Assistant-OpenAi-Realtime-Api-Python). The repository retains its existing [MIT LICENSE](LICENSE), including the original copyright notice. Third-party models, SDKs and APIs remain subject to their respective licenses and terms.

<div align="center">

**Built to demonstrate how AI conversations become actionable sales workflows.**

[**🌐 Live App**](https://leadpilot-ai-ysmi.vercel.app/) · [**💻 GitHub**](https://github.com/Anujku007/LeadPilot-AI)

</div>
