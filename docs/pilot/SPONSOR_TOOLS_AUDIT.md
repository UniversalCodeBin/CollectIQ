# PayPal hackathon sponsor tools: repository audit

Audit date: 2026-11-08. Repository state: branch `build/m0-m8`, HEAD `7bb46ca`.
Scope: the ten sponsor tools named in the hackathon brief. This was a read-only audit. No application code,
dependencies, lockfiles, deployment configuration or existing documentation were changed, and nothing was installed.
`CollectIQ_Post_Implementation_Audit.md` (untracked) was not read or modified.

## 1. Executive summary

CollectIQ does not use any of the ten sponsor tools. Repository evidence is consistent across every place
that could show usage: tracked source, both lockfiles, manifests, CI, compose files, the OpenAPI pipeline,
the installed backend virtualenv and frontend `node_modules`, environment variable names, and git history.

Each of the ten tools appears only in one internal document, `docs/implementation-audit.md` section 6
(lines 128–137, added in commit `1facbae`). That section assesses the tools and records that none is adopted.
That is a documented assessment, so each tool is classified **D. Mentioned only**. None is classified A, B or C.

| # | Sponsor tool | Classification | Runtime use | Dependency present | Confidence |
|---|---|---|---|---|---|
| 1 | AG Grid | D. Mentioned only | No | No | High |
| 2 | APIMatic | D. Mentioned only | No | No | High |
| 3 | Astropods | D. Mentioned only | No | No | High |
| 4 | Bryntum | D. Mentioned only | No | No | High |
| 5 | Channel3 | D. Mentioned only | No | No | High |
| 6 | Elastic | D. Mentioned only | No | No | High |
| 7 | KERNEL | D. Mentioned only | No | No | High |
| 8 | Postman | D. Mentioned only | No | No | High |
| 9 | Render | D. Mentioned only | No | No | High |
| 10 | Zapier | D. Mentioned only | No | No | High |

Confidence is high that the tracked repository and its local install contain no sponsor code or dependency.
Confidence is lower about anything outside the repository, such as a Render dashboard or a Postman workspace,
because those are not visible here. The repository has no git remote, so no hosted CI or deployment history is available.

## 2. Repository inspection methodology

1. **Text search across all tracked files.** `git grep -in` for each name and its common variants (`ag-grid`, `aggrid`,
   `ag grid`, `apimatic`, `astropods`, `bryntum`, `channel3`, `elastic`, `elasticsearch`, `opensearch`, `kernel`,
   `postman`, `render.com`, `onrender`, `render.yaml`, `zapier`). Lockfiles were included, not excluded.
2. **Manifests and lockfiles.** Read `frontend/package.json` and `backend/pyproject.toml` in full, and confirmed that
   `frontend/package-lock.json` and `backend/uv.lock` contain no sponsor package name.
3. **Installed packages.** Listed `backend/.venv/lib/python3.12/site-packages` (distribution names) and
   `frontend/node_modules` (top level and `@`-scoped directories) and searched both for sponsor names.
4. **Build, CI and deployment.** Read `.github/workflows/ci.yml`, `compose.yaml`, `deploy/compose.prod.example.yaml`
   and the `Makefile` targets. No `render.yaml`, Dockerfile for a hosting platform, or Postman, Zapier or Elastic
   configuration exists.
5. **OpenAPI and client generation.** Checked how the API contract is produced and consumed:
   `drf-spectacular` on the backend (`make openapi`) writes `docs/api/openapi.generated.yaml`, and
   `openapi-typescript` (`frontend/package.json`, script `gen:api`) generates `frontend/src/lib/api-types.ts`.
   No APIMatic SDK generator or developer portal is involved.
6. **Environment and configuration.** Searched `.env.example` (tracked) and listed the variable names only, without
   values, from the ignored local `.env`. No sponsor variable names were present in either.
7. **Ignored and generated directories.** Searched `.superpowers/`, `var/`, `frontend/dist/`, `frontend/test-results/`
   and `backend/.test-storage/`. No matches. Checked the Stitch export archive file listing. No matches.
8. **Git history.** `git log --all -i --grep` and `git log --all -S` for each name. Every match for a vendor name
   traces to commit `1facbae` (the audit document) or to commit `5cd78f1` (for the word "kernel", see section 4).
