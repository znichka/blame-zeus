# ADR-016: Web-Only Product Direction + Mosaic Frontend Redesign

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-20  |
| **Status**   | Accepted    |
| **Amends**   | — |
| **Amended by** | —         |
| **Supersedes** | DEV-007 (telegram-bot build placeholder) |

---

## Context

blame-zeus was planned as two runtime services (`IMPLEMENTATION_PLAN.md §Service Layout`): the
Phase 1 `core-api` (Q&A brain + REST API + Thymeleaf web UI), and a Phase 2 `telegram-bot` — a thin
adapter that would consume the same `POST /api/v1/query` and relay answers into a Telegram chat.

The Telegram consumer was **never implemented**. The `telegram-bot/` module is an empty placeholder:
its only real file is `build.gradle.kts`, and even the Telegram starter dependency is commented out
(DEV-007) because coordinates were never verified. No source, no `CoreApiClient`, no formatter.

Meanwhile the actual front door — the web page (`core-api/src/main/resources/templates/index.html`)
— is a functional but generic scaffold: a Tailwind-CDN page with a plain input and an understated,
footnote-style rendering of the source citations that are the product's whole point. It does not
convey the product's personality (a wry, source-attributed mythology oracle) and leans on an
external CDN at runtime.

The product is being refocused: **the web page is the product**, and it should look and read like it.
The Telegram direction is being dropped rather than carried as perpetual dead weight in the build,
compose files, env templates, and docs.

## Decision

### 1. Remove the `telegram-bot` module; the product is web-only

Drop the Telegram consumer from scope entirely. The `telegram-bot/` module, its `settings.gradle.kts`
inclusion, its `docker-compose.full.yml` service block, and its `.env` / `.env.example` variables
(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `CORE_API_BASE_URL`) are to be removed. No `core-api`
code depends on the module, so removal is compile-clean. `IMPLEMENTATION_PLAN.md §6 (Consumer Layer
— Telegram Bot)` and roadmap Stage 11 are **withdrawn**.

### 2. Redesign the single web page into a Greek/Roman mosaic theme

Replace the Tailwind-CDN scaffold with a bespoke, **self-contained** design (no CDN, no external web
font) inspired by ancient mosaic floor art. Design brief to be implemented:

- **Palette (light-only by design — no navy, no dark backgrounds):** near-white cream base
  `#fdfbf5`; muted steel blue `#3d6a8c` (headings) and lighter `#5a86a8` (border bands); terracotta
  `#c76b4a` (accents, linework, submit arrow, labels); muted blue-gray placeholder; warm-gray body.
- **Ornament (pure CSS / inline-SVG `data:` URIs, no image assets):** a Greek-key (meander) band
  across the top and a wave-scroll band across the bottom, thin light-blue with terracotta linework —
  decorative framing (`aria-hidden`).
- **Typography:** a classical **system serif stack** (`Georgia, 'Iowan Old Style', 'Palatino
  Linotype', 'Times New Roman', serif`) for the title/answer; system sans for tagline/labels/chips.
