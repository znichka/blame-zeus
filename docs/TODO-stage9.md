# Stage 9 — Web UI (Thymeleaf smoke UI + Swagger): Detailed Checklist

**Done when:** a browser at `http://localhost:8080/` renders a query form; submitting any of the 17
gold questions returns a page showing (a) a **color-coded route badge** driven by
`QueryResponse.routeDecision`, (b) the answer text with **citations as numbered footnotes**, (c) a
**conflicts section** (`Author, Work: claim` per version) whenever `conflicts[]` is non-empty —
*regardless of route*, since enrichment is route-independent (DEV-014), (d) a **collapsible SQL
block** when `sqlGenerated != null`, and (e) an **error banner** instead of the answer block when
`serviceError == true`; Swagger UI loads at `/swagger-ui.html`; the new `WebController` +
`OpenApiConfig` compile and the full `:core-api:test` suite is green.

> **Design is the plan's, not the plan's dead branches.** `WebController` serves `GET /` (empty
> form) and `POST /web/query` → calls the **existing** `QueryService.handle(question)` (the exact
> same entry point `QueryController.query` already uses at `QueryController.kt:37`) → drops the
> returned `QueryResponse` onto the model for the template. **No new orchestration, no new query
> logic, no second code path.** The web layer is a *view* over the identical service call the REST
> API makes.
>
> Two things the older plan text still implies that must **NOT** be built:
> - **No `CONFLICT` route badge case as a live route.** IMPLEMENTATION_PLAN §860 lists
>   "CONFLICT=orange" in the badge color map, but there is **no `CONFLICT` route** (killed in Stage 7
>   per ADR-007 / DEV-014) — `routeDecision` is only ever `SQL`/`RAG`/`MIXED` **or `null`**. The
>   badge must map those three plus a safe fallback for `null`; do **not** add a CONFLICT route or
>   branch. Conflicts render from `conflicts[]`, never from a route. (Keep an orange style available
>   for the *conflicts section header* if desired — that is presentation, not a route.)
> - **No new DTO / no `WebQueryResponse`.** The template binds directly to the existing
>   `QueryResponse` (`answer`, `routeDecision`, `citations`, `conflicts`, `sqlGenerated`,
>   `serviceError`). Every field the UI needs already exists — see the field map in Track 0.

> **Prerequisite: Stages 5–8 complete.** The web UI is a thin view over `QueryService.handle()`,
> which already dispatches all three routes and runs route-independent conflict enrichment. Nothing
> in Stage 9 touches routing, handlers, or enrichment.

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:
- **DEV-009** — `springdoc-openapi-starter-webmvc-ui` is pinned **`2.6.0`** (already declared in
  `core-api/build.gradle.kts:30`; **do not** bump to 2.8.x — it requires Spring Boot 3.4.x and breaks
  `@SpringBootTest` context loading under 3.3.13). `OpenApiConfig.kt` targets 2.6.0's API surface;
  `@Operation`/`@Tag`/`OpenAPI`+`Info` bean usage is unaffected.
- **DEV-014** — no `CONFLICT` route; `routeDecision ∈ {SQL, RAG, MIXED, null}`. `conflicts[]` is
  populated by route-independent enrichment, so a conflict-shaped question surfaces versions no matter
  which badge shows. The integration test must assert this (conflict-shaped question → non-empty
  `conflicts[]` under whatever route it took), **not** a CONFLICT route.
- **DEV-008** — Testcontainers pinned `1.21.4`; any DB-backed test reuses `AbstractContainerTest`
  (the pattern `QueryControllerTest` already follows). The `WebController` render test and the
  `QueryControllerIntegrationTest` are `@AutoConfigureMockMvc` over `AbstractContainerTest`, matching
  the existing controller test exactly — no new container setup.
- **DEV-051 / DEV-021** — `conflicts[]` entries carry `passageRef` (nullable) and cite via the
  deterministic `ConflictSynthesizer`; the template should render `passageRef` when present, same
  citation shape as `citations[]`.

**Build deps are already present — confirm, don't add.** `spring-boot-starter-web` (:14),
`spring-boot-starter-thymeleaf` (:16), and `springdoc-openapi-starter-webmvc-ui:2.6.0` (:30) are all
already in `core-api/build.gradle.kts`. Track 0 verifies this; **no `build.gradle.kts` edit is
expected**. If one turns out to be missing, adding it is a deviation → log the next `DEV-NNN`.

