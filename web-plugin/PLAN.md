# Chrome-laajennus: “Explore in 3D” → Goteverse-spawn

Tavoite: käyttäjä on karttapalvelussa, painaa laajennuksessa **Explore in 3D**, ja striimoitu näkymä teleporttaa pelaajan vastaavaan paikkaan scenessä (WGS84 → scene, validointi, UX).

Nykyinen stack tukee ideaa: **web ↔ Kit -viestintä** ja **TeleportService.teleport_to_coordinates** ovat olemassa. Kolme kriittistä aukkoa: **koordinaattien luotettava keruu**, **WGS84 → scene -georeferenssi**, ja **turvallinen välitys** laajennuksesta striimiin.

---

## 1. Arkkitehtuuri (lyhyesti)

- **Web-viewer** (`web-viewer-sample-main`) striimaa Kitistä; viestit kulkevat messaging-kanavan kautta (`younite.messaging_core_extension` — esim. `sendCustomMessage`).
- **Teleportti tänään**: spawnpointit / POI (`teleportToSpawnpoint`, `poiTeleport`, `seatTeleport` jne.). Suoraa “lat/lon webistä” -polkua ei ole vielä sopimuksena.
- **OSM / kaupunki**: navmesh-graafi on esikäsitelty scenen koordinaateissa; maailman ja WGS84:n suhde on **projektikohtainen** — pitää määritellä eksplisiittisesti.

---

## 2. Koordinaattien lähde: useita karttapalveluja (ei vain Google Maps)

Periaate: **yksi yhteinen sisäinen muoto** laajennuksessa, esim. `{ lat, lon, source?, accuracy? }`. Karttapalvelukohtainen logiikka erillisiin **adaptereihin**.

| Kerros | Tehtävä |
|--------|---------|
| **Tunnista host** | `maps.google.com`, `www.google.com/maps`, `openstreetmap.org`, `www.openstreetmap.org`, Bing Maps, Mapy.cz, … |
| **Pura koordinaatit** | Ensisijaisesti **URL** (query/hash/polku) — ei DOM-kaivua jos välttämätöntä. |
| **Fallback** | Käyttäjä liittää `lat,lon` / kopioi URL:n / “käytä nykyistä välilehden URL:ia”. |

**Adapteri-malli (suositus):**

- Taulukko tai rekisteri: `(hostPattern | predicate) → parseFn(url) → { lat, lon } | null`.
- Jokainen palvelu: tunnetut URL-muodot dokumentoitu testeihin (yksikkötestit URL-stringeillä).
- **Google Maps**: usein `@lat,lng` tai `?q=lat,lng` tai `ll=` — URL-parsinta ensin; DOM vain jos pakko (käyttöehdot + hauraus).
- **OpenStreetMap**: `https://www.openstreetmap.org/#map=zoom/lat/lon` tai `?mlat=&mlon=`.
- **Muut**: lisätään adaptereina samalla kontraktilla; MVP:ssä 1–2 palvelua + geneerinen “ei tunnistettu → näytä ohje / liitä koordinaatit”.

**Manuaali-vaihtoehto (aina mukana):** pieni kenttä “Latitude / Longitude” + “Lähetä” — toimii kaikilla sivuilla ja on hyvä demoskenaario.

---

## 3. Laajennus → Goteverse-selain: välitystavat

Laajennus ei voi kirjoittaa WebRTC-datakanavaan ilman yhteistä päätettä.

| Vaihtoehto | Idea | Plussat | Miinukset |
|------------|------|---------|-----------|
| **A) Deep link / query** | Avaa tai fokusoi `https://oma-goteverse/?geo=lat,lon` (tai hash). Web-app lukee parametrin ja lähettää Kitille viestin. | Yksinkertainen, ei tarvitse content scriptia Goteverse-domainille jos query riittää. | Uudelleenlataus / routing; URL pitää olla whitelistissä. |
| **B) `chrome.tabs.sendMessage`** | Content script Goteverse-välilehdessä kutsuu samaa polkua kuin UI (`sendCustomMessage`). | Ei URL-muutosta; toimii kun stream jo auki. | Vaatii oikean originin, käyttäjällä tab auki, manifest-luvat. |
| **C) Paikallinen sidecar** | POST `localhost` → välitys. | Erottaa oikeudet. | Infrastruktuuria, ylläpito. |

**Ehdotus ensimmäiseen iterointiin:** **A + B yhdessä** — yritä ensin fokusoida olemassa olevaa Goteverse-tabia ja lähettää viesti (B); jos tabia ei ole, avaa deep link (A), jolloin web-app käynnistää saman viestin kun yhteys valmis.

