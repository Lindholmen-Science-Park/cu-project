1. Overview 

This document summarises the technical progress related to the development activities within the work package. The objective is to highlight the main architectural solutions, AI-related developments, the relation to the LDT-toolbox, and the pilot implementation of wayfinding capabilities. 

The document accompanies Deliverable D4.3 and provides an overview of the implemented concepts and the technical direction of the platform development. 

The key areas addressed in this milestone include: 

Technical solution structure (small, medium, large deployment models) 

How to utilise the USD-framework 

How to get access to 3D-environments (with or without pixel streaming) 

How to gamify the solution and make it interactive 

AI integrations and future opportunities 

Utilisation and contribution to the LDT-toolbox 

Wayfinding pilot implementation based on NavMesh (and its connection to data structures and GATE-related work) 

Opportunity space (incident handling, spatial analytics, and CCTV-camera prompting) 

The purpose is not to provide full technical documentation, but rather to present the current implementation approach, its maturity, and the possibilities it enables for further development. 

 

2. Technical Solution — Small, Medium, Large 

The technical architecture can be conceptualised through three different deployment scales. These represent increasing levels of capability and infrastructure complexity depending on the needs of the deployment scenario. 

2.1 Small-scale deployment 

The small-scale configuration represents the most lightweight approach. 

Characteristics include: 

No pixel streaming or real-time rendering delivery 

Focus on data layers, spatial information and user interface interaction 

Optional use of Citiverse and Cesium for geospatial context and coordinate handling 

This configuration is suitable for environments where the emphasis is on data visualisation, geospatial context and service interaction, rather than high-fidelity real-time 3D rendering. 

Typical use cases may include: 

lightweight web applications 

data-oriented city dashboards 

scenarios where GPU infrastructure is not available 

 

2.2 Medium-scale deployment 

The medium-scale configuration introduces greater flexibility while still avoiding the infrastructure requirements of full streaming. 

Characteristics include: 

Multiple configuration options for different deployment contexts 

Shared architecture and logic with the full platform implementation 

No WebRTC pixel streaming 

This approach allows the system to support multiple environments or studies with slightly different requirements while maintaining a consistent architecture and data model. 

The same underlying logic — such as navigation, messaging and spatial interaction — can be reused even without a streamed 3D runtime. 

 

2.3 Large-scale deployment 

The large-scale configuration corresponds to the full digital twin runtime environment currently implemented in the project. 

Key characteristics include: 

Full Omniverse Kit-based application 

WebRTC-based pixel streaming 

Bidirectional messaging between the web interface and the runtime environment 

Modular extension architecture 

The implementation includes functionality such as: 

navigation and wayfinding 

scene interaction and object selection 

AI-assisted interactions 

environmental simulation 

This configuration represents the reference implementation of the platform architecture and demonstrates the full capability of the digital twin environment. Incident handling, spatial analytics and related opportunity areas are described in Section 6 (Opportunity space). 

 

2.4 Access to 3D environments (with or without pixel streaming) 

The platform supports two main approaches to providing users with access to the 3D environment. 

Without pixel streaming (small- and medium-scale): users interact with data layers, maps, and user interfaces that are driven by the same spatial and semantic data as the full digital twin. Geospatial context can be provided via Citiverse or Cesium. This approach does not require a real-time rendered 3D view and avoids the need for WebRTC and GPU-backed streaming infrastructure. 

With pixel streaming (large-scale): the full Omniverse Kit runtime is rendered on the server and the view is delivered to the client via WebRTC. Users experience the 3D environment in real time, with bidirectional messaging for interaction. The choice between the two depends on deployment constraints, use case requirements, and available infrastructure. 

 

2.5 Utilising the USD-framework 

The implementation is built on the Universal Scene Description (USD) framework (OpenUSD). The 3D environment is represented as a USD stage composed of layers and sublayers, allowing modular scene assembly, versioning, and reuse. 

Key aspects of USD utilisation include: 

scene graph structure for environments, objects, and spatial references 

sublayers for separating concerns (e.g. navigation, incidents, OSM roads, exit points) 

payload and visibility orchestration for performance and level-of-detail 

coordinate systems and geolocation (e.g. WGS84 and local scene coordinates) 

The use of USD supports interoperability with other OpenUSD-based tools and pipelines and provides a stable foundation for data structure alignment with external systems (see Section 5). 

 

2.6 Gamification and interactivity 

The platform is designed to support interactive and game-like use cases. Interactivity is achieved through: 

click-based selection and picking (e.g. map clicks, object selection) 

