# Hyperframes Composition Brief: SANKET

## Objective
Create a short, premium cinematic launch-style product video for SANKET showcasing its problem, solution, closed-loop workflow, key features, AI architecture, real-world impact, and strong closing statement.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Poster frame: `brag-output/brag.jpg` (baked into frame 0 of video)
- Format: landscape — 1920x1080 @ 30fps
- Duration: 25.0 seconds (750 frames)

## Source Material
- Project root: `c:/Users/admin/Desktop/Prisma`
- Primary files read: `frontend/index.html`, `frontend/src/styles/index.css`, `frontend/src/pages/LandingPage.tsx`, `frontend/src/pages/landing/LiveConsoleLanding.tsx`, `backend/ml/`, `docs/ARCHITECTURE.md`
- Product name: SANKET
- Tagline / strongest claim: "Stop guessing demand. Forecast every SKU."
- Key UI or visual moments to recreate:
  - Real UI Forecast Run (`sanket_forecast_run.png`) with p10/p50/p90 uncertainty envelope
  - 4-step operational loop (`01 INGEST` → `02 FORECAST` → `03 DECIDE` → `04 ACT`)
  - AI Foundation Models (Chronos zero-shot, TFT, N-HiTS ensembles)
  - 3D Vertical Hero visuals (`3d_fashion.png`, `3d_electronics.png`, `3d_pharma.png`)
  - Official SANKET LogoMark SVG
- Copy that must appear verbatim:
  - "Stop guessing demand. Forecast every SKU."
  - "01 Ingest · 02 Forecast · 03 Decide · 04 Act"
  - "Amazon Chronos Zero-Shot · Deep Ensembles"
  - "-35% Stockout Occurrences · 99.4% Service Levels · GxP 21 CFR Part 11"

## Creative Direction
- Tone preset: `cinematic` / `polished`
- Creative direction: High-end enterprise AI product launch film / Demo-Day trailer
- Interpretation: Fast-paced, kinetic, sleek, restrained, high-contrast dark aesthetic with glowing teal/cyan accents and warm platinum typography.
- Avoid: Generic SaaS language, blurry low-res graphics, static slides, unreadable text.

## Visual Identity
- Background: `#060606` canvas with subtle emerald aurora glow (`#071B1D`, `#03363D`)
- Text: `#E8E5D0` (warm platinum primary), `#FFFFFF` (pure white high-contrast), `#91AEAB` (muted sage)
- Accent: `#BDD9D7` (jet stream cyan) and emerald cyan `#10B981` / `#06B6D4`
- Alert/Problem color: `#EF4444` / `#F43F5E` (crimson warning for Scene 1)
- Display font: Space Grotesk
- Body font: IBM Plex Sans
- Data/Mono font: IBM Plex Mono

## Storyboard & Timing (750 frames = 25.0s @ 30fps)
1. Scene 1 (0.0s – 3.5s, f0–f105): Supply Chain Chaos & Guesswork Problem
2. Scene 2 (3.5s – 7.0s, f105–f210): SANKET Emergence & Core Solution
3. Scene 3 (7.0s – 11.0s, f210–f330): The 4-Step Closed Loop (How It Works)
4. Scene 4 (11.0s – 15.0s, f330–f450): Real UI Forecast Engine (Key Features)
5. Scene 5 (15.0s – 18.5s, f450–f555): Foundation AI & Multi-Model Stack (Technology)
6. Scene 6 (18.5s – 22.0s, f555–f660): Multi-Vertical Verified Impact (Real-World Impact)
7. Scene 7 (22.0s – 25.0s, f660–f750): Grand Finale & Closing CTA

## Audio Configuration
- Music: `assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (109.96 BPM)
- SFX files:
  - `assets/sfx/impact/impactBell_heavy_000.ogg` (Opening hit at 0.0s)
  - `assets/sfx/impact/impactSoft_medium_000.ogg` (Solution reveal at 3.5s)
  - `assets/sfx/casino/card-slide-1.ogg` (Step card 1 at 7.0s)
  - `assets/sfx/casino/card-place-1.ogg` (Step card 2 at 8.5s)
  - `assets/sfx/interface/click_001.ogg` (Forecast trigger at 11.2s)
  - `assets/sfx/interface/glitch_002.ogg` (AI foundation tech at 15.0s)
  - `assets/sfx/impact/impactSoft_medium_002.ogg` (Impact metrics slam at 18.5s)
  - `assets/sfx/casino/chips-stack-1.ogg` (Metrics count-up at 19.5s)
  - `assets/sfx/impact/impactBell_heavy_003.ogg` (Final logo slam at 22.0s)
  - `assets/sfx/interface/switch_001.ogg` (CTA chime at 22.8s)