### Testivaihe: kiinteä osoite `http://localhost:5173/`

Tuotantoympäristöä ei ole vielä — oletus **Vite-dev-palvelin** osoitteessa `http://localhost:5173/` (tai sama origin + polku; laajennuksessa vakio `VIEWER_ORIGIN = 'http://localhost:5173'`).

**Laajennuksen logiikka kun käyttäjä painaa Explore in 3D:**

1. **`chrome.tabs.query`** — etsi välilehti, jonka URL alkaa `http://localhost:5173` (tai vastaa `VIEWER_ORIGIN/*`). Huom: älä vaadi täsmälleen juurta ilman polkua, jos sovellus käyttää reititystä (`/cu`, jne.).
2. **Jos välilehti löytyy** — `chrome.tabs.update(tabId, { active: true })` (tuo välilehti eteen). Koordinaatit perille **B)**-polulla: `chrome.tabs.sendMessage(tabId, { type: 'EXPLORE_GEO', lat, lon })`. Content script Goteverse-sivulla välittää viestin appille (esim. `window.postMessage` + app kuuntelee, tai injektoitu bridge joka kutsuu samaa lähetystä kuin UI).  
   - **Älä** vaihda olemassa olevan tabin URL:ia `?geo=…` -muotoon jos striimi voi olla jo auki: täysi **sivun uudelleenlataus** katkaisee WebRTC-pixel streamingin. Query-parametri sopii **vain** uuteen välilehteen / kylmään käynnistykseen.
3. **Jos välilehteä ei löydy** — `chrome.tabs.create({ url: 'http://localhost:5173/?geo=' + encodeURIComponent(`${lat},${lon}`) })` (tai sovittu muoto `?lat=&lon=`). Web-app lukee parametrin mountissa / stream-valmistuttua ja lähettää `geoTeleport` Kitille kerran.

**Manifest (MV3):** `host_permissions` / `content_scripts.matches` sisältää `http://localhost:5173/*` (tai laajempi localhost vain devissä). Tuotannossa vaihdetaan myöhemmin oikea origin samaan logiikkaan.

**Tiivistys:** ensin **onko viewer jo auki** → fokusoi + viesti; muuten **uusi välilehti** deep linkillä ja koordinaatit URLissa.

---

## 4. Georeferenssi (kriittinen)

WGS84 (lat/lon) → USD-scene (tyypillisesti cm, oma origo, Y ylös).

Tarvitaan jokin **yksi dokumentoitu muunnos**:

- **Ankkuripisteet** (tunnettu lat/lon ↔ tunnettu scene `X,Y,Z`), tai  
- **Affiini / projektio** (2D XZ tasossa + erillinen Y-strategia).

Kysymykset suunnitelmaan:

- **Kattavuus**: vain stadionin ympäristö, koko “city tile” -alue, vai koko maailma paperilla?  
- **Y**: raycast maahan, kiinteä offset, vai DTM / terrain-sampling?  
- **Navmesh**: jos piste navmeshin ulkopuolella → lähin validi piste tai selkeä virhe (kuten muissa teleporteissa).

Tämä kannattaa toteuttaa **Kit-puolella yhdessä paikassa** (esim. palvelu joka ottaa lat/lon ja palauttaa scene-koordinaatit), jotta web/laajennus pysyy tyhmänä.

---

## 5. Kit- ja web-puolen tapahtumasopimus

- Uusi inbound-viesti tyyliin `geoTeleport` / `exploreAtCoordinates`: `{ latitude, longitude }` (optiot: `source`, `requestId`).  
- Handler: muunnos → `TeleportService.teleport_to_coordinates` (+ mahd. snap, navmesh-check).  
- Tulos webiin: sama malli kuin `poiTeleport` / `seatTeleport` — `*Result` + `viewTransitionReady` jos halutaan yhtenäinen fade.

Turvallisuus: origin / istunto, rate limit, mahdollinen allowlist vain tietyille deployment-URL:eille (tuotepäätös).

---

## 6. Toteutusjärjestys (backlog)

1. **Georeferenssi** — määritelmä + testipisteet + hyväksymiskriteeri (virhe metreissä). Ilman tätä ei kannata hiota laajennusta.  
2. **Kit + web** — yksi viesti lat/lon → teleport; virheenkäsittely ja navmesh-käyttäytyminen.  
3. **Web** — deep link -parseri (`?geo=`) + valinnainen content script -polku; yhteinen apufunktio “lähetä geoTeleport”.  
4. **Chrome-laajennus MVP** — Manifest V3, popup: “lue nykyisen tabin URL” + adapterit (Google + OSM) + manuaalinen lat/lon; Explore-nappi → `tabs.query` localhost:5173 → sendMessage tai `tabs.create` + `?geo=`.  
5. **Laajennus v2** — lisää adaptereita; paranna tunnistusta; privacy policy / Chrome Web Store -putki.  
6. **Oikeudellinen** — Maps DOM -scraping vältetään; URL/käyttäjän syöte ensisijainen.

