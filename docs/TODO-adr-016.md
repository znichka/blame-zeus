# ADR-016 — Web-Only Direction + Mosaic Frontend Redesign: Detailed Checklist

**Done when:** the `telegram-bot` module and all its wiring (build, compose, env) are gone and
`./gradlew projects` lists only `core-api`; a full `./gradlew build` is green with no telegram
reference anywhere in code/build/compose/env; the single web page (`index.html`) renders the
self-contained Greek/Roman **mosaic** theme (cream base, steel-blue serif "Blame Zeus" header +
tagline, pure-CSS meander/wave border strips, pale-blue input with terracotta submit arrow, a
"Verdict" answer label) with **no Tailwind-CDN or web-font network request**; curated example-question
**chips** fill+submit the input; source citations render in a **first-class "Sources" panel** paired
with the existing "Sources disagree" conflict panel; every existing `QueryResponse` binding and the
`!conflictsInProse && !conflicts.isEmpty()` conflict gate (see D4.5) are preserved; `:core-api:test` is green; and the stale telegram
references in docs are cleaned up.

> **This is post-MVP work — not part of `IMPLEMENTATION_PLAN.md §9`.** It implements
> `docs/adr/adr-016-web-only-direction-mosaic-frontend.md`, decided after Stage 9 shipped. It is
> tracked under `TODO.md`'s **Post-MVP Enhancements** section, named by ADR (not a numbered stage),
> so the §9 stage history stays untouched. **ADR-016 supersedes DEV-007** and withdraws
> `IMPLEMENTATION_PLAN.md §6` + roadmap Stage 11 (banners already added; documentation landed as
> **DEV-058**).

> **Scope is presentation + subtraction only — no backend logic changes.** The redesign is purely
> `index.html` + new `static/` CSS/JS. Do **not** touch `WebController.kt`, `QueryService`, the
> routing/handler/AI layers, or any DTO (`QueryResponse`/`Citation`/`ConflictEntry`). No new
> endpoint, no loader, no runtime read of `evaluation/gold-questions.json` — example questions are
> **hardcoded** in the template. Light-only theme by design (no dark-mode variant, no navy).

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:

- **DEV-058** already recorded this decision (documentation-first); this checklist is the deferred
  **implementation**. No second scope entry is needed unless the build/redesign itself deviates.
- **DEV-055** — controller/web tests mock `QueryService` via `@MockkBean` (never a live
  `@AiService`); a template rewrite must keep `WebControllerTest` green. If any test asserts specific
  markup (Tailwind class names, old citation `<ol>` structure), update the assertion to the new
  structure — do **not** loosen the `QueryService` mocking pattern.
- **ADR-015 / DEV-056** — the `!conflictsInProse` gate on the "Sources disagree" box is load-bearing:
  it prevents double-printing conflicts already woven into the prose. The redesign must keep the gate
  `th:if="${!response.conflictsInProse && !response.conflicts.isEmpty()}"` **exactly**.
