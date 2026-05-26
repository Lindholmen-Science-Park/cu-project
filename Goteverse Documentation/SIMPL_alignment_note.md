# Federation of datasets through SIMPL — Relevance and alignment note

**Context:** Answer for bi-weekly documentation headline: *"Federation of datasets through SIMPL for testing/usage of cities in experimentation facilities/pilots"* (following meeting with Anna and Monica).

---

## 1. What is SIMPL?

**SIMPL** is an open-source, smart and secure **middleware platform** from the European Commission that supports **data access and interoperability** among European data spaces. It is a key enabler of the Common European Data Spaces.

- **Simpl-Open:** The open-source software stack that powers data spaces and cloud-to-edge federation; enables data to flow between members and across sectors while keeping data sovereign (e.g. at national level).
- **Simpl-Labs:** An experimentation environment where data spaces can test interoperability and prototype with Simpl-Open before full deployment — directly relevant to “testing/usage … in experimentation facilities/pilots”.
- **Simpl-Live:** Real deployments of Simpl-Open for six sectoral data spaces, including the **Smart Communities Data Space** (cities and communities).

**Relevance to cities:** The **Smart Communities Data Space** is one of the Simpl-Live instances. “Federation of datasets through SIMPL for testing/usage of cities in experimentation facilities/pilots” is therefore **directly in scope** of SIMPL: city-related datasets can be federated and made interoperable via SIMPL, and Simpl-Labs is the place to experiment before going live.