**Deviation protocol:** latest entry is **DEV-053**; new ones start at **DEV-054**. If any track
deviates (e.g. a build-dep edit, introducing a view-model DTO instead of binding `QueryResponse`
directly, or `OpenApiConfig` proving unnecessary and being dropped), log it, mark the touched line
`[DEVIATED - see DEVIATIONS.md DEV-NNN]`, and add the §9 stage-note pointer in IMPLEMENTATION_PLAN.

---

## Parallelization Guide

```
Track 0 (read-only confirm) ─┐
                             ├─→ Track B (WebController, TDD) ──┐
Track A (4 design decisions) ┘                                  ├─→ Track E (integration + render tests) ─→ Track F (manual smoke)
                             ├─→ Track C (index.html template) ─┤
                             └─→ Track D (OpenApiConfig) ────────┘
```

- **Track 0 + Track A start immediately, in parallel** — 0 is read-only confirmation, A is four
  decisions on paper. Neither depends on the other (A can proceed on the field map A already knows;
  0 just corroborates).
- **Tracks B, C, D depend on A** (A2 fixes the request shape B binds; A3 fixes the badge/null
  handling C renders; A4 decides D's scope) **and are mutually independent** — the controller, the
  template, and the OpenAPI bean touch disjoint files and can be built concurrently.
- **Track E depends on B + C** (needs a live controller + a template that renders) — but the
  `QueryControllerIntegrationTest` half (REST JSON contract) depends only on the already-shipped
  `QueryController`, so it can start as soon as Track 0 confirms the response shape.
- **Track F is last** — manual browser smoke needs B + C + D wired and the app runnable.

---

## Track 0 — Pre-flight confirms (read-only, no production code)

_Purpose:_ corroborate the field map the template binds to and the single service entry point the
controller calls. Write findings to a scratch note, not the repo; log any contradiction as a DEV.

- [ ] **0.1** Confirm the single entry point: `QueryService.handle(question: String): QueryResponse`
      (`QueryService.kt:33`) is what `QueryController.query` calls (`QueryController.kt:37`).
      `WebController.POST /web/query` calls the **same** method — no new service method.
- [ ] **0.2** Confirm the `QueryResponse` field map the template binds to (`QueryResponse.kt`):
      | field | type | template use |
      |---|---|---|
      | `answer` | `String` | answer block (hidden when `serviceError`) |
      | `routeDecision` | `RouteDecision?` (`SQL`/`RAG`/`MIXED`/**null**) | route badge |
      | `citations` | `List<Citation>` (`author, work, passageRef, stance?`) | numbered footnotes |
      | `conflicts` | `List<ConflictEntry>` (`claimValue, sourceAuthor, sourceWork, passageRef?`) | conflicts section |
      | `sqlGenerated` | `String?` | collapsible SQL block (only when non-null) |
      | `serviceError` | `Boolean` (default false) | error banner when true |
- [ ] **0.3** Confirm the three build deps are already declared and **no build edit is needed**:
      `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, `springdoc-openapi-starter-webmvc-ui:2.6.0`
      (`core-api/build.gradle.kts:14,16,30`). Note: Thymeleaf autoconfigures `src/main/resources/templates/`
      as the view root — the template goes there.
- [ ] **0.4** Confirm springdoc `2.6.0` autoconfigures `/swagger-ui.html` and `/v3/api-docs` with
      **zero** config — i.e. Swagger loads even if Track D's `OpenApiConfig` is never written. This
      scopes Track D to *customization only* (title/description/version), not enablement.
- [ ] **0.5** Confirm no `WebController`, no `src/main/resources/templates/` dir, and no
      `OpenApiConfig.kt` exist yet (all greenfield) — so there is no prior version to preserve.
- [ ] **0.6** Note the existing test pattern to mirror: `QueryControllerTest` is
      `@AutoConfigureMockMvc` over `AbstractContainerTest` with real seeded data, no mocks
      (`QueryControllerTest.kt:16-17`). Track E reuses this exactly.

---

## Track A — Design decisions (on paper, no production code)

_Purpose:_ pin four choices so B/C/D can proceed without blocking on each other. Record each in the
scratch note; none of these is a deviation (they're new-code design), unless they contradict the plan.

- [ ] **A1 — View return style.** `WebController` methods return a `String` view name (`"index"`)
      and take a Spring `Model`, **or** return `ModelAndView`. Decision: **`String` + `@GetMapping`/
      `@PostMapping` with `Model`** (simplest; matches Thymeleaf idiom). Both GET and POST render the
      **same** `index` template — GET with no `response` attribute, POST with it.
- [ ] **A2 — Request binding for `POST /web/query`.** The form submits a single `question` field.
      Decision: bind `@RequestParam("question") question: String` (HTML form → `application/
      x-www-form-urlencoded`), **not** `@RequestBody` (that's the JSON REST path). Confirm the form
      `method="post" action="/web/query"` with `<input name="question">` matches the param name.
- [ ] **A3 — Route badge + null handling.** Map `routeDecision`: `SQL`→blue, `RAG`→green,
      `MIXED`→purple; **`null`**→neutral/grey "—" (a grounded refusal or an error can leave it null).
      Decide the Thymeleaf expression: a `th:switch` on `routeDecision?.name` or a `th:classappend`
      keyed on the enum. **No CONFLICT case** (DEV-014). Also decide: badge always shown once a
      response exists, hidden on the empty first-load form.
- [ ] **A4 — `OpenApiConfig` scope.** Given 0.4 (Swagger works with zero config), decide whether
      `OpenApiConfig` adds value. Decision: **yes, minimal** — an `@Bean OpenAPI` with `Info`
      (title "blame-zeus Core API", version, one-line description) so Swagger isn't titled from the
      bare artifact name. Keep it to that; `@Tag`/`@Operation` annotations on `QueryController` are
      optional polish, not required for "done."

---

## Track B — `WebController.kt` (TDD)

_Depends on: A1, A2._ New file `controller/WebController.kt`. Inject only `QueryService`.

- [ ] **B1 — Test first.** `WebControllerTest` (`@AutoConfigureMockMvc` over `AbstractContainerTest`,
      per 0.6):
  - [ ] **B1.1** `GET /` returns 200, `Content-Type: text/html`, and the view renders the form
        (assert body contains the `<form`/`name="question"` input); **no** `response` model attribute
        present (empty-form state).
  - [ ] **B1.2** `POST /web/query` with form param `question=...` returns 200 HTML and the rendered
        body reflects a real `QueryResponse` (assert the answer text and the route badge label appear).
        Use a seeded question that routes deterministically (e.g. a DATA/SQL question) so the badge
        assertion is stable.
- [ ] **B2 — `GET /`** → `@GetMapping("/")`, returns `"index"`, adds nothing else to the model.
- [ ] **B3 — `POST /web/query`** → `@PostMapping("/web/query")`, `@RequestParam question`, calls
      `queryService.handle(question)`, `model.addAttribute("response", it)` and
      `model.addAttribute("question", question)` (so the form re-shows the asked question), returns
      `"index"`.
- [ ] **B4** Confirm `WebController` is `@Controller` (**not** `@RestController` — it returns view
      names, not response bodies), and lives in the `controller` package alongside `QueryController`.
- [ ] **B5** Run `:core-api:test` — `WebControllerTest` green.

---

## Track C — `templates/index.html` (Thymeleaf + Tailwind CDN)

_Depends on: A2, A3._ New file `src/main/resources/templates/index.html`. Binds to the `response`
model attribute (`QueryResponse`); the whole result section is `th:if="${response != null}"` so
first load shows only the form. Each sub-block is independently checkable.

- [ ] **C1 — Page skeleton + Tailwind.** `<!DOCTYPE html>`, `xmlns:th`, `<head>` pulls Tailwind via
      CDN `<script src="https://cdn.tailwindcss.com"></script>` (no build step, per plan §864).
      Centered max-width container, page title "blame-zeus — Greek Mythology Lore Assistant".
- [ ] **C2 — Query form.** `<form method="post" action="/web/query">` with a text `<input
      name="question">` (pre-filled via `th:value="${question}"`) + submit button. Matches A2's param
      name exactly.
- [ ] **C3 — Result wrapper.** Everything below is inside `th:if="${response != null}"`.
- [ ] **C4 — Route badge.** Color-coded per A3: `SQL` blue / `RAG` green / `MIXED` purple / `null`
      grey. Show the enum name (or "—" for null). Small pill styling.
- [ ] **C5 — Error banner vs answer block (mutually exclusive).**
  - [ ] **C5.1** When `${response.serviceError}` → red banner ("Something went wrong answering that.
        Try rephrasing."), **and hide** the answer/citations/SQL blocks.
  - [ ] **C5.2** Else → answer block: `th:text="${response.answer}"` in a readable prose container.
- [ ] **C6 — Citations as numbered footnotes.** `th:if="${!response.citations.isEmpty()}"`; ordered
      list, one entry per `Citation` as `Author, Work` + `passageRef` (+ `stance` if present). Number
      them so the answer reads with footnote-style references.
- [ ] **C7 — Conflicts section.** `th:if="${!response.conflicts.isEmpty()}"`; a labeled section
      ("Sources disagree") with one block per `ConflictEntry` formatted `sourceAuthor, sourceWork:
      claimValue` (+ `passageRef` when non-null). Renders regardless of route (DEV-014) — do **not**
      gate on `routeDecision`.
- [ ] **C8 — Collapsible SQL block.** `th:if="${response.sqlGenerated != null}"`; a `<details>`/
      `<summary>` ("Show generated SQL") wrapping a `<pre><code th:text="${response.sqlGenerated}">`.
- [ ] **C9** Verify the template renders end-to-end via Track B's `WebControllerTest` (POST path
      exercises C2–C8 for a real response) — no separate template unit test needed.

---

## Track D — `OpenApiConfig.kt` (Springdoc customization)

_Depends on: A4._ New file `config/OpenApiConfig.kt`. Minimal per A4.

- [ ] **D1** `@Configuration class OpenApiConfig` with `@Bean fun customOpenAPI(): OpenAPI` returning
      `OpenAPI().info(Info().title("blame-zeus Core API").version("1.0").description("Greek Mythology
      Lore Assistant — source-attributed Q&A with conflict awareness"))`. Uses springdoc `2.6.0`'s
      `io.swagger.v3.oas.models.*` API surface (DEV-009) — verify imports resolve against `2.6.0`.
- [ ] **D2** (optional polish, not required for done) `@Tag`/`@Operation` on `QueryController`
      endpoints for nicer Swagger grouping. Skip if time-boxed.
- [ ] **D3** Confirm the app still starts and `/v3/api-docs` reflects the custom title (Track F.2).

---

## Track E — Integration + render tests

_Depends on: B + C (render tests); the REST half depends only on Track 0._ Mirror `QueryControllerTest`
(`@AutoConfigureMockMvc` over `AbstractContainerTest`, real seeded data, no mocks).

- [ ] **E1 — `QueryControllerIntegrationTest`** (REST JSON contract; the TODO.md Stage 9 item):
  - [ ] **E1.1** `POST /api/v1/query` → HTTP 200 and `routeDecision` present and ∈ `{SQL,RAG,MIXED}`
        for a normal question.
  - [ ] **E1.2** A **conflict-shaped** question (e.g. "Who were Aphrodite's parents?") returns
        non-empty `conflicts[]` via enrichment **regardless of the route it took** — assert on
        `conflicts[]`, **not** on a CONFLICT route (DEV-014). `[DEVIATED - see DEVIATIONS.md DEV-014]`
  - [ ] **E1.3** (if not already covered) a question whose SQL filter is empty / a refusal still
        returns 200 with a coherent `QueryResponse` (no 500).
- [ ] **E2 — WebController render assertions** already covered by Track B1; if any C-block needs
      explicit coverage (e.g. conflicts section renders for a conflict-shaped POST), add a targeted
      MockMvc body-contains assertion here.
- [ ] **E3** Run full `:core-api:test` — all green.

---

## Track F — Manual browser smoke (last)

_Depends on: B + C + D wired, app runnable (`docker-compose` DB up, seeded)._

- [ ] **F1** `GET http://localhost:8080/` — form renders, Tailwind styles applied.
- [ ] **F2** `GET http://localhost:8080/swagger-ui.html` — Swagger UI loads; title reflects
      `OpenApiConfig` (Track D). `GET /v3/api-docs` returns the spec JSON.
- [ ] **F3** Submit all **17 gold questions** through the web form; for each verify:
  - route badge color matches the expected route (SQL/RAG/MIXED),
  - answer text is present and grounded,
  - citations render as footnotes with author/work/passageRef,
  - conflict-shaped questions show the conflicts section (versions attributed `Author, Work: claim`),
  - SQL questions expose the collapsible SQL block,
  - any refusal / error path shows the error banner cleanly (no stack trace, no blank page).
- [ ] **F4** Record the smoke result; if any question renders wrong, fix the offending Track C block
      (or B binding) and re-run F3 for that question.

---

## Definition of Done (roll-up)

- [ ] `WebController.kt` serves `GET /` + `POST /web/query`, calling the existing
      `QueryService.handle()` — no new query path.
- [ ] `templates/index.html` renders form, route badge (SQL/RAG/MIXED/null), answer + numbered
      citations, conflicts section (route-independent), collapsible SQL, and `serviceError` banner.
- [ ] `OpenApiConfig.kt` sets a custom Swagger title/description (springdoc 2.6.0).
- [ ] `QueryControllerIntegrationTest` proves the JSON contract incl. conflict-via-enrichment
      (DEV-014); `WebControllerTest` proves the HTML render; `:core-api:test` fully green.
- [ ] Manual smoke of all 17 gold questions in-browser passes; Swagger loads.
- [ ] Any deviation logged as `DEV-054+` with inline markers and the §9 stage-note pointer.
