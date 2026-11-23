# LeadPilot AI — Student Project Presentation Notes

**Project:** LeadPilot AI — NVIDIA-Powered AI Sales Copilot
**Developer / maintainer:** [@Anujku007](https://github.com/Anujku007)
**Type:** Personal AI/ML and full-stack portfolio project (local working prototype)

## Project objective

Build a conversational AI assistant that helps sales teams qualify leads, record customer requirements, book consultations only with explicit confirmation, and manage follow-ups and sales outcomes through an integrated CRM.

## The problem

Sales teams often spend time on repetitive qualification questions and manually transferring customer information to spreadsheets. Important requirements get lost, follow-up reminders are missed, and scheduling requires repeated back-and-forth.

## My proposed solution

LeadPilot AI links the stages of a sales process in one system:

**Customer inquiry → Speech-to-text / typed chat → AI conversation → BANT extraction and scoring → Persistent CRM → Calendar availability → Explicit booking → Salesperson handoff → Meeting notes → Follow-up / Won / Lost → Analytics**.

## 90-second pitch

> LeadPilot AI is my personal AI/ML and full-stack project for sales qualification and follow-up management. The problem I wanted to address is that a sales team may spend a lot of time asking basic questions, manually tracking leads, and arranging meetings. I developed an integrated workspace that uses NVIDIA AI to converse with a potential customer, transcribe voice, generate spoken responses, and extract information using the BANT framework: Budget, Authority, Need and Timeline. These details are saved in a CRM, and the application gives each lead a qualification score. A qualified lead can view available Google Calendar slots and explicitly confirm a consultation. After a meeting, a salesperson can record notes and mark the opportunity as Follow-up Required, Won or Lost. I also added admin and salesperson authentication, lead assignments, and analytics. I tested the local application using automated Python tests and a React production build. My contribution is the connected end-to-end workflow and the application around the AI services; this is a working local MVP rather than a fully deployed enterprise product.

## Live demonstration (5–8 minutes)

1. **Admin sign-in:** Show protected dashboard and existing demo leads. Explain that direct unauthenticated CRM API requests return 401.
2. **Role-based access:** Show a salesperson account with only assigned test leads; explain backend-enforced access restrictions.
3. **New conversation:** Start a new chat. A database record is created only after the first message, not simply by opening the page.
4. **AI qualification:** Use a fictional prospect with a ₹70,000 budget, owner approval, CRM follow-up needs, and a three-week implementation timeline. Show BANT score 100/100 when all information is extracted.
5. **Optional voice:** Record a short response, stop, preview audio, transcribe, correct any misheard words, then send. Play the AI's spoken response. Have a typed-message fallback in case the external service is unavailable.
6. **Calendar:** Check live availability; show a proposal. Only click **CONFIRM BOOKING** if you are intentionally creating a test event in the connected calendar.
7. **Sales pipeline:** Show a previously completed **demo** appointment and its meeting notes. Demonstrate Follow-up Required, Won, or Lost and explain that revenue figures are agreed deal values, not actual payments.
8. **Analytics:** Show how two appointments for one conversation are counted as one opportunity. Show due/upcoming follow-up reminders.
9. **End with boundaries:** This is a local portfolio MVP; live NVIDIA-driven Twilio telephone calls and production cloud deployment are not complete.

## Main engineering modules

| Component | Technology and responsibility |
| --- | --- |
| Interface | React + Vite, admin and assigned salesperson workspaces |
| Server | Python + FastAPI for API orchestration |
| LLM | NVIDIA Nemotron for conversation and structured extraction |
| Speech | NVIDIA Parakeet ASR and NVIDIA Magpie TTS |
| CRM | SQLAlchemy + SQLite; persistent conversations and lead profiles |
| Rules | Deterministic BANT scoring and lead categories |
| Booking | Google Calendar API, available slots, proposals and explicit confirmation |
| Authentication | Session cookies, password hashing, backend admin/sales permission checks |
| Pipeline | Meeting notes, Won/Lost/Follow-up outcomes, deduplicated opportunity counts |
| Quality | Python regression tests, isolated test DB, Vite production build |

## What makes my implementation useful

- It is an **end-to-end workflow**, not just an LLM chat response.
- BANT extraction becomes **structured, persistent CRM information**.
- Calendar actions require **verifiable availability and explicit confirmation**.
- Sales outcomes and won values belong to **unique opportunities** rather than duplicate appointment counts.
- The salesperson workspace enforces **assigned-lead permissions on the server**.
- Voice transcription is **reviewable and editable** before sending.

## Honest scope and results

In November 2026, the local release check reported **150 passing Python tests** and a successful React build. The voice/chat and calendar paths were tested in a local Windows environment, including a booked test consultation. The project is not yet hosted as a production SaaS. Browser follow-up notifications require the workspace to be open. A real NVIDIA-powered Twilio telephone call is not deployed. Demo monetary values are not verified received payments.

## Likely questions and answers

**Q: Why is this better than a normal chatbot?**
A: It turns conversational details into a saved CRM profile, calculates qualification, and connects the result to a confirmed appointment and sales pipeline.

**Q: Does the model decide which deal is won?**
A: No. A salesperson records meeting outcomes. BANT scoring uses explicit application rules on extracted fields.

**Q: Could the AI accidentally book a meeting?**
A: A proposal is separate from a real event. Booking requires explicit confirmation and a successful calendar call.

**Q: How are duplicate deals avoided?**
A: Multiple appointments under the same CRM conversation are represented as one sales opportunity in pipeline totals.

**Q: How is customer information protected?**
A: The local app has login and backend-enforced admin/sales permissions. Production deployment still needs HTTPS, secret management, CSRF/origin review, operational monitoring, backup, and a more thorough security audit.

**Q: What is your individual contribution?**
A: I shaped the LeadPilot AI problem and user journey; built and integrated the React interface and FastAPI workflows; connected AI conversation and speech services, BANT qualification, CRM, scheduling, authentication, and sales analytics; and validated them as a cohesive local demonstration. The project also uses existing libraries and some starter scaffolding, which is credited in the README and retained MIT license.

## Attribution and academic integrity

LeadPilot AI is presented as a **student-led personal implementation**, not as an assertion that every library or inherited starter component was written from scratch. The project retains the original MIT copyright notice and acknowledges adapted starter scaffolding. If submitting for course assessment, follow the institution's policies about source reuse and AI-assisted development.
