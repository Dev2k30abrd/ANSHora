# Anshora Analyst — Frontend (React + Vite)

Clean, Claude-style chat UI (serif answers, quiet sidebar, no model name shown) for the Anshora backend: live **analysis steps timeline**, **artifact side panel**
(profit impact, dashboards, sensitivity grids, SQL tables), **verification + confidence badge**,
Stop / Regenerate / Edit-and-rerun, follow-up chips, server-side chat history, projects, decision log,
monitors, alerts bell, data connectors and board-report export.

## Run locally

Start the backend first (see `backend/README.md`), then:

```bash
cd frontend
npm install
cp .env.example .env        # Windows: copy .env.example .env   (VITE_API_URL=http://127.0.0.1:8000)
npm run dev
```

Open http://localhost:5173 → **Create a workspace** → *Try sample data* (or upload a CSV) →
ask **"Where am I losing money?"**

Other commands: `npm run build` · `npm run lint` · `npm test` (render smoke tests) · `npm run preview`

If the backend runs on another host/port set `VITE_API_URL` in `.env` and add the frontend origin to the
backend's `CORS_ORIGINS`.

## Structure

```
src/
  App.jsx                    shell: auth, datasets, chats, panels, notifications
  services/api.js            axios client + SSE streaming (AbortController for Stop)
  components/
    ChatInterface.jsx        streaming chat, welcome money-snapshot, edit/regenerate/stop
    AssistantMessage.jsx     answer + steps + artifact cards + verification + follow-ups
    StepsTimeline.jsx        live tool-call timeline      VerificationBadge.jsx  proof popover
    ArtifactPanel.jsx        Claude-style result panel     ProfitImpact / SensitivityView / TableView
    panels/                  Profit, Decisions, Monitors, Connectors, Settings, Notifications + original panels
```