**Source:** [SIMPL policy (digital-strategy.ec.europa.eu)](https://digital-strategy.ec.europa.eu/en/policies/simpl), [SIMPL Programme FAQ](https://simpl-programme.ec.europa.eu/landing-page/faq).

---

## 2. Is this relevant to our work package?

**Yes, it is relevant**, in two ways:

1. **Strategic / programme alignment**  
   Our work delivers **city-oriented experimentation facilities and pilots** (3D simulation, wayfinding, NavMesh, OSM, streaming, AI integration). These are exactly the kind of “experimentation facilities/pilots” where **federated city datasets** (e.g. from SIMPL / Smart Communities Data Space) could be consumed or combined — e.g. OSM, POI, 3D city models, or other city data from multiple sources in a governed way.

2. **Current state**  
   The codebase does **not** yet integrate with SIMPL (no references to SIMPL, data spaces, or dataset federation). Alignment can be described as **planned or under assessment**: our pilots and data (scene data, POI, OSM, etc.) are candidates to be exposed or consumed via SIMPL once the programme expects it, and our “experimentation facilities” are a natural fit for using Simpl-Labs or federated city datasets.

---

## 3. Suggested wording for the bi-weekly documentation

**Short (one sentence):**  
*“We are assessing alignment with the SIMPL middleware platform: our city experimentation facilities and pilots are a natural fit for consuming or contributing federated city datasets (e.g. via the Smart Communities Data Space and Simpl-Labs), and we will align delivery with SIMPL as the programme’s data-space strategy is clarified.”*

**Slightly longer (two bullets):**  
- **Relevance:** SIMPL is the EC’s open-source middleware for federating datasets across European data spaces. The **Smart Communities Data Space** (Simpl-Live) and **Simpl-Labs** (experimentation) are directly relevant to “federation of datasets for testing/usage of cities in experimentation facilities/pilots”.  
- **Our alignment:** Our work package delivers city-oriented experimentation facilities and pilots (3D simulation, wayfinding, streaming). We are assessing how our data (e.g. OSM, POI, scene data) and pilots can align with SIMPL — e.g. consuming or exposing federated city datasets via Simpl-Labs or the Smart Communities Data Space, in line with Anna’s and Monica’s expectations.

---

## 4. Suggested next steps (for Johan / team)

- **Clarify with Anna and Monica** what level of alignment they expect (e.g. active integration vs. documented assessment and roadmap).
- **Monitor** [SIMPL Programme](https://simpl-programme.ec.europa.eu/) and Smart Communities Data Space; MVP (end of 2024) and Simpl-Labs are the natural entry points for experimentation.
- **Document** in the work package (e.g. in milestone or D4.3) that SIMPL alignment is recognised and under assessment for federation of city datasets in our pilots.

---

## 5. How to actually align — and what it means for the team

### 5.1 Documentation vs development?

**Right now: mostly documentation and light process.** SIMPL is about *how* datasets are shared and governed (data spaces, access control, catalogues, interoperability), not about changing how we build the 3D viewer or wayfinding. So:

- **Documentation:** Yes. We should document our position (this note), which datasets we have (OSM, POI, scene data, etc.), and that we’re assessing SIMPL alignment in deliverables (milestone, D4.3).
- **Development impact:** Only if we decide to *integrate* (e.g. a connector to consume or expose data via SIMPL). Until then, developers do **not** need to think about SIMPL in every PR or daily task. No new “SIMPL check” in the pipeline.

**If we go further:** Actual integration (e.g. “SIMPL connector” or “publish our city data to Simpl-Labs”) becomes a normal feature: backlog item, owner, design, implementation. Then it affects the people working on that feature, not the whole team’s daily routine.

### 5.2 Levels of alignment (what to do in practice)

| Level | What it means | Who does what |
|-------|----------------|----------------|
| **A. Documentation only** | We state that we’re assessing SIMPL and that our pilots are a fit for federated city data. No code changes. | Tech lead / PM: keep this note, use suggested wording in reports; team: no daily change. |
| **B. Data-space friendly practices** | We keep our data and APIs in a shape that *could* plug into SIMPL later (clear ownership, formats, minimal metadata). | Tech lead: add a short “data readiness” checklist or doc (what we have, where it lives, format). Team: when adding new datasets or APIs, follow existing conventions; no SIMPL-specific routine. |
| **C. Real integration** | We build a connector to Simpl-Labs or the Smart Communities Data Space (consume federated datasets and/or expose ours). | Becomes a scoped feature: backlog, design, implementation. Only the people assigned to it need to work with SIMPL in their daily work. |

**Recommendation:** Start with **A** (already done with this note and the bi-weekly wording). Move to **B** if you want to be “ready” without committing to integration — e.g. one short data-inventory doc. Commit to **C** only when the programme or Anna/Monica asks for it, or when you explicitly prioritise it.

### 5.3 What the team should do in their daily routine

- **Default (no integration yet):** Nothing special. No SIMPL in code reviews, no new checklist. Awareness is enough: “We might consume or expose city data via SIMPL later; for now we document and assess.”
- **If you adopt level B (data-space friendly):** When introducing a *new* dataset or external data source, document it in the data inventory (name, source, format, owner). No extra daily routine beyond that.
- **If you adopt level C (integration):** Only the person(s) working on the SIMPL connector need to care in their daily work; the rest of the team is unchanged.

### 5.4 What you as tech lead should do

1. **Decide the level** (A only, or A+B, or A+B then C) with your PM / programme contact, using Anna’s and Monica’s expectations as input.
2. **Raise it with the team once** (see below): share what SIMPL is, that we’re aligning at level A (and B/C if applicable), and that daily work doesn’t change unless we scope integration.
3. **Keep it on the radar:** One backlog item or roadmap line (“SIMPL alignment — documentation / assessment” or “SIMPL connector — TBD”). Revisit when SIMPL MVP or Simpl-Labs is available or when the programme asks for an update.
4. **Own reporting:** Use the suggested wording in bi-weekly and milestone docs so the programme sees we’re aligned.

### 5.5 How to raise this with the team

- **Short sync or team meeting:**  
  - “We need to align with an EC middleware called SIMPL for federating city datasets in data spaces. It’s relevant to our pilots. For now it’s **documentation and awareness**: we’re not changing how we develop day to day. I’ll add it to the backlog/roadmap; if we ever integrate, we’ll scope it as a normal feature.”  
  - Share this note (or a one-page summary) and the link to SIMPL so people can read if interested.

- **Written follow-up:**  
  - Post the same message in your team channel (Slack/Teams/etc.) and attach or link this doc.  
  - Optionally create a **backlog ticket** (e.g. “SIMPL alignment — document position and data readiness”) so it’s visible and assignable; sub-tasks can be “Update milestone/D4.3 wording” and “Data inventory (if level B)”.  

- **Avoid:** Making it sound like “from now on every PR must consider SIMPL” — that would be unnecessary and confusing until we have a concrete integration goal.

**One-line for the team:** *“SIMPL is the EC’s data-space middleware for cities. We’re documenting that we align and assess; daily dev doesn’t change unless we later add a SIMPL integration feature.”*

---

## 6. Draft email reply to Johan

You can copy the text below and adapt as needed.

---

**Subject:** Re: SIMPL alignment — federation of datasets for cities in pilots

Hi Johan,

Thanks for looping me in. I’ve looked into SIMPL and how it relates to our work.

**Short answer:** Yes, it’s relevant. SIMPL is the EC’s open-source middleware for federating datasets across European data spaces. One of its live data spaces is the **Smart Communities Data Space** (cities/communities), and **Simpl-Labs** is the environment for experimenting before deployment — so “federation of datasets through SIMPL for testing/usage of cities in experimentation facilities/pilots” is directly in scope. Our work package delivers exactly that kind of city-oriented experimentation and pilots (3D simulation, wayfinding, streaming), so we’re a natural fit for consuming or contributing federated city data via SIMPL.

**Where we’ve been:** We haven’t been aligning with SIMPL explicitly until now. Our focus was on building the pilots and the data (OSM, POI, scene data, etc.) for our own experimentation — not with a mindset of contributing to or consuming from a federated data space. So we need to shift that.

**How we’re changing our way of working:** From now on we’re treating SIMPL alignment as part of our approach: we’re documenting our position, assessing how our datasets and pilots can contribute to or consume from SIMPL (e.g. via the Smart Communities Data Space and Simpl-Labs), and we’ll adapt as the programme’s data-space strategy and Anna’s/Monica’s expectations become clearer. In practice that means: (1) reporting and documentation first (so the bi-weekly and milestones reflect this), (2) then, where it makes sense, keeping our data and APIs in a shape that could plug into SIMPL later, and (3) scoping actual integration (e.g. Simpl-Labs) when the programme or the team prioritises it. Day-to-day development doesn’t need to change unless we take on a concrete SIMPL integration feature — but the *mindset* is now “we’re part of the federation story” rather than only building for our own pilots.

**For your bi-weekly documentation**, under the headline “Federation of datasets through SIMPL for testing/usage of cities in experimentation facilities/pilots”, you could use something like:

*“We are aligning our delivery with the SIMPL middleware platform: our city experimentation facilities and pilots are a natural fit for consuming or contributing federated city datasets (e.g. via the Smart Communities Data Space and Simpl-Labs). We have not previously aligned explicitly with SIMPL; from now on we document our position, assess how our data and pilots can contribute to or consume from federated data spaces, and will adapt our way of working (including data practices and optional integration) as the programme’s strategy is clarified.”*

I’ve put a short internal note together (with sources, suggested wording, and how we’re raising this with the team) that we can reuse for reporting. If you want to discuss or tweak the wording, happy to do that.

Best,  
[Your name]

---