9. **Lexical false positives reviewed and rejected.** The word "render" matches React Testing Library's `render`
   (commits `9765c19`, `6ad2a78`, `2032577`) and Django REST Framework's `JSONRenderer`
   (`backend/collectiq/platform/idempotency.py:11,85`, `backend/collectiq/settings/base.py:86`). "Kernel" matches
   CollectIQ's own internal labels: "Platform kernel" in the architecture diagram of `CollectIQ_SAD_v0.1.md:223`
   (added in commit `5cd78f1`), and "System Kernel" / "KERNEL ACTIVE" in Stitch UI exports
   (`stitch_collectiq_receivables_copilot/*/code.html`). None refers to the KERNEL vendor.

Not inspected: the vendor websites were not browsed, because the question is about use in the repository, not product
capability. Capability statements in section 8 come from the earlier assessment in `docs/implementation-audit.md`
(sources dated 2026-11-04). They were not re-verified in this audit.

## 3. Evidence for each classification

Each row cites the assessment in `docs/implementation-audit.md`. "No" in the runtime column means no code, import,
configuration or dependency for the tool exists anywhere in the tracked repository, the local virtualenv or `node_modules`.

### 3.1 AG Grid. D. Mentioned only

- **Identifiers searched:** `ag-grid`, `ag-grid-community`, `ag-grid-react`, `aggrid`, `ag grid`. None found in any file.
- **Where it appears:** `docs/implementation-audit.md:128`. Row says: the queue order comes from the server, so a plain table
  is enough, and Community is "a possible later swap".
- **Actual frontend:** plain HTML tables and lists. No grid component import (`frontend/src/**`).
- **Runtime use:** no. **Installed:** no.

### 3.2 APIMatic. D. Mentioned only

- **Identifiers searched:** `apimatic`, `@apimatic/*`, `apimatic-cli`, `apimatic-sdk`. None found.
- **Where it appears:** `docs/implementation-audit.md:129`. The row says `openapi-typescript` already covers the one
  client needed.
- **Actual API tooling:** `drf-spectacular` (`backend/pyproject.toml`), `make openapi`, `openapi-typescript` (`frontend/package.json`).
  These are open-source generators, not APIMatic. Having an OpenAPI document does not show APIMatic is used.
- **Runtime use:** no. **Installed:** no.

### 3.3 Astropods. D. Mentioned only

- **Identifiers searched:** `astropods`. None found.
- **Where it appears:** `docs/implementation-audit.md:130`. Row says the AI is "a constrained gateway, not agents", and that the
  assessment was based on marketing and blog sources, not the vendor's docs.
- **Actual AI layer:** an in-house bounded gateway with its own tool registry (`backend/collectiq/ai/`). Having an in-house
  agent-like layer does not show Astropods is used.
- **Runtime use:** no. **Installed:** no.

### 3.4 Bryntum. D. Mentioned only

- **Identifiers searched:** `bryntum`, `@bryntum/*`. None found.
- **Where it appears:** `docs/implementation-audit.md:131`. Row says no scheduling UI is in scope.
- **Actual UI:** no scheduler, Gantt or commercial grid component in `frontend/package.json`.
- **Runtime use:** no. **Installed:** no.

### 3.5 Channel3. D. Mentioned only

- **Identifiers searched:** `channel3`, `trychannel3`. None found.
- **Where it appears:** `docs/implementation-audit.md:132`. Row says "No fit."
- **Runtime use:** no. **Installed:** no.

### 3.6 Elastic. D. Mentioned only

- **Identifiers searched:** `elastic`, `elasticsearch`, `opensearch`, `@elastic/*`, `elastic-apm`, `elasticapm`. Only `docs/implementation-audit.md:133` matches.
- **Where it appears:** row says PostgreSQL search and structured logs are enough at this scale.
- **Actual search and logging:** PostgreSQL with row-level security, and the in-database audit chain (`backend/collectiq/audit/`).
  No Elasticsearch client, index or log shipper exists.
- **Runtime use:** no. **Installed:** no.

### 3.7 KERNEL. D. Mentioned only

- **Identifiers searched:** `kernel.sh`, `@onkernel/*`, `kernel` as a vendor reference. The only vendor reference is
  `docs/implementation-audit.md:134`, which says "No fit. Automating bank portals is out of scope."
- **Lexical false positives:** "System Kernel" and "KERNEL ACTIVE" labels in the Stitch export and the SAD diagram refer to CollectIQ's
  own policy engine (see section 2, item 9). They are not the vendor.
- **Runtime use:** no. **Installed:** no.

### 3.8 Postman. D. Mentioned only

