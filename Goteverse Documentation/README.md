# Goteverse documentation

TL;DR:
Use this prompt (agent delivers the four headline bullets **and** writes the archive file, **`git commit`**, and **`git tag wp4-report-*`** — run it on the day you want as the report date, or include an explicit `YYYY-MM-DD` in the message). Reporting to Johan is **email only** (no Word template); paste the bullets into the fortnightly mail.
"Generate the WP4 bi-weekly draft using Goteverse Documentation/WP4_BIWEEKLY_REPORTING.md and the repo since the latest wp4-report-* git tag."

Project notes and **WP4 EU bi-weekly (Citiverse)** reporting material. This folder sits next to the main codebase; use it for programme-facing text, archives, and stable references.

## What’s here

| Item | Purpose |
|------|---------|
| [WP4_BIWEEKLY_REPORTING.md](./WP4_BIWEEKLY_REPORTING.md) | Full workflow: four EU headlines, how to archive, tag (`wp4-report-YYYY-MM-DD`), and generate the next draft from git + archive. |
| [wp4_standing_positions.md](./wp4_standing_positions.md) | Slow-changing LDT / SIMPL / EDIC positions (update when the programme stance changes, not every fortnight). |
| [wp4_reports_archive/](./wp4_reports_archive/) | Archived copies of **sent** report text (one file per report date, e.g. `YYYY-MM-DD.md`). |
| [LDT_toolbox_contribution_note.md](./LDT_toolbox_contribution_note.md), [SIMPL_alignment_note.md](./SIMPL_alignment_note.md) | Extra detail for toolbox and SIMPL alignment when drafting bullets. |
| [MILESTONE_19.md](./MILESTONE_19.md), [MILESTONE_19_SUMMARY.md](./MILESTONE_19_SUMMARY.md) | Milestone-related notes. |

## Quick hint for drafting the next WP4 report

Use the four section titles in `WP4_BIWEEKLY_REPORTING.md`. For a new draft: take the **delta since the latest `wp4-report-*` git tag** (`git log` / `git diff`), read the **newest** file in `wp4_reports_archive/` so you do not repeat unchanged wording, and use `wp4_standing_positions.md` when commits do not cover programme position. The Cursor rule `.cursor/rules/wp4-biweekly-reporting.mdc` does this **and** by default archives, commits, and tags after generating the bullets.
