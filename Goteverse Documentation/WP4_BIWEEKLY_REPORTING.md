# WP4 bi-weekly reporting (CU / Citiverse)

**Context:** Email thread in [THREAD.md](./THREAD.md). Johan needs a few short bullets per headline for the EU-aligned report (same structure across Citiverse projects). *“No activity” is valid information.*

**Recipients:** Every two weeks, send Johan a **manual email** (same thread as [THREAD.md](./THREAD.md)) with the four programme headlines as short bullets — there is **no separate Word template**, only email text.

**Agent rule (Cursor):** [@wp4-biweekly-reporting](.cursor/rules/wp4-biweekly-reporting.mdc).

**One prompt (default — full automation):** *“Generate the WP4 bi-weekly draft using this file and the repo since the last `wp4-report-*` tag.”* The agent outputs the four headlines **and** writes `wp4_reports_archive/YYYY-MM-DD.md`, **`git commit`**, and **`git tag wp4-report-YYYY-MM-DD`** (report date = today unless you state another `YYYY-MM-DD` in the message). **Opt out of git:** add *draft only* / *no git* / *bullets only* if you only want the text.

**Your remaining step toward Johan:** paste the bullets into the email — unless you edit them afterward, the archived copy matches what you send.

---

## Workflow: tag + archive (after each submission)

A **baseline** (`wp4-report-*` tag + archive file) is required for a clean next delta. **Normally the agent does steps 2–4** in the same turn as the draft (see Cursor rule). Manual steps below apply if you work without the agent or need to fix history.

**Draft vs archive:** Programme wording prefers the **exact sent** text. If you change bullets after the agent run, ask the agent to update the archive (or edit the file) so the repo stays aligned with what Johan received.

1. **Finalise** the four sections (Laura/Vivian review if needed).
2. **Archive** — Save the **exact sent text** to `Goteverse Documentation/wp4_reports_archive/YYYY-MM-DD.md` (create a new file per report date). The first baseline is [wp4_reports_archive/2026-03-24.md](./wp4_reports_archive/2026-03-24.md).
3. **Commit** the repo state you want as the baseline (at least the archive update and any doc changes).
4. **Tag** that commit:
   ```bash
   git tag wp4-report-YYYY-MM-DD
   ```
   Example: `git tag wp4-report-2026-03-24`
5. **Slow-changing context** — If LDT/SIMPL/EDIC *programme* position changes, update [wp4_standing_positions.md](./wp4_standing_positions.md) (not every fortnight).

*Next report:* an agent (or you) runs `git log wp4-report-<previous>..HEAD` and reads the **latest** archive file to avoid copy-paste repetition.

---

## Agent workflow (generate next draft)

1. Resolve **latest** tag: `git tag -l 'wp4-report-*' | sort | tail -1`
2. **Delta:** `git log <that-tag>..HEAD --oneline` and optionally `git diff <that-tag>..HEAD --stat`
3. Read **newest** `Goteverse Documentation/wp4_reports_archive/*.md` — do **not** repeat unchanged bullets; stress what is **new** or say honestly that a headline has no new activity.
4. Read **`Goteverse Documentation/wp4_standing_positions.md`** for LDT/SIMPL/EDIC when commits do not cover it.
5. Deep detail only if needed: [LDT_toolbox_contribution_note.md](./LDT_toolbox_contribution_note.md), [SIMPL_alignment_note.md](./SIMPL_alignment_note.md)
6. Output **only** the four EU headlines below, 1–3 bullets each.
7. **Persist baseline (default):** write those same four sections to `wp4_reports_archive/YYYY-MM-DD.md`, then `git add`, `git commit`, `git tag wp4-report-YYYY-MM-DD` — unless the user asked **draft only** / **no git** (see Cursor rule).

---

## Headlines (use these titles in the email to Johan)

### 1. Contribution to the technological stack of the LDT Toolbox through open-source tools/ AI models/ technologies:

### 2. Reuse and testing of LDT Toolbox solutions (e.g. the EU building dataset or others):

### 3. Federation of datasets through SIMPL for testing/usage of cities in experimentation facilities/pilots:

### 4. Progress of preparatory activities to transfer technologies/datasets/solutions/services to the EDIC:

---

## Draft — **24 March 2026** (paste into email to Johan)

*Canonical archived copy: [wp4_reports_archive/2026-03-24.md](./wp4_reports_archive/2026-03-24.md). After send: commit + `git tag wp4-report-2026-03-24`.*