- **Identifiers searched:** `postman`, `.postman_collection.json`, `newman`, `postman-collection`, `@postman/*`. None found, apart from `docs/implementation-audit.md:135`.
- **Actual API testing:** `schemathesis` and `pytest` (`backend/pyproject.toml` dev group). Having API tests does not show Postman is used.
- **Runtime use:** no. **Installed:** no. No Postman collection file exists in the repository.

### 3.9 Render. D. Mentioned only

- **Identifiers searched:** `render.com`, `onrender`, `render.yaml`, `render-cli`. Only `docs/implementation-audit.md:136` matches.
- **Where it appears:** row calls Render "a candidate deploy target under OD-04", needing the owner's decision, and says
  "T40 stays local". `docs/pilot/open-decisions.md` lists OD-04 as an open decision.
- **Actual deployment:** `compose.yaml` (local, Postgres 16 only) and `deploy/compose.prod.example.yaml` (api, worker, scheduler,
  migrate, ClamAV and Postgres services for Docker Compose). No Render blueprint, service definition or deploy step exists.
- **Runtime use:** no. **Installed:** no.

### 3.10 Zapier. D. Mentioned only

- **Identifiers searched:** `zapier`, `zapier-platform`, `@zapier/*`. Only `docs/implementation-audit.md:137` matches.
- **Where it appears:** row says Zapier "conflicts with the no-auto-send and no-auto-allocate rules" (`CLAUDE.md` rules).
- **Actual background jobs:** a database-backed worker and scheduler (`backend/collectiq/platform`, `make worker`). Background jobs do not show Zapier is used.
- **Runtime use:** no. **Installed:** no.

## 4. Git history

- Every vendor-name match in history is in commit `1facbae` (`docs: implementation audit and requirement-level traceability`),
  which introduced the section 6 assessment. No commit adds a dependency, import or configuration for any sponsor tool.
- `git log -S` matches for `kernel` in commit `5cd78f1` (`chore: repo baseline and local database`) are the "Platform kernel"
  diagram label in the SAD. `git log -S` matches for `render` in commits `9765c19`, `6ad2a78` and `2032577` are React Testing
  Library's `render` import. Neither is a sponsor tool.
- `git remote` is empty, so this history is local only.

## 5. Implemented sponsor integrations

**None.** No sponsor tool is implemented in CollectIQ's code, configuration, deployment or tests.

## 6. Installed-but-unused dependencies

**None.** No sponsor package appears in `frontend/package.json`, `frontend/package-lock.json`, `backend/pyproject.toml`,
`backend/uv.lock`, the installed `backend/.venv` distributions, or `frontend/node_modules`.

## 7. Mentioned-only tools

All ten tools. Each appears only in `docs/implementation-audit.md` section 6:

| Tool | Line | Documented position |
|---|---|---|
| AG Grid | 128 | Plain table is enough; Community is a possible later swap |
| APIMatic | 129 | `openapi-typescript` already covers the one client needed |
| Astropods | 130 | Would add a second place for agent payloads; not adopted |
| Bryntum | 131 | No scheduling UI in scope |
| Channel3 | 132 | No fit |
| Elastic | 133 | PostgreSQL search and structured logs are enough at this scale |
| KERNEL | 134 | No fit; bank-portal automation is out of scope |
| Postman | 135 | Optional developer aid at most, never a product dependency |
| Render | 136 | Candidate deploy target under OD-04; owner decision needed |
| Zapier | 137 | Conflicts with the no-auto-send and no-auto-allocate rules |

## 8. Hackathon relevance and recommended sponsor integrations

Capability and price claims below come from the earlier assessment (`docs/implementation-audit.md`, sources dated 2026-11-04)
and were not re-checked against vendor sites in this audit. Anything marked "unverified" should be checked before a decision.

