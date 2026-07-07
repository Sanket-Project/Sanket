# SANKET — Decouple & Restructure Plan

_Generated 2026-06-28. Nothing is executed until you approve. All "removals" are **moves into `archive/`**, so everything is reversible (and stays in git history)._

## Goal
Cut this local copy loose from production and GitHub, get it building/running cleanly on the local laptop, and reorganize the folder. You will handle the actual teardown of live cloud resources and the GitHub repo yourself.

---

## Current state (what I found)
- **Local dev is already decoupled at runtime.** `backend/.env` is `APP_ENV=development` → `localhost:5432` Postgres + `localhost:6379` Redis. `frontend/.env.local` disables Firebase and routes the API through the Vite proxy to the local backend. So `start-dev.bat` / `docker-compose` run fully local already.
- **Production coupling** lives in: `firebase.json`, `.firebaserc` (project ID — to be set once the new Sanket Firebase project is created), `backend/cloudrun-env.yaml`, `backend/.gcloudignore`, `infra/kubernetes/overlays/production/`.
- **GitHub coupling**: git remote `origin → github.com/baltejgoud/sanket-project.git`; CI/CD in `.github/workflows/` (backend-ci, frontend-ci, ml-ci, build-images, deploy, security). `build-images` → GHCR on push to main; `deploy` → k8s staging/production.
- **Security flag**: `backend/firebase-credentials.json` is a real service-account key in the working tree (not git-tracked). Recommend rotating/revoking after we move it out.
- **Uncommitted work**: 3 modified tracked files + 1 untracked PDF — will be left untouched.

---

## 1. Decouple from production (reversible)
Move into `archive/prod-config/`:
- `firebase.json`, `.firebaserc`
- `backend/cloudrun-env.yaml`, `backend/.gcloudignore`
- `infra/kubernetes/overlays/production/` (keep `base/` and `staging/`)

Move out of tree into `archive/secrets/` and **rotate in GCP**:
- `backend/firebase-credentials.json`

Leave active (already local): `backend/.env`, `frontend/.env.local`, `docker-compose.yml`, `start-dev.bat`, `stop-dev.bat`.

> `frontend/.env` still holds the prod Firebase project values, but `.env.local` overrides it for local dev. I'll leave `.env` as a reference unless you want it blanked.

## 2. Remove GitHub CI/CD + git remote
- Move `.github/workflows/*.yml` → `archive/github-workflows/`
- `git remote remove origin` (local commit history preserved)

## 3. Restructure (target layout)
```
Sanket/
├── backend/            unchanged internally
├── frontend/           unchanged internally
├── infra/              observability + k8s base/staging
├── docs/
│   └── reports/        SANKET_Audit_Report.docx, SANKET_ReAudit_Report.docx, SANKET_Project_Overview.pdf
├── scripts/            *.bat (rebuild_*, run_*, start-dev, stop-dev), run_forecast.py, ingest_sales.py, generate_pitch.js
├── data/               sanket_sales_history.csv, forecast_results.json
├── archive/            legacy root index.html, prod-config/, github-workflows/, secrets/
├── docker-compose.yml
├── package.json / package-lock.json / node_modules   (for generate_pitch.js — TBD: move under scripts/)
└── README.md
```
Reference fixes after moving: update paths inside the `.bat` scripts (and `run_*.bat` → `*.py`) so local dev still works. `start-dev.bat` uses `%~dp0` relative paths, so it keeps working if moved alongside the others — to be verified.

## 4. Verify error-free
From here: `npm run build` (frontend), backend import/lint sanity checks. Full stack run (Postgres/Redis/uvicorn/arq) happens on your laptop via `start-dev.bat`.

---

## Open questions before execute
1. Move `node_modules` + root `package.json` (the `generate_pitch.js` toolchain) under `scripts/`, or leave at root?
2. Blank the prod values in `frontend/.env`, or leave as reference?
3. OK to run `git remote remove origin` from here (may need to run on your machine due to a sandbox lock)?
