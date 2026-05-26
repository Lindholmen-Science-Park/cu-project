# How we could provide to the LDT toolbox

**Context:** Milestone 19 requires that we “utilise and contribute to the LDT-toolbox in a way that provides value to the programme and other work packages.” This note outlines **concrete ways we could provide (contribute) to the LDT toolbox**, pending alignment with the actual LDT deliverables and ownership.

---

## 1. What we could contribute

Depending on what the LDT toolbox accepts and how it is structured, we could provide:

### 1.1 Tooling and scripts

| Asset | Description | LDT value |
|-------|-------------|-----------|
| **OSM road graph pipeline** | `source/data/osm/generate_roads.py` — Offline OSM data fetch, graph build, USD export for city-scale wayfinding. | Reusable “OSM → graph → scene” pipeline for any city/venue using OSM. |
| **AI training pipeline** | `tools/ai_training/` — Data prep, `train.py`, Modelfile, POI/navigation intent training. | Pattern and tooling for POI/NLP + navigation in 3D/wayfinding pilots. |
| **Seat/layout tooling** | Seat lookup generation, layout variants (see seat-navigation topic). | Conventions and scripts for seat-based navigation and evacuation studies. |

### 1.2 Conventions and patterns

| Asset | Description | LDT value |
|-------|-------------|-----------|
| **Extension layout** | premake5.lua, extension.toml, `.kit` registration, Python package layout. | Shared structure for Omniverse/Kit extensions so other WPs can add features consistently. |
| **Orchestrator patterns** | Payload/visibility orchestrator (show/hide/load/unload); NavMesh Bake Orchestrator + `NavMeshAreaProvider` protocol. | Reusable patterns for scene lifecycle and rebake coordination. |
| **Event/messaging contract** | `younite.messaging_core_extension`, outbound events, `events_contracts.py`. | Common event names and payloads for web–Kit and cross-extension use. |
| **Interactions schema** | `interactions.json` schema, Collider convention, projectable overlays, action registry. | Data-driven interaction and overlay model usable by other pilots. |

### 1.3 Data formats and schemas

| Asset | Description | LDT value |
|-------|-------------|-----------|
| **POI index** | `poi_index.json` shape and usage (ids, names, coords, optional metadata). | Common POI format for wayfinding and AI across work packages. |
| **Interactions config** | `interactions.json` (primName/primPath, triggers, speech, mapMarker, etc.). | Standard config format for interactive objects and NPCs. |
| **Sublayer conventions** | Scene composition, layer naming, which layers carry what (see sublayers.mdc). | Shared USD/scene layout conventions for multi-WP scenes. |

### 1.4 Documentation

| Asset | Description | LDT value |
|-------|-------------|-----------|
| **Topic rules** | `.cursor/rules/topics/` — navmesh-areas, bake-orchestrator, route-measurement, osm-navigation, interactions, seat-navigation, incidents, etc. | Design and implementation guidance that can be reused or adapted in LDT docs. |
| **Extension READMEs** | e.g. `navmesh_route_extension`, `osm_navigation_extension`, `ai_training/README.md`. | How to use wayfinding, OSM, and AI tooling in other projects. |

---

## 2. How do we actually contribute?

**Short answer:** We can’t complete the handover until we know **where** the toolbox lives and **how** contributions are accepted. Below: what to find out, then what to do.

### 2.1 What we need from the programme

| Question | Why it matters |
|----------|-----------------|
| **Where is the LDT toolbox?** (Git repo, SharePoint, wiki, shared drive?) | Determines how we submit (PR, upload, form, link). |
| **Who owns / curates it?** (WP lead, PM, specific deliverable owner?) | We need a single contact to ask “how do we add X?”. |
| **What format do contributions take?** (Code in a repo, PDF/doc, schema files, links to our repo?) | So we package the right thing. |
| **Is there a process or template?** (Contribution checklist, naming, licence?) | So our contribution is accepted and discoverable. |

**Action:** Johan (or whoever reports to Anna/Monica) should ask the programme or the LDT deliverable owner these questions. Until then, we contribute “in spirit” by documenting and preparing (see below).

### 2.2 What we can do now (without the toolbox structure)

1. **Document our offer**  
   Keep this note and the “What we could contribute” list (section 1) up to date. Reference it in D4.3 / Milestone 19 so the programme sees we’re ready.

2. **Make our repo and docs easy to reuse**  
   - Ensure key paths are documented (e.g. in MILESTONE_19.md, README, topic rules).  
   - Tag a release or branch (e.g. `milestone-19` or `v0.x`) so LDT/other WPs can point to a stable snapshot.

3. **Prepare one or two “contribution packages”**  
   So that when the process is clear, we can submit quickly:  
   - **Option A:** A short doc (1–2 pages) that describes the OSM pipeline + link to `source/data/osm/generate_roads.py` and a minimal README for that script.  
   - **Option B:** A schema/example doc for `poi_index.json` and `interactions.json` (fields, meaning, example snippet).  
   Put these in `docs/` or a small `docs/ldt_contrib/` folder; when LDT asks for “something to drop in”, we already have it.

4. **Use the milestone wording**  
   In reports and D4.3: “We utilise and contribute to the LDT-toolbox; we have documented our candidate contributions and are ready to hand over once the LDT deliverable structure and process are confirmed.”

### 2.3 What we do once we know where and how

- **If toolbox = Git repo:** Fork or get access, add our artefact (script + README, or schema doc), open a PR or push to an agreed branch; follow any CONTRIBUTING or template.
- **If toolbox = shared drive / SharePoint:** Upload the prepared doc or zip (script + README, or schema doc) to the agreed folder; use the naming convention they specify.
- **If toolbox = “link to external repos”:** We don’t “upload”; we send the maintainer our repo URL and the path(s) to the relevant assets (e.g. `.../source/data/osm/generate_roads.py`, `docs/...`); they add a pointer in the toolbox.
- **If there’s a catalogue or index:** Register our contribution (title, one-line description, link or attachment) so other WPs can find it.

In all cases: one owner (e.g. tech lead or WP lead) does the handover and records in the milestone what was actually contributed (e.g. “OSM pipeline doc + link to script in repo X”).

---

## 3. Modes of providing (once process is clear)

- **Documentation only:** Describe the above in a short “Goteverse-Omniverse contribution to LDT” section (in D4.3 or milestone annex). No handover of code yet; LDT can reference our repo or docs.
- **Packaged artefacts:** Contribute specific items (e.g. script + README, or schema doc for `interactions.json` / `poi_index.json`) to the LDT repo or shared drive.
- **Living alignment:** Document where our repo lives and which paths/versions to use; LDT (and other WPs) consume from our repo or from tagged releases.

---

## 4. Suggested next steps

1. **Clarify with LDT owners** (via Johan or programme) what the toolbox contains and how contributions work (see section 2.1).
2. **Do the "now" actions** in section 2.2 (document, tag repo, prepare one or two contribution packages).
3. **When the process is known,** perform the handover (section 2.3) and update MILESTONE_19.md section 4 (and MILESTONE_19_SUMMARY.md) with the concrete examples contributed.

---

## 5. One-sentence for the milestone (with placeholder)

*“We provide to the LDT toolbox by [e.g. contributing OSM wayfinding tooling and data-format conventions / documenting our extension and event patterns for reuse / …], and will add concrete artefacts once the LDT deliverable structure is confirmed.”*

Use the placeholder until LDT deliverables and handover process are fixed; then replace with the agreed contribution list.