| Tool | Relevance to CollectIQ | Recommendation | Module | Complexity | Security and privacy | Necessary? |
|---|---|---|---|---|---|---|
| **Render** | Would host the existing API, worker, scheduler and Postgres for a hosted demo. The prod compose example already defines these services. | **Optional, consider for the hackathon demo.** Needs the OD-04 decision first. The earlier assessment says to check that Render's Postgres roles allow forced row-level security. Persistent always-on worker and scheduler are needed. ClamAV would need its own container. | Deploy only; no code change | Medium (service split, secrets, migrations, ClamAV container) | Customer receivables data would sit with a third party. Needs review of the data-processing terms and secret handling. Pricing unverified. | No. The repository runs locally without it. |
| **Postman** | Could export a collection from the OpenAPI document for judges or partners to try the API. | **Optional developer artifact.** Generate an importable collection from `docs/api/openapi.generated.yaml`. Use placeholders only. Do not commit tokens. | Docs and dev tooling | Low | A collection file can leak credentials if one is saved in it. Keep the export free of secrets. | No |
| **AG Grid** | Could help with sorting, filtering and large invoice or reconciliation tables. | **Only if a real table needs it.** Current tables are plain. Community edition license per the earlier assessment, unverified here. | `frontend/src/features/**` tables | Medium (bundle size, styling against the Stitch design system) | Client-side only. Adds a dependency to a screen that shows customer data. | No |
| **Elastic** | Search and log analysis across audit events. | **Defer.** Copying audit or customer data into a search index creates a second store of personal data and works against the append-only audit design. Consider only for operational logs, after a privacy review. | Would sit beside `audit/` | High | Adds a second copy of personal data. Needs its own retention and access rules. | No |
| **APIMatic** | SDK and developer-portal generation. | **Not recommended.** `openapi-typescript` and `drf-spectacular` already produce what the product needs. | None | High | No product benefit | No |
| **Zapier** | Workflow automation across apps. | **Not recommended for customer messages.** Conflicts with the human-approval rule and the no-auto-send rule in `CLAUDE.md`. | None | Low, but the rule conflict rules it out | Would let an external automation send or change data | No |
| **Astropods** | Agent infrastructure. | **Not recommended.** The AI layer is a bounded gateway with its own tool registry. Adding agent infrastructure would add a second place where payloads flow. Vendor capabilities not verified here. | None | High | Adds an external payload path | No |
| **KERNEL** | Browser infrastructure for agents, with stealth, CAPTCHA handling and credential vaults. | **Not recommended.** Stealth and credential-vault features conflict with the product's scope and privacy posture, and bank-portal automation is out of scope. | None | High | Credential handling and anti-bot evasion are the wrong direction for this product | No |
| **Bryntum** | Scheduling and Gantt components. | **Not recommended.** No scheduling UI is in scope. | None | High | None | No |
| **Channel3** | Product catalogue search. | **Not recommended.** No fit with receivables. | None | Not applicable | None | No |

None of these is necessary for CollectIQ to run, test or be demonstrated locally. The only one with a clear hackathon
benefit is Render, as a hosted demo, and that depends on a business decision (OD-04) and possibly a payment.

## 9. Hackathon relevance

- **Product fit:** the product's value is in receivables follow-up with human approval. None of the sponsor tools is needed for that.
- **Architectural cost:** each added service is a second place for customer data. The repository already enforces tenant isolation
  and an append-only audit trail inside PostgreSQL, so external stores would need the same guarantees.
- **Demonstration:** the product can be demonstrated locally with `make dev` and the e2e suite (`make e2e`). A hosted URL is the
  only thing a sponsor tool would meaningfully add.

## 10. Risks and limitations

- **Scope of the search.** The search covers the repository as tracked and locally installed. It cannot see vendor accounts,
  hosted dashboards, Postman workspaces, Render services or anything not committed.
- **No remote.** `git remote -v` is empty, so no hosted CI history is available. `.github/workflows/ci.yml` says it has not run.
- **Name collisions.** Generic words ("render", "kernel") were checked by hand. Future code could reuse those words for unrelated reasons.
- **Earlier assessment.** Capability and pricing claims in section 8 come from `docs/implementation-audit.md`. This audit did not re-verify them.
- **Environment values.** Only environment variable names were read from the local `.env`. Values were not read or recorded.
- **Stitch archive.** Only file names inside `stitch_collectiq_receivables_copilot.zip` were checked, not their contents, because the
  extracted export in the repository was already searched.

## 11. Final sponsor-tool usage statement

Suitable for an honest hackathon submission:

> CollectIQ did not use any of the ten PayPal hackathon sponsor tools (AG Grid, APIMatic, Astropods, Bryntum, Channel3,
> Elastic, KERNEL, Postman, Render, Zapier) in its code, dependencies, configuration, deployment or tests. These tools
> appear only in the project's internal implementation audit, where they were assessed and not adopted, or noted as a
> possible later option. The project's own tooling includes Django, Django REST Framework, drf-spectacular, PostgreSQL,
> React, Vite, openapi-typescript, Vitest, Playwright, pytest and schemathesis. The project does include a PayPal
> integration, but PayPal is the hackathon host and is not on the sponsor list.
