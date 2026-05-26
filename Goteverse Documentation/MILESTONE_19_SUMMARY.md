# Milestone 19 — Summary (one page)

**Delivered with:** D4.3, end of March. **Reference:** Goteverse-Omniverse Research.pdf.

| Topic | Summary | References |
|-------|---------|------------|
| **Technical solution — Small** | No pixel streaming. Citiverse (and optionally Cesium) for geo/terrain/POI. Lightweight, data/UI focus. | Research PDF; project architecture |
| **Technical solution — Medium** | A couple of deployment configurations; no pixel streaming. Same event/nav logic, no WebRTC viewer. | Research PDF; `.kit` and extensions |
| **Technical solution — Large** | Full stack: Omniverse Kit + WebRTC livestream, messaging, all extensions (NavMesh, OSM, AI, interactions, etc.). | Research PDF; `younite.usd_viewer_streaming.kit`; project-base.mdc |
| **AI integrations** | Ollama + custom Younite model; POI/navigation intents; route and POI data available for AI/analytics. Training and runtime tooling in repo. | `younite.ai_chat_extension`; `tools/ai_training/README.md` |
| **LDT-toolbox** | We utilise and contribute to the LDT-toolbox in a way that provides value to the programme and other work packages. | To be detailed with LDT deliverables |
| **Wayfinding — NavMesh pilot** | Local/indoor: baked NavMesh, shortest path, area costs, route measurement, routes-to-exits. City-scale: OSM graph, Dijkstra, POI routes. | `younite.navmesh_route_extension`, `younite.osm_navigation_extension`; route-measurement.mdc; osm-navigation.mdc |

**Packaging:** Use MILESTONE_19.md for the full narrative; this summary for annex or quick reference.