proximity and trigger-based interactions (e.g. NPC dialogue, information overlays) 

navigation actions (e.g. “move to” a seat, exit, or point of interest) 

configurable actions and overlays driven by data (e.g. interactions configuration) 

Incident placement and maintenance bots add scenario-based elements that can support training, evacuation drills, or crowd studies. The combination of real-time control, AI-assisted queries, and spatial feedback allows the solution to be used in a gamified or simulation-oriented manner. 

 

3. AI Integrations and Opportunities 

AI functionality has been integrated into the platform to support natural interaction with the digital twin environment. 

The current implementation includes an AI chat interface that enables users to interact with the environment through natural language queries. These interactions allow the system to interpret user intent, identify relevant locations or objects, and trigger appropriate responses such as navigation or contextual information. 

The AI component currently operates through a locally hosted model environment, allowing the system to: 

interpret natural language requests 

identify relevant points of interest 

trigger navigation or information responses 

The architecture is designed to remain model-agnostic, allowing different AI providers or models to be integrated in the future. 

Future opportunities include: 

AI-assisted navigation and route suggestions 

contextual explanations of urban infrastructure 

AI-driven analytics based on spatial behaviour 

integration with external data sources or city services 

The event-driven system architecture allows AI functionality to be expanded without modifying the core runtime components. 

 

4. Utilising and Contributing to the LDT-Toolbox 

The development work carried out within this work package aligns with the broader objectives of the Local Digital Twin (LDT) Toolbox initiative. 

The project both utilises existing concepts and contributes new technical patterns that may be relevant for other digital twin implementations. 

The LDT-toolbox is utilised through: 

shared architectural principles 

interoperability considerations 

alignment with open digital twin technologies such as OpenUSD 

At the same time, the project contributes back to the ecosystem through: 

practical implementations of navigation and spatial interaction 

integration patterns between web interfaces and digital twin runtimes 

experimentation with AI-assisted interaction 

The intention is that these experiences can provide practical reference implementations for other cities and projects exploring similar technologies. 

 

5. Wayfinding — NavMesh Pilot Study 

A pilot implementation of wayfinding functionality has been developed as part of the platform. 

The objective of this work is to demonstrate how navigation and route planning can be integrated into a digital twin environment. The wayfinding implementation is designed with data structures and interfaces that could align with complementary wayfinding work carried out by the project partner GATE. Keeping this alignment in mind supports consistent representation of routes and locations across the ecosystem and leaves room for future collaboration, without predefining GATE’s specific deliverables or current progress. 

The implementation consists of two complementary components: 

Local navigation (NavMesh) 

Local navigation within buildings or detailed environments is implemented using a NavMesh-based approach. 

This allows the system to: 

calculate shortest paths between locations 

generate routes to exits or seating areas 

measure route distances 

support multiple simultaneous routes 

The NavMesh approach allows navigation to respect environmental constraints such as obstacles or accessibility requirements. 

This functionality is particularly relevant for use cases such as: 

accessibility studies 

evacuation planning 

visitor guidance inside venues 

 

City-scale navigation (OSM) 

For navigation at the city scale, the system utilises OpenStreetMap-based road network data. 

The road graph is processed into a navigation structure that allows the system to calculate routes across the urban environment. 

This enables the platform to support: 

navigation between points of interest 

city-scale route visualisation 

integration between outdoor navigation and indoor environments 

 

6. Opportunity space 

This section highlights areas that present clear opportunities for further development and integration. 

Incident handling and spatial analytics 

The platform includes support for incident placement and spatial analytics (e.g. NavMesh-blocking obstacles, area-based costs, camera and sound areas). These capabilities can be extended to support scenario-based training, evacuation studies, and analytics on crowd movement and exposure. The same data structures and event flows can be used to feed analytics pipelines or to drive visualisation of spatial metrics. 

CCTV-cameras and prompting 

There is an opportunity to connect the digital twin to camera-based analytics and prompting. Virtual CCTV viewpoints and camera frustums are already represented in the scene (e.g. for NavMesh cost areas and visibility studies). These can be extended to explore how prompting or steering of camera systems — in the digital twin or in relation to real-world camera feeds — could support operators or AI-driven analysis. Ideas include using the digital twin as a testbed for camera placement, prompt design for camera analytics, or linking simulated camera views to real-world CCTV workflows. 

Bringing these topics under a single “opportunity space” headline allows the work package to present incident handling, spatial analytics, and CCTV-related developments as a coherent set of directions for future work and collaboration. 


 