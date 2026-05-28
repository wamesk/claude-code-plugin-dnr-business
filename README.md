# dnr-business

> Claude Code plugin + Claude.ai Skill — vygeneruje **Detailný návrh riešenia (DNR)** vo WAME vizuálnej identite ako `.docx`. Vstupom je priečinok s podkladmi, jednotlivé súbory alebo voľný popis. V git repozitári automaticky berie do úvahy existujúci kód (moduly, deps, README).

## Čo to robí

Po príkaze `/dnr-business <vstup>` sa stane:

1. **Zber kontextu** — skill prečíta podklady (`.docx` / `.pdf` / `.md` / `.txt`), repo deep-scanom zistí ekosystém (Laravel / Vue / Next…), moduly (`wamesk/*`, `Modules/*`, `app/Models`), prečíta package súbory a `README`.
2. **Doplnenie chýbajúcich informácií** — cez `AskUserQuestion` sa pýta len na to čo sa nedá deteguť (klient, typ projektu, biznis cieľ, out of scope, termín).
3. **Generovanie štruktúrovaného plánu** — Claude vyplní JSON podľa pevnej schémy (12 povinných + 5 voliteľných sekcií). Sekcie *Fázy* a *Riziká* sú schémou vynútené (min. 5 rizík).
4. **Validácia** — Python validátor v stdlibu prekontroluje JSON; chyby sa fixujú v cykle (max 3 pokusy).
5. **Render do `.docx`** — stdlib OOXML generátor vyrobí Word dokument s WAME brandingom: zelená `#20E87A`, navy `#091145`, font **Inter**, hlavička s názvom projektu, päta s verziou.

Výstup je hotový dokument pripravený na revíziu — všetky neznáme údaje sú v ňom označené ako `[DOPLNIŤ]` a vypísané do záverečného súhrnu ako otvorené body.

## Inštalácia

### Claude Code (cez WAME marketplace)

```
/plugin marketplace add wamesk/claude-code
/plugin install dnr-business@wame
```

### Claude.ai (online)

1. Stiahni priečinok `skills/dnr-business/` z tohto repa.
2. Nahraj ho v Claude.ai Settings → Capabilities → Skills.

## Použitie

```
/dnr-business ~/projects/foo/kickoff/           # priečinok podkladov
/dnr-business kickoff.docx cenova_kalkulacia.pdf  # viacero súborov
/dnr-business                                    # len voľný popis + aktuálny repo
/dnr-business inputs/ --client="Acme s.r.o." --project=eshop --lang=sk
/dnr-business inputs/ --output=docs/DNR_v1.0.docx
/dnr-business --init                             # per-project config
/dnr-business --from-json=docs/dnr_plan.json     # preskoč LLM, rerender
/dnr-business inputs/ --dry-run                  # len JSON plán
```

### Claude.ai chat

Nahraj podklady (DOCX/PDF/MD) a napíš:

> Sprav mi DNR pre tohto klienta.

Skill sa zapne podľa popisu, opýta sa na chýbajúce informácie a vygeneruje `.docx` na stiahnutie.

## Štruktúra dokumentu

Vždy 12 povinných sekcií, voliteľne 5 ďalších:

| #  | Sekcia |
|----|--------|
| 00 | Titulná strana (klient, dátum, verzia) |
| 01 | Úvod a účel dokumentu |
| 02 | Východiskový stav |
| 03 | Ciele projektu (biznis · technické · out of scope) |
| 04 | Popis riešenia a rozsah (moduly + sitemap + user flows) |
| 05 | Používateľské roly a prístupy |
| 06 | Technické riešenie (platforma, integrácie, bezpečnosť) |
| 07 | GDPR a právne požiadavky |
| 08 | Podklady od klienta |
| 09 | **Fázy projektu a harmonogram** (povinné) |
| 10 | **Riziká a ich riadenie** (povinné, min. 5) |
| 11 | Podmienky a záväzky |
| 12 | Schválenie dokumentu |
| A  | Wireframy a UX flows (voliteľné) |
| B  | Dátový model (voliteľné) |
| C  | SEO stratégia (voliteľné) |
| D  | Migrácia dát (voliteľné) |
| E  | Školenie a odovzdanie (voliteľné) |