---

## 7. Toteutussuunnitelma (vaiheet)

Alla järjestys, jossa riippuvuudet pitävät: ensin **päästä päähän -putki** yhdellä testipisteellä, sitten georeferenssin tarkennus ja laajennus.

### Vaihe 0 — Georeferenssi ja stub *(aloitettu / peruspolku valmis)*

**Muunnosmalli (tuotantopolku):** projektissa on jo **`GeoCoordinateService`** (`geo_coordinate_service.py`): WGS84 ↔ USD käyttäen **CesiumGeoreference**-origoa ja **`Cesium_World_Terrain`** `xformOp:translate` -offsetia (ENU, cm-scene). Katso `.cursor/rules/topics/cesium-geolocation.mdc` — ankkuriesimerkki (Skandinavium): **57.69924°N, 11.98767°E**.

**Teleporttiin yhteinen API:** **`latlon_to_scene_xyz_for_teleport(lat, lon, height_m=0)`** (`geo_teleport_transform.py`):

- Jos `get_geo_coordinate_service()` on **ready** → sama tulos kuin `latlon_to_usd`.
- Jos georef **ei** ole valmis (ei Cesium-primiä / scene ei vielä ladattu) → **stub**: kiinteä **`PlayerSpawnPoint_01`**-translate (`player_spawnpoints_layer.usda`), jotta viestiputkea voi testata ilman hiljaista epäonnistumista.

**Testipisteet (manuaalinen hyväksyntä myöhemmin; ENU-malli pätee hyvin noin 10 km origosta):**

| Kuvaus | lat | lon | Odotus |
|--------|-----|-----|--------|
| Georeference-ankkuri (Composer) | 57.69924 | 11.98767 | Lähellä stadionin / Skandinavium-kohdetta scenessä (visuaalinen linjaus) |
| Toinen piste samaan kaupunkiin | *(täytä kun mitattu)* | *(täytä kun mitattu)* | Virhe alle X metriä (sovittava) |

**Hyväksyntä vaiheelle 0:** stub-polku palauttaa dokumentoidun `(x,y,z)`; kun scene latautuu Cesium-georefilla, sama funktio palauttaa ei-stub -arvon; logissa näkyy selvästi stub-haara (`[geo_teleport_transform] georef not ready …`).

---

### Vaihe 1 — Kit: `geoTeleport` + tulosviesti

| Tehtävä | Tiedostot / paikat (ohjeellinen) |
|--------|----------------------------------|
| Uusi inbound `_observe("geoTeleport", …)` samaan tyyliin kuin `poiTeleport` / `seatTeleport`. | `younite.navmesh_route_extension` / `extension.py` (tai erillinen pieni palvelu + subscription; älä hajauta logiikkaa). |
| Muunnos `latitude`/`longitude` → scene; kutsu `TeleportService.teleport_to_coordinates`. | `teleport_service.py` (käyttö olemassa); georef-moduuli uusi tai `stage_core` -apu. |
| Outbound `geoTeleportResult` (+ tarvittaessa `viewTransitionReady` yhdenmukaisesti muiden teleporttien kanssa). | `register_outbound_events` navmesh-route- tai messaging-puolella; `events_contracts` / vastaava jos projektissa lista. |
| Virheet: navmesh ulkopuolella / muunnos epäonnistuu → payload webiin. | Sama malli kuin `poiTeleportResult` `success: false`. |

**Hyväksyntä:** dev-konsolista / väliaikaisesta Python-kutsusta tai testiviestistä: `geoTeleport` siirtää pelaajan stub-kohteeseen; web saa tulosviestin.

---

### Vaihe 2 — Web: yksi lähetyspolku + deep link

| Tehtävä | Tiedostot / paikat (ohjeellinen) |
|--------|----------------------------------|
| Apufunktio `requestGeoTeleport({ lat, lon })` joka kutsuu `sendMessage('geoTeleport', …)` vain kun striimi/datakanava on valmis. | `web-viewer-sample-main/src/features/streaming/messaging.ts` (tai rinnalle `geoTeleport.ts`) + kutsu hookista. |
| Lukee `?geo=lat,lon` (tai `lat` + `lon`) mountissa; tallentaa; **yksi lähetys** kun yhteys OK; `history.replaceState` poistaa parametrin. | `AppStream.tsx` / stream root tai olemassa oleva “stream ready” -hook. |
| (Valinnainen dev) Nappi tai konsolikomento samaan apuun. | `DevViewLayer` tai vastaava. |