- **DEV-057** — SQL answers now carry real citations; the "Sources" panel is what surfaces them, so
  verify a DATA question shows sources in Track H (regression guard for DEV-057's work).

**Deviation protocol:** latest existing entry is **DEV-058**; new ones start at **DEV-059**. If any
track deviates from ADR-016, log it, mark the touched line `[DEVIATED - see DEVIATIONS.md DEV-NNN]`,
and add the ADR-016 pointer.

---

## Parallelization Guide

```
Track 0 (read-only confirm) ─┐
                             ├─→ Track A (asset/design decisions on paper) ─┬─→ Track C (CSS) ─┐
Track B (remove telegram-bot) ┘  (B is fully independent of A/C/D/E)         ├─→ Track D (index.html) ─┬─→ Track G (tests) ─→ Track H (manual smoke)
                                                                            └─→ Track E (chips JS) ────┘
                             └─→ Track F (docs cleanup — any time after B lands)
```

- **Track 0 + Track B start immediately.** 0 is read-only confirmation; B (module removal) is
  independent of the frontend work and can land first to shrink the build.
- **Track A** (design/asset decisions on paper) unblocks the frontend tracks.
- **Tracks C / D / E** are the frontend: CSS, template, chip JS. D depends on C (references the
  stylesheet + classes) and E (references the chip markup/JS); do C and E before finishing D, or
  stub and reconcile.
- **Track F** (docs cleanup) can land any time once B has removed the module.
- **Track G** updates tests after the template shape changes; **Track H** (manual browser smoke) is
  last — needs everything wired and the app runnable.

---

## Track 0 — Pre-flight confirms (read-only, no production code)

_Purpose:_ corroborate the removal surface and the bindings the redesign preserves. Write findings to
a scratch note; log any contradiction as a DEV.

- [x] **0.1** Confirm no `core-api` (or `ingestion`/`scripts`) code references telegram:
      `grep -ri "telegram" core-api ingestion scripts` returns nothing. Removal is compile-clean.
- [x] **0.2** Confirm the removal surface exactly: `telegram-bot/` dir (only real file
      `build.gradle.kts`); `settings.gradle.kts` include line (`include("core-api", "telegram-bot")`);
      `docker-compose.full.yml` `telegram-bot:` service block; `.env` + `.env.example` telegram block
      (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `CORE_API_BASE_URL`). `docker-compose.yml`
      (DB-only) has **no** telegram reference — leave it.
- [x] **0.3** Confirm the `QueryResponse` field map the template binds
      (`domain/dto/QueryResponse.kt`): `answer`, `routeDecision: RouteDecision?`,
      `citations: List<Citation>`, `conflicts: List<ConflictEntry>`, `sqlGenerated: String?`,
      `serviceError`, `conflictsInProse`. `Citation(author, work, passageRef, stance?)`;
      `ConflictEntry(claimValue, sourceAuthor, sourceWork, passageRef?)`. The redesign changes **no**
      field.
- [x] **0.4** Confirm `WebController` (`controller/WebController.kt`) serves `GET /` → `index` and
      `POST /web/query` (`@RequestParam question`) → `index` with model `question` + `response`.
      **No controller change** — chips submit the same form; the input keeps `name="question"`.
- [x] **0.5** Confirm Spring Boot serves `/static/**` off the classpath (default). The new
      `core-api/src/main/resources/static/css/blame-zeus.css` is referenced as `/css/blame-zeus.css`
      and `static/js/examples.js` as `/js/examples.js`. The `static/` dir does not yet exist.
- [x] **0.6** Confirm the current template touch-points to preserve
      (`resources/templates/index.html`): route badge `th:switch`, `serviceError` box, citations
      `<ol>` (→ becomes the Sources panel), the "Sources disagree" box with its `!conflictsInProse`
      gate, and the generated-SQL `<details>`. Note which existing tests assert markup (Track G).

---

## Track A — Design & asset decisions (on paper, no production code)

_Purpose:_ pin the concrete implementation choices ADR-016's brief leaves open. Record each in the
scratch note; none is a deviation unless it contradicts ADR-016.

- [x] **A1 — Palette as CSS custom properties.** Define `:root` vars: `--cream:#fdfbf5`,
      `--steel:#3d6a8c`, `--steel-light:#5a86a8`, `--terracotta:#c76b4a`, `--input-bg:#eef4f8`,
      plus derived warm-gray body + muted blue-gray placeholder. Single source of truth for the theme.
- [x] **A2 — Meander (top) + wave-scroll (bottom) border strips.** Decide the pure-CSS technique:
      inline-SVG `data:` URI `background-image` on thin fixed strips (light-blue band + terracotta
      linework), `aria-hidden`, non-interactive, do not cause horizontal scroll on narrow viewports.
      Keep the SVG small and inlined (no external asset, no CDN).
- [x] **A3 — Typography.** Serif stack `Georgia, 'Iowan Old Style', 'Palatino Linotype',
      'Times New Roman', serif` for title/answer; system sans (`system-ui, -apple-system, 'Segoe UI',
      sans-serif`) for tagline/labels/chips. **No web-font download.**
- [x] **A4 — Example-question set + chip interaction.** Fix the curated set (hardcoded, from
      `evaluation/gold-questions.json`, conflict-weighted): CONFLICT — *"Who were Aphrodite's
      parents?"*, *"How did Achilles die?"*, *"Who was Io's father?"*; FACT — *"Why did Athena turn
      Arachne into a spider?"*; DATA — *"Which Olympians are children of Cronus?"*; MIXED — *"Which
      heroes had a divine parent and died at Troy?"*. Interaction: chip is a `<button type="button"
      data-question="…">`; `examples.js` sets the input value and submits the form (single-turn model
      preserved). Decide graceful no-JS behavior (chips can be plain and simply inert, or be links —
      keep it simple; JS-fill is the primary path).
- [x] **A5 — Answer / Sources / Conflict layout.** "Verdict" = thin terracotta left-border rule +
      small uppercase terracotta label + serif answer. "Sources" = a first-class panel (uppercase
      terracotta label + one card/row per citation), always visible when `citations` non-empty.
      "Sources disagree" = terracotta-accented panel, visually paired with Sources, gated **exactly**
      by `!conflictsInProse && !conflicts.isEmpty()`. Route badge de-emphasized into the palette;
      generated-SQL `<details>` restyled. Decide the small-screen stacking order.

---

## Track B — Remove the `telegram-bot` module (build / compose / env)

_Independent of the frontend tracks._ No `core-api` code depends on it (0.1).

- [x] **B1** Delete the entire `telegram-bot/` directory (including its `build/` output).
- [x] **B2** `settings.gradle.kts` — change `include("core-api", "telegram-bot")` →
      `include("core-api")`. (Leave the unrelated `ingestion` comment.)
- [x] **B3** `docker-compose.full.yml` — delete the whole `telegram-bot:` service block
      (`build`/`image`, `depends_on: core-api: service_healthy`, and the `CORE_API_BASE_URL` /
      `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` env). Leave `core-api` + `postgres` intact.
- [x] **B4** `.env` and `.env.example` — remove the telegram block (`# Telegram bot (Phase 2)`,
      `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, the `# core-api base URL …` comment, and
      `CORE_API_BASE_URL`). These vars are used **only** by the removed compose block.