## Vstupy

| Formát | Status | Závislosť |
|---|---|---|
| `.docx` | ✅ | stdlib `zipfile` + `xml.etree` |
| `.md` / `.txt` | ✅ | stdlib |
| `.pdf` | ⚠️ vyžaduje `pdftotext` | `brew install poppler` |
| Priečinok | ✅ rekurzívne (max 20 súborov × 200 KB) | stdlib |
| Voľný popis v prompte | ✅ | — |
| Repo kontext (auto) | ✅ ak je v git repe | stdlib |

## Výstup

`.docx` v jazyku klienta, s plnou diakritikou, vo WAME vizuálnej identite:

- **Farby:** primary `#20E87A` (akcent), `#091145` (navy, nadpisy), `#F4F5F8` (light), `#5C6679` (muted text).
- **Font:** `Inter` s fallbackom `Calibri`.
- **Hlavička:** `WAME — Detailný návrh riešenia · <názov> · <klient>` s green underline.
- **Päta:** `WAME s.r.o. · wame.sk · info@wame.sk · <verzia> · <dátum>`.

## Konfigurácia

Per-project config v `~/.claude/plugins/data/dnr-business-wamesk/<project-hash>/config.json`:

```json
{
  "output_dir": "docs",
  "language": "auto",
  "default_version": "v1.0",
  "client": {
    "company": "",
    "contact_name": "",
    "contact_email": "",
    "contact_phone": ""
  }
}
```

Vytvor cez `/dnr-business --init`. CLI flagy (`--lang`, `--client`, …) preplnia config.

## Architektúra

```
USER → /dnr-business <vstupy>
         │
         ▼
       SKILL.md (Claude orchestruje)
         │
         ├── python3 dnr_to_docx.py --read-inputs --paths ...
         │     → plain text dump zo súborov
         │
         ├── python3 dnr_to_docx.py --scan-repo --root .
         │     → ekosystém, moduly, package súbory (ak je repo)
         │
         ├── AskUserQuestion → chýbajúce kľúčové údaje (klient, typ, ciel)
         │
         ├── Claude (LLM): extract → JSON podľa dnr_json_schema.json
         │
         ├── python3 dnr_to_docx.py --validate --json plan.json
         │     → ok / errors[]
         │
         └── python3 dnr_to_docx.py --build --json plan.json --output DNR.docx
               → finálny .docx (stdlib OOXML, WAME branding)
```

## Princípy

- **Nikdy si nevymýšľa údaje** — chýbajúce hodnoty sa označia ako `[DOPLNIŤ]` a vypíšu sa v záverečnom súhrne.
- **Biznis tón** — každá technická voľba má zdôvodnenie biznis prínosu.
- **Žiadne externé deps** — stdlib-only, funguje aj v Claude.ai sandboxe.
- **Sekcie 09 a 10 sú vynútené schémou** — schéma neprijme plán bez fáz a min. 5 rizík.

## Roadmap

- [x] Phase 1 — DOCX generátor (stdlib OOXML), validátor schémy, repo deep-scan.
- [ ] Phase 2 — Inkrementálne `--update-from=DNR_v1.0.docx` na revízie.
- [ ] Phase 2 — Voliteľné vloženie WAME loga ako PNG (assets bundlovať).
- [ ] Phase 2 — Generovanie sprievodného Markdown sumáru pre PR / Teamwork.

## Súvisiace pluginy

- [`teamwork-tasks-from-dnr`](https://github.com/wamesk/claude-code-plugin-teamwork-tasks-from-dnr) — z hotového DNR vygeneruje Teamwork import-ready XLSX + plán.
- [`teamwork-task`](https://github.com/wamesk/claude-code-plugin-teamwork-task) — implementuje konkrétne tasky z Teamwork URL.
- [`teamwork-task-test`](https://github.com/wamesk/claude-code-plugin-teamwork-task-test) — overí akceptačné kritériá taskov.

## Licencia

MIT — pozri `LICENSE`.
