# Figman yhdistäminen projektiin

Projekti on jo kytketty Figmaan **manuaalisesti**: design-tokenit ja node-linkit ovat paikallaan. Tässä lyhyt ohje.

---

## 1. Design-tokenit (värit, varjot, säteet)

**Paikka:** `src/app/index.css` – `:root`-lohko

Figma-värit ja -tyylit synkataan CSS-muuttujina. Kun designeri muuttaa Figmassa:

1. Avaa Figma → **Dev mode** (oikealla).
2. Valitse elementti → kopioi **Color**, **Effects** (shadow), **Corner radius**.
3. Päivitä `index.css`:

```css
:root {
    --Off-white: #F6F6F6;
    --figma-purple: #351A84;
    --figma-text: #1a1a1a;
    --figma-shadow-sm: 0 1px 6px 0 rgba(0, 0, 0, 0.30);
    --figma-radius-button: 80px;
    --figma-radius-panel: 12px;
    /* lisää tarvittaessa */
}
```

Komponenteissa käytä: `color: var(--figma-text);`, `border-radius: var(--figma-radius-panel);` jne.

---

## 2. Node-linkit (suora linkki Figmaan)

**Paikka:** `src/config/figma.ts`

- **FIGMA_FILE_KEY** – Figma-tiedoston ID (URL: `figma.com/design/vnlxvc8YpXncYM1HfEulQk/...`).
- **FIGMA_NODES** – node-IDt, jotta voit avata oikean framen Dev modessa.

Uusi komponentti:

1. Avaa Figmassa frame → oikealla **Copy link** tai node-id (esim. `1505-6613`).
2. Lisää `figma.ts`-tiedostoon:

```ts
export const FIGMA_NODES = {
    menuButton: '5721-7121',
    peoplePanel: '5721-7131',
    frame: '1505-6675',
    peopleCard: '1505-6613',  // uusi
} as const;

export const figmaUrls = {
    // ...
    peopleCard: getFigmaNodeUrl(FIGMA_NODES.peopleCard),
};
```

Koodissa: `import { figmaUrls } from '../config/figma';` ja esim. linkki `figmaUrls.peopleCard`.

---

## 3. Tyylien kopiointi Dev modesta

Kun toteutat uutta UI:ta:

1. Avaa Figma → **Dev mode** (välilehti oikealla).
2. Valitse frame tai komponentti.
3. **Inspect**-paneelista kopioi:
   - **Layout** (padding, gap, flex, width, height)
   - **Typography** (font, size, weight)
   - **Color** (fill, border)
   - **Effects** (shadow, blur)
4. Liitä arvot vastaavan komponentin CSS-tiedostoon (esim. `CUControls.css`).

---

## 4. Vapaaehtoinen: Figma REST API

Jos haluat hakea design-tokeneja automaattisesti:

1. **Figma-tili** → Settings → Personal access tokens → luo token.
2. Tallenna token esim. `.env`: `VITE_FIGMA_ACCESS_TOKEN=xxx` (älä commitoi).
3. Voit tehdä skriptin (Node), joka kutsuu [Figma REST API](https://www.figma.com/developers/api#get-file-styles-endpoint) ja kirjoittaa värit/tyylit esim. `index.css` tai JSON-tiedostoon.

Tämä vaatii oman skriptin; yleensä **manuaalinen** tokenien ja Dev mode -kopioiden käyttö riittää.

---

## Yhteenveto

| Toimi            | Missä                          |
|------------------|--------------------------------|
| Värit, varjot    | `src/app/index.css` (:root)   |
| Node-linkit      | `src/config/figma.ts`         |
| Komponenttityylit| Figma Dev mode → kopioi → CSS |

Projekti käyttää jo näitä: CU-napit ja People-paneeli viittaavat Figma-tokeniin (`--Off-white`, `--figma-radius-panel` jne.) ja node-idt on listattu `figma.ts`:ssä.
