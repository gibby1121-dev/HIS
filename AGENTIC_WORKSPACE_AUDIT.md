# Agentic Workspace & Architecture Audit

**Date:** 2026-07-03
**Scope:** The HIS repository (`gibby1121-dev/HIS`), its GitHub state, and the
Claude agentic environment attached to it — connectors, plugins, skills,
scheduled routines, automation (Zapier), and session hooks.

**Overall grade: 🟡 Yellow.** The automation layer (skills + routines) is
genuinely well-architected. The repository layer is the weak point: one repo is
carrying at least four unrelated ventures, the PR queue has structural errors,
and there is zero repo-level agent configuration (no CLAUDE.md, no CI, no
tests), so every agent session starts blind.

---

## 1. Repository architecture — 🔴 Red

### 1.1 Identity confusion (the biggest issue)

The HIS repo is currently four different things at once:

| Signal | Says the repo is… |
|---|---|
| GitHub description | "Heartland Iron Solutions — Reusable starter kit for KGFO coworker plugins" |
| `README.md` | "Regenerative soil-biology venture — research, design, and pitch materials" |
| `main` contents | Soil-biology investor deck **and** a Sandhills/Mid-Iowa equipment-market pipeline |
| Open PRs | A personal **Health Advisor** system (#2) and an **AI-creator profile** (#6) |

None of these four workstreams belong together. For an agentic workspace this
is worse than ordinary clutter: every agent session infers project context from
the repo, and here that context is contradictory. An agent asked to "update the
deck" or "extend the pipeline" can plausibly land in the wrong venture.

**Fix:** one repo per venture. At minimum:
- `HIS` → keep the Sandhills/Heartland Iron equipment tooling (matches the repo name).
- Soil-biology venture (deck + screening deck) → its own repo.
- **Health Advisor (PR #2) → a private personal repo, urgently.** It references
  personal health data, lab ranges, medication guardrails, and Vault file IDs.
  Personal medical material should not sit in a business repo's PR queue.
- Creator profile (PR #6) → wherever the content/marketing work lives.

### 1.2 PR queue is structurally broken

| PR | State | Problem |
|---|---|---|
| #3 | open | **Wrong base:** targets feature branch `claude/fungi-…` instead of `main`; its head branch was already merged to main via #5. Fully redundant — close it. |
| #7 | open | **Wrong base and wrong title:** titled as the (already-merged) investor deck, base is a feature branch, head is an unrelated `knowledge-os-visualization` branch. Close or retarget to `main` with a real title. |
| #4 | open | Reuses the branch already merged in #1, so its diff stacks on merged history. Rebase onto `main` or recreate. |
| #2 | open | Health Advisor — move to a private repo (see 1.1), then close here. |
| #6 | open | Creator profile — decide: merge to its proper home or close. |

Five orphaned `claude/*` branches remain on the remote after merges/abandonment.
Enable "automatically delete head branches" in repo settings and prune the rest.

**Root cause worth noting:** the wrong-base PRs (#3, #7) are a known failure
mode when agent sessions open PRs while a previous feature branch is checked
out. A repo-per-venture split plus branch cleanup largely eliminates it.

### 1.3 No repo-level agent configuration

There is no `CLAUDE.md`, no `.claude/settings.json`, no repo skills, no CI
workflow, no PR template, no `.gitignore`, and no tests. Consequences:

- Every session rediscovers the project from scratch (and, per 1.1, often
  misinterprets it).
- Nothing verifies `market_snapshot.py` still runs before a merge.
- The generated artifact `notebooklm_source.md` is committed alongside source —
  it will produce noisy diffs on every pipeline run.

**Fix (small, high leverage):**
1. Add a `CLAUDE.md` stating what the repo is, what it is not, how to run the
   pipeline, and that PRs always target `main`.
2. Add `.gitignore` for `notebooklm_source.md` (or move generated output to an
   ignored `out/` directory).
3. Add a minimal GitHub Actions workflow: `pip install -r requirements.txt &&
   python market_snapshot.py` on sample data + a handful of pytest cases for
   `merge_and_score` / `flag_hot_categories`.

## 2. Pipeline code quality — 🟢 Green

`market_snapshot.py` is in good shape: staged design, loud validation with a
dedicated `PipelineError` and distinct exit codes, import-safe `main()`,
divide-by-zero handling on the engagement score, duplicate collapsing, and
category-average backfill. Minor notes, none blocking:

- No unit tests (covered in 1.3).
- `merge_and_score` reports "Matched N lots" before backfill using `Views`
  notna — correct, but a match-rate below some threshold should probably warn
  loudly given the pipeline's "fail loudly on format drift" philosophy.
- Row-wise `iterrows()`/`apply` rendering is fine at current scale; revisit
  only if inventory grows to tens of thousands of lots.

## 3. Automation layer (skills, routines, Zapier) — 🟢 Green, with trims

### 3.1 Skills — the strongest part of the stack

The claude.ai skill set is a textbook example of encoding recurring business
workflows: `post-sale-auction-recap`, `want-it`, `merge-equipment-listings`,
`org-health-audit`, plus document skills (xlsx/pptx/pdf/docx) and
`skill-creator`. Descriptions are detailed, trigger-scoped, and include
explicit NOT-for clauses — this is how skills should be written.

One gap: `org-health-audit` (the cross-venture structural audit) lives only on
claude.ai and is not loadable inside Claude Code sessions. Cross-venture audits
that need repo access would benefit from a repo-hosted copy under
`.claude/skills/` in whichever repo becomes the "org" home.

### 3.2 Scheduled routines

One routine: **Email triage**, weekdays 15:00 UTC, firing into a persistent
environment with Gmail connected. Prompt is well-scoped (categorize, summarize,
draft — it drafts rather than sends, which is the right guardrail). Two notes:

- The routine's session allows `Bash`, `Write`, `WebFetch`, etc. Inbox content
  is untrusted input; a triage routine only needs Gmail read + draft tools.
  Trimming `allowed_tools` shrinks the prompt-injection blast radius.
- 15:00 UTC = 10:00 AM Central — confirm that's the intended triage time
  year-round (DST shifts it).

### 3.3 Zapier

Connected but effectively unused — only the two stock skills (`mcp-roast`,
`onboarding`) and no evidence of enabled actions in active use. Either build a
real workflow on it (e.g., auction-day notifications) or disconnect it: an
idle, broadly-scoped automation bridge is pure attack surface.

## 4. Connector & plugin surface — 🟡 Yellow

### 4.1 Connectors

9 connected and enabled in-session: Gmail, Google Calendar, Google Drive,
Canva, Zapier, Higgsfield, plus **Crypto.com, Expedia, and Uber** — the last
three have no plausible connection to any active venture and should be
disconnected. 10 more are installed but unconfigured (Adobe, Datadog, GitHub,
Granola, M365, Mixpanel, Notion, Playwright, Postman, Windsor.ai) — remove the
ones you don't intend to finish connecting.

**Security note (the important one):** the current default session combines
(a) untrusted content sources (Gmail inbox, web), (b) sensitive private data
(Drive/Vault, health material), and (c) outbound write channels (Gmail drafts,
Zapier, Drive writes). That trio is the classic prompt-injection exfiltration
setup. It's manageable, but deliberately: keep high-sensitivity work (Health
Advisor/Vault) in sessions with the minimum connector set, and don't run
inbox-reading routines with write-capable tools enabled (see 3.2).

### 4.2 Plugins

21 plugins enabled. Several map to real workflows (`tractorhouse-vault`,
`small-business`, `marketing`, `content-writer-assistant`, `pdf-viewer`). But
`cockroachdb`, `daloopa`, `intercom`, `apollo`, `adspirer-ads-agent`,
`bigdata-com`, `nimble`, `brightdata-plugin`, `postiz`, `box` look speculative.
Every enabled plugin adds tools and context to every session, degrading tool
selection. Disable anything not used in the last month; re-enabling takes
seconds.

## 5. Session hooks & environment — 🟢 Green

The remote-execution environment is correctly configured: SessionStart hook
pins the git signing identity, Stop hook enforces commit-and-push before a
session ends, and permissions are minimal. No action needed.

---

## Execution status (2026-07-03)

Applied in this session:

- ✅ Closed PR #3 (redundant, wrong base) and PR #7 (wrong base/title;
  `knowledge-os` branch retained for re-targeting).
- ✅ Closed PR #2 (Health Advisor) without merge; branch retained pending
  migration.
- ✅ Added `CLAUDE.md`, `.gitignore`, CI workflow, and a 10-case pytest suite;
  untracked generated `notebooklm_source.md`; corrected README identity.
- ✅ **Fixed a real bug the new tests caught:** a lot with `DaysOnMarket = 0`
  crashed `merge_and_score` (object-dtype `pd.NA` has no `__round__`); now
  handled via nullable `Float64`.
- ✅ Re-checked PR #4: its diff against `main` is actually clean (only the two
  screening-deck commits) — left open pending the soil-biology repo split.

Blocked (needs owner action — the GitHub integration cannot create repos or
delete branches):

- ⛔ Create a **private** repo for Health Advisor; then the migration from
  `claude/health-advisor-vault-nd18hf` can be completed and the branch deleted.
- ⛔ Create a repo for the soil-biology venture (decks), then close PR #4 and
  remove `investor-deck.md` from HIS.
- ⛔ Delete remote branch `claude/inventory-webstats-merge-score-evuuow`
  (content already merged via #5); enable "automatically delete head branches"
  in repo settings.
- ⛔ Update the GitHub repo description (currently "Reusable starter kit for
  KGFO coworker plugins").
- ⛔ Connector/plugin trims (claude.ai settings): disconnect Crypto.com,
  Expedia, Uber; prune unused plugins; tighten Email-triage routine tools.

## Top 5 fixes, ranked

1. **Move Health Advisor (PR #2) out of HIS into a private repo** — personal
   medical data in a business repo's PR queue is both a privacy and hygiene
   problem.
2. **Split the repo by venture and fix the README/description mismatch** so
   agents stop inheriting contradictory context.
3. **Close the broken PRs (#3, #7), rebase #4, decide #6**, delete merged
   `claude/*` branches, and enable auto-delete of head branches.
4. **Add `CLAUDE.md` + `.gitignore` + a minimal CI run + pytest smoke tests**
   to HIS so agent sessions start informed and merges stay verified.
5. **Trim the surface:** disconnect Crypto.com/Expedia/Uber, prune unused
   plugins and unconfigured connectors, tighten the Email-triage routine's
   tool list, and either use or disconnect Zapier.