**Hyväksyntä:** selaimessa `http://localhost:5173/?geo=57.7,11.97` (tarkista formaatti) → yksi teleportti stub-sijaintiin ilman ikuisuussilmukkaa.

---

### Vaihe 3 — Silta: content script ↔ React

| Tehtävä | Tulos |
|--------|--------|
| `web-plugin/` (tai `web-viewer-sample-main/public/`): content script joka kuuntelee `chrome.runtime.onMessage`, tekee `window.postMessage` (sopimus: `source`, `type`, `lat`, `lon`). | Viesti päätyy sivun kontekstiin. |
| Web-app: `window.addEventListener('message', …)` — validoi `event.source === window` ja tunnettu `source`-merkkijono; kutsuu `requestGeoTeleport`. | Sama polku kuin query; ei duplikaattilogiikkaa Kitille. |

**Hyväksyntä:** manuaalisesti `chrome.tabs.sendMessage` devtoolsista / laajennuksen popupista → pelaaja teleporttaa ilman sivun reloadia.

---

### Vaihe 4 — Chrome-laajennus MVP

| Tehtävä | Tulos |
|--------|--------|
| MV3 `manifest.json`: `permissions` (`tabs`, `scripting` tarvittaessa), `host_permissions` `http://localhost:5173/*`, content script match. | Laajennus latautuu devissä. |
| Popup: nykyisen tabin URL → adapteri (Google + OSM) + manuaalinen lat/lon. | `parseUrlToGeo(url)` moduuli + testit URL-merkkijonoille. |
| Explore: `tabs.query` → löytyi → `tabs.update` + `sendMessage`; ei löydy → `tabs.create` + `?geo=`. | Sama logiikka kuin §3 testivaihe. |
| README: miten ladataan unpacked + miten käynnistetään Vite + Kit. | Tiimi voi toistaa. |

**Hyväksyntä:** Maps/OSM-välilehti → Explore → viewer teleporttaa (stub-georef); toinen ajo avoimella tabilla ei katkaise striimiä.

---

### Vaihe 5 — Georeferenssi oikeaksi + navmesh-käyttäytyminen

| Tehtävä | Tulos |
|--------|--------|
| Korvaa stub oikeilla ankkureilla / projektiolla; validoi testipisteet maastossa. | Virhemarginaali dokumentoitu. |
| Navmesh: snap tai lähin piste tai selkeä virheviesti UI:hin (tulosviestin kenttä). | Käyttäjä ei jää “tyhjään” tilaan. |
| (Tuote) Rate limit / allowlist — myöhemmin tuotantoorigin kanssa. | Dokumentoitu rajaus. |

---

### Vaihe 6 — Laajennus v2 ja julkaisu

- Lisää kartta-adaptereita; virheilmoitukset popupissa.
- Privacy policy, Chrome Web Store -paketti, tuotanto-`VIEWER_ORIGIN` konffista.

---

### Riippuvuuskaavio (lyhyesti)

```
Georef (stub) ──► Kit geoTeleport ──► Web sendMessage + ?geo= ──► Content script ──► Chrome MVP
       │                    │
       └────────────────────┴──► Tarkenna georef + navmesh (vaihe 5)
```

### Testilistä (lyhyt)

- [ ] Kit: `geoTeleport` onnistuu / epäonnistuu tulosviestillä.
- [ ] Web: cold start URL-query, ei tuplalähetystä.
- [ ] Web: postMessage-silta, ei reload.
- [ ] Laajennus: tab olemassa / tab puuttuu.
- [ ] Stub korvattu: tunnettu piste kartalla ≈ oikea paikka scenessä.

---

## 8. Tiivistelmä

| Osa | Tila / tarve |
|-----|----------------|
| Viestikanava web ↔ Kit | Valmis |
| Teleport numerokoordinaatteihin | Valmis (`teleport_to_coordinates`) |
| WGS84 → scene | **Suunniteltava ja toteutettava** |
| Inbound “geo teleport” -viesti | **Lisättävä** |
| Chrome-laajennus | Uusi; **monipalvelutuki = URL-adapterit + manuaalisyöte** |
| Välitys striimiin | **Deep link + valinnainen tab-viesti** |

Ensimmäinen konkreettinen askel: lukita georeferenssi ja yksi testikohde (esim. stadionin kulma), sitten toteuttaa `geoTeleport`-polku päästä päähän ennen kuin rakennetaan useita kartta-adaptereita.