- [x] **B5** Verify: `./gradlew projects` lists only `core-api`; `./gradlew build` green;
      `grep -ri "telegram" --exclude-dir=build --exclude-dir=.git .` returns only the intentional
      historical notes in `docs/DEVIATIONS.md` (DEV-007/DEV-058) and ADR-016 — no live code/build/env.

---

## Track C — Mosaic stylesheet (`static/css/blame-zeus.css`)

_Depends on: A1–A3, A5._ New file `core-api/src/main/resources/static/css/blame-zeus.css`.

- [x] **C1** Create `static/css/` and the stylesheet. Encode the A1 palette vars, the cream page
      background, centered `max-width` content column, and the A3 typography.
- [x] **C2** Implement the A2 meander (top) + wave-scroll (bottom) border strips as pure CSS /
      inline-SVG `data:` URIs. Confirm no horizontal overflow at ~360px width.
- [x] **C3** Style the header ("Blame Zeus" serif steel-blue + sans warm-gray tagline), the input
      (pale-blue `#eef4f8` rounded rectangle, soft blue border, muted placeholder) with the terracotta
      submit **arrow** on the right, and the example-question **chips**.
- [x] **C4** Style the results area: "Verdict" label + answer, route badge (palette-toned), the
      first-class **Sources** panel, the paired **"Sources disagree"** panel (terracotta accent), the
      `serviceError` box (terracotta-toned), and the generated-SQL `<pre>` (restyled, still readable).