*Source alignment: [THREAD.md](./THREAD.md) (Johan’s four headlines); [LDT_toolbox_contribution_note.md](./LDT_toolbox_contribution_note.md); [SIMPL_alignment_note.md](./SIMPL_alignment_note.md). Vivian/Aki: align with Laura before sending if anything is sensitive.*

### 1. Contribution to the technological stack of the LDT Toolbox through open-source tools/ AI models/ technologies:

- WP4 continues development on an **OpenUSD** scene graph with **NVIDIA Omniverse Kit** (streaming viewer), **modular Python extensions**, and a **web client**—open, reusable patterns for digital-twin pilots.
- **Candidate contributions to the LDT toolbox** (documented internally for handover once the programme’s contribution channel is confirmed) include: **OSM → graph → scene** tooling, **AI training** patterns for POI/navigation-style intents, **payload / NavMesh bake orchestrator** patterns, **web–Kit messaging contracts**, and **data-driven interaction** schemas (`interactions.json`, POI index conventions). *(See LDT contribution note.)*

### 2. Reuse and testing of LDT Toolbox solutions (e.g. the EU building dataset or others):

- **EU building dataset:** No integration or testing of the EU building dataset in this reporting period *(unless you have concrete activity—then replace this bullet)*.
- **LDT toolbox outputs:** Reuse is **pending clarification** of where the LDT toolbox lives and how other WPs should consume or test its deliverables; WP4 has **mapped what we can offer** (scripts, schemas, docs) so we can plug in quickly once the process is agreed.

### 3. Federation of datasets through SIMPL for testing/usage of cities in experimentation facilities/pilots:

- **SIMPL** (EC middleware for data spaces) is **relevant** to our city-oriented experimentation facilities: **Smart Communities Data Space** and **Simpl-Labs** match the headline’s intent (federated city data for pilots).
- **This period:** **No SIMPL connector or runtime integration** in the stack yet; we are **documenting alignment and assessment**—our pilots and datasets (e.g. OSM, POI, scene data) are **candidates** to consume or expose federated city data via SIMPL when the programme’s expectations and entry points (e.g. Simpl-Labs) are clear. *(See SIMPL alignment note.)*

### 4. Progress of preparatory activities to transfer technologies/datasets/solutions/services to the EDIC:

- Engineering continues to structure capabilities as **extensions and services** (streaming, navigation, interactions, AI hooks) suitable for **later formal handover**; **no EDIC transfer milestone completed** this reporting period.
- **Preparatory (parallel to LDT):** Internal documentation of **candidate artefacts** and **stable repo references** (e.g. for milestone/D4.3 packaging) supports eventual transfer once EDIC and toolbox processes are defined.

---

### Optional compact email block (all four topics in one paragraph)

You can use this shorter form in the same email if you prefer one continuous block instead of four titled sections.

> **1. LDT technological stack** — WP4 builds on OpenUSD, Omniverse Kit, modular extensions, and a web streaming client. We have documented candidate contributions for the LDT toolbox (OSM/scene pipeline, AI training patterns, orchestration and messaging patterns, interaction/POI schemas); actual submission awaits the programme’s toolbox location and contribution process.  
> **2. Reuse/testing LDT solutions** — No use of the EU building dataset this period. Reuse of other LDT outputs is pending clarification of toolbox access and testing expectations.  
> **3. SIMPL** — We recognise SIMPL as the relevant federation layer for city data in pilots (Smart Communities / Simpl-Labs). There is no technical integration yet; we report alignment under assessment and pilots as a natural fit for future federation.  
> **4. EDIC** — Ongoing packaging as extensions/services; no formal EDIC transfer step completed this period.

---

## Pattern for **future** fortnights

Reuse the four headings above. Under each, 1–3 bullets max. Prefer facts (what changed, what was tested, what was delivered) over generic claims.

| Headline | What EU is asking (in practice) |
|----------|----------------------------------|
| 1 | New or continued use of open tech, AI models, or shared tooling. |
| 2 | Use of LDT outputs (datasets, components) in your pilot. |
| 3 | SIMPL and federated city / experiment data. |
| 4 | Steps toward making results reusable via EDIC. |

---

*Last updated: tag + archive workflow, standing positions, Cursor rule `wp4-biweekly-reporting.mdc` (March 2026).*