- **Header:** "Blame Zeus" in serif steel-blue, with the tagline *"Ask about the gods, we'll tell you
  whose fault it is. (Probably Zeus, but we'll double check.)"* No icon/logo — typography only.
- **Question input:** a pale blue-tinted rounded rectangle (`#eef4f8`, soft blue border), placeholder
  e.g. *"Who slew the Hydra?"*, terracotta submit **arrow** on the right. Single-turn
  (question-then-answer), not a multi-turn thread. Keeps the existing `POST /web/query`, `name="question"`.
- **Answer area:** a thin terracotta left-border rule, a small uppercase terracotta **"Verdict"**
  label, and the response in serif dark warm-gray.
- Mood: sunlit museum case — airy, modern, understated classical ornament, humor in the copy.

### 3. Surface curated example questions as clickable chips

Show a small set of **hardcoded, curated** example-question chips beneath the input so first-time
visitors know what to ask. Chips fill the input and submit the form (a tiny vanilla-JS helper),
preserving the single-turn model. The set is drawn from `evaluation/gold-questions.json` but
**hardcoded in the template** — no runtime coupling to the eval fixture (which is not on the
`core-api` classpath and lacks REFUSAL examples). The set is weighted toward the app's defining
conflict-awareness feature (CONFLICT questions surface multiple contradictory attributed accounts):

- CONFLICT: *"Who were Aphrodite's parents?"*, *"How did Achilles die?"*, *"Who was Io's father?"*
- FACT: *"Why did Athena turn Arachne into a spider?"*
- DATA: *"Which Olympians are children of Cronus?"*
- MIXED: *"Which heroes had a divine parent and died at Troy?"*

### 4. Elevate source attribution to a first-class "Sources" panel

Source attribution is the product's defining feature, yet the current page renders citations as a
muted numbered footnote list. The redesign promotes citations into a **styled, always-visible
"Sources" panel** under the Verdict, visually paired with the existing "Sources disagree" conflict
panel, so attribution and disagreement read as one "receipts" section. This is a **presentation
change only** — all current DTO bindings are preserved:
- Citations: `citation.author`, `.work`, `.passageRef`, `.stance` (`QueryResponse.citations`).
- Conflicts: `conflict.sourceAuthor`, `.sourceWork`, `.claimValue`, `.passageRef`, gated **exactly**
  by `th:if="${!response.conflictsInProse && !response.conflicts.isEmpty()}"` (ADR-015 fallback rule —
  avoids double-printing when conflicts are already woven into the prose).
- Route badge, error box, and generated-SQL `<details>` remain, restyled into the palette.

No changes to `WebController.kt`, `QueryService`, or any DTO are required — the redesign is purely
the template plus self-contained `static/` CSS/JS.

## Alternatives considered

- **Keep telegram-bot as a dormant placeholder.** Rejected: it has sat empty since Stage 1a, adds
  noise to the build/compose/env/docs, and the product is not pursuing a chat channel.
- **Load example questions dynamically from `gold-questions.json`.** Rejected: the file is not on the
  `core-api` classpath, contains no REFUSAL examples, and is eval infrastructure; coupling the
  runtime UI to it adds a loader + endpoint for no user-facing benefit. Hardcoding a curated subset
  lets us pick the strongest "wow" (conflict) demonstrations.
- **Bundle a classical web font (e.g. EB Garamond `.woff2`) locally.** Rejected for now: a larger
  asset for marginal gain; a system serif stack keeps the page fully self-contained and light.
- **Layer the theme on top of the Tailwind CDN.** Rejected: an external runtime dependency and an
  awkward fit for the bespoke meander/wave ornament, which is cleaner as hand-written CSS.

## Consequences

**Positive**
- The web page is the single, coherent front door and reflects the product's voice.
- Fully self-contained page (no Tailwind CDN, no web-font request) — simpler, offline-friendly.
- Source attribution — the defining feature — is visually first-class.
- Build, compose, env, and docs shed an unused module.

**Negative / costs**
- Loses the option of a Telegram channel without re-introducing a module (low cost — none existed).
- A curated example set must be maintained by hand if the showcase questions change.

**Scope note / sequencing**
- This ADR is being recorded **before** implementation. The documentation deliverables (this ADR,
  the DEV entry, the plan/TODO annotations) land first; the module removal and template/`static`
  redesign are a follow-up implementation stage. Recording the full design brief here ensures none
  of the design intent is lost in the interim.

**Follow-ups**
- Record `DEV-058` in `docs/DEVIATIONS.md` cross-referencing this ADR and superseding DEV-007.
- Add the deviation banner to `IMPLEMENTATION_PLAN.md §6` and the Stage 11 roadmap row; annotate
  the Stage 11 section in `docs/TODO.md` as removed.
- Implementation stage (deferred): delete `telegram-bot/`, edit `settings.gradle.kts`,
  `docker-compose.full.yml`, `.env`/`.env.example`; rewrite `index.html`; add `static/css` + `static/js`.