- [x] **C5** No `@import`, no external font/CDN URL anywhere in the file (self-contained requirement).

---

## Track D — Rewrite the template (`index.html`)

_Depends on: C + E._ Edit `core-api/src/main/resources/templates/index.html`.

- [x] **D1** Replace the Tailwind-CDN `<head>` with `<link rel="stylesheet" href="/css/blame-zeus.css">`
      (and defer `/js/examples.js`). Keep the Thymeleaf namespace and `<title>`.
- [x] **D2** Top meander strip (decorative, `aria-hidden`) → header block ("Blame Zeus" + tagline) →
      the question `<form method="post" action="/web/query">` with `input name="question"`
      `th:value="${question}"`, placeholder *"Who slew the Hydra?"*, and the terracotta submit arrow.
      **Unchanged form contract** (0.4).
- [x] **D3** Example-question **chips** block under the input (A4 set), each a
      `<button type="button" data-question="…">`; add the bottom wave-scroll strip.
- [x] **D4** Results block (`th:if="${response != null}"`), preserving **every** binding:
  - [x] **D4.1** Route badge `th:switch="${response.routeDecision?.name()}"` (SQL/RAG/MIXED/default),
        restyled/de-emphasized.
  - [x] **D4.2** `serviceError` box (`th:if="${response.serviceError}"`) — terracotta-toned copy.
  - [x] **D4.3** "Verdict" answer (`th:unless="${response.serviceError}"`, `th:text="${response.answer}"`).
  - [x] **D4.4** First-class **Sources** panel (`th:if="${!response.citations.isEmpty()}"`) — one
        row/card per `citation` binding `author`, `work`, optional `passageRef`, optional `stance`.
  - [x] **D4.5** **"Sources disagree"** panel — gate **exactly**
        `th:if="${!response.conflictsInProse && !response.conflicts.isEmpty()}"` (ADR-015/DEV-056),
        each `conflict` binding `sourceAuthor`, `sourceWork`, `claimValue`, optional `passageRef`.
  - [x] **D4.6** Generated-SQL `<details>` (`th:if="${response.sqlGenerated != null}"`) — restyled `<pre>`.
- [x] **D5** Watch the field-name asymmetry: citations use bare `author`/`work`; conflicts use
      `sourceAuthor`/`sourceWork` and the claim text is `claimValue`; `Citation.passageRef` is
      non-nullable, `ConflictEntry.passageRef` nullable.

---

## Track E — Example-chip behavior (`static/js/examples.js`)

_Depends on: A4._ New file `core-api/src/main/resources/static/js/examples.js`.

- [x] **E1** Vanilla JS (no library, no CDN): on chip click, read `data-question`, set the
      `name="question"` input's value, and submit its form. Keeps the single-turn flow.
- [x] **E2** Progressive enhancement: script is `defer`-loaded; if JS is unavailable the page still
      renders and the manual input still works (chips simply do nothing, or are plain text) — decide
      per A4 and keep it graceful.

---

## Track F — Docs cleanup (stale telegram references)

_Depends on: B._ Remove/annotate telegram mentions the ADR-016 pivot obsoletes. Prefer a short
"(removed — see ADR-016 / DEV-058)" note over deleting history in the append-only/authoritative docs.

- [x] **F1** `README.md` — drop the `telegram-bot` line from the architecture diagram, the "Full
      stack with Telegram bot" section, and the module list; make the module list web-only.
- [x] **F2** `CLAUDE.md` — language list (`core-api`, ~~`telegram-bot`~~), the Service Layout table
      row, and the directory-tree line.
- [x] **F3** `docs/TECH_GUARDRAILS.md` and `docs/TODO-stage1.md` — annotate/trim the telegram refs.
- [x] **F4** `docs/adr/adr-003-model-selection.md` and `docs/adr/adr-012-external-reference-identification.md`
      — leave the historical prose but note telegram is out of scope (web-only) where it would mislead.
- [x] **F5** `IMPLEMENTATION_PLAN.md §6` banner, roadmap Stage 11 strike, and `docs/TODO.md` Stage 11
      "REMOVED" note — **already done** with DEV-058; just verify they read correctly after B lands.

---

## Track G — Tests

_Depends on: B + D._

- [x] **G1** Run `:core-api:test` after B (module removal) — confirm nothing referenced
      `telegram-bot` and the suite still compiles/passes.
- [x] **G2** Update any test that asserts old markup. `WebControllerTest` (`@MockkBean QueryService`,
      DEV-055) must stay green; if it asserts Tailwind classes or the old citations `<ol>`, re-point
      the assertions at the new structure (Sources panel, chips) — keep the mocking pattern.
      (No update needed: its assertions check text content — "SQL", "Zeus", "Hesiod, Theogony",
      "Show generated SQL", "Sources disagree" — not Tailwind classes or `<ol>` structure; all 5
      cases passed unmodified against the new template.)
- [x] **G3** Run the full `:core-api:test` — green.

---

## Track H — Manual browser smoke (last)

_Depends on: C–E wired, docs OK, app runnable (`docker-compose` DB up + seeded; `bootRun` with
`OPENAI_API_KEY`/`LLM_API_KEY`/`LLM_CHAT_MODEL`/`EMBEDDING_MODEL`)._ Use the `run` or
claude-in-chrome skill.

- [ ] **H1** `GET /` renders the mosaic layout: cream bg, meander top + wave bottom strips,
      steel-blue serif "Blame Zeus" + tagline, pale-blue input + terracotta arrow, example chips.
      **DevTools Network shows no request to `cdn.tailwindcss.com` or any font/CDN host** —
      `/css/blame-zeus.css` and `/js/examples.js` load 200 (self-contained requirement).
- [ ] **H2** Click the *"Who were Aphrodite's parents?"* chip → the input fills and the form submits →
      a **Verdict** answer renders; conflicts are woven into the prose (`conflictsInProse=true`) so the
      "Sources disagree" panel is **absent**; if a fallback occurs it appears (gate honored, no dupes).
- [ ] **H3** Ask a **DATA** question (*"Which Olympians are children of Cronus?"*) → prose answer, the
      **Sources** panel lists real citations (DEV-057 regression guard), and the "Show generated SQL"
      disclosure works.
- [ ] **H4** Ask a **FACT** question → answer + Sources panel; ask a **MIXED** question → same uniform
      shape. Confirm a `serviceError` path shows the terracotta error box.
- [ ] **H5** Responsive check at ~360px: no horizontal page scroll; border strips and panels reflow;
      wide content (SQL `<pre>`) scrolls within its own container.

---

## Definition of Done (roll-up)

- [x] `telegram-bot/` deleted; `settings.gradle.kts`, `docker-compose.full.yml`, `.env`/`.env.example`
      cleaned; `./gradlew projects` lists only `core-api`; `./gradlew build` green; no live telegram
      reference remains (only historical DEV-007/DEV-058 + ADR-016 notes).
- [x] `static/css/blame-zeus.css` + `static/js/examples.js` created; fully self-contained (no CDN, no
      web font); `index.html` rewritten into the mosaic theme with the Verdict/Sources/"Sources
      disagree" layout.
- [x] Every `QueryResponse` binding preserved; the `!conflictsInProse && !conflicts.isEmpty()`
      conflict gate kept exactly; `WebController`/`QueryService`/DTOs unchanged.
- [x] Example-question chips fill+submit the input (single-turn).
- [x] Docs cleaned of stale telegram references (README, CLAUDE.md, guardrails/stage1, ADR-003/012).
- [x] `:core-api:test` green (markup-asserting tests updated).
- [ ] Manual browser smoke passes (Track H), including the no-CDN network check and the DATA-question
      Sources regression guard.
