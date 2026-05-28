---
name: dnr-business
description: "Use when the user asks to 'vytvor DNR', 'priprav DNR', 'sprav DNR', 'sprav klientske DNR', 'priprav detailný návrh riešenia', 'urob DNR pre klienta', 'create a DNR', 'prepare a DNR', or invokes '/dnr-business'. Accepts a folder of supporting materials, individual file(s) (.docx/.pdf/.md/.txt), or a free-form description as input. If the skill runs inside a project repository, it additionally deep-scans the repo (modules, Laravel/wamesk layout, package files, README) so the resulting DNR reflects the existing codebase context. Produces a WAME-branded .docx Detailný návrh riešenia in the client's language (sk/cs/en) with all mandatory sections — Východiskový stav, Ciele, Popis riešenia, Technické riešenie, GDPR, Podklady, Fázy, Riziká, Podmienky — plus optional Wireframy, Dátový model, SEO, Migrácia, Školenie. Never invents client data — uses [DOPLNIŤ] for unknowns and reports them as open questions at the end."
argument-hint: "[path/to/folder-or-file ...] [--output=docs/DNR.docx] [--lang=auto|sk|cs|en] [--client=\"Company\"] [--project=web|eshop|system|app] [--init] [--from-json=plan.json] [--dry-run]"
allowed-tools: [Bash, Read, Write, Glob, Grep, AskUserQuestion]
---

# DNR — Detailný návrh riešenia (WAME)

Vytvorí **záväzný projektový dokument** vo WAME vizuálnej identite, ktorý
predchádza vývoju webu/eshopu/systému/appky. Píše sa po schválení cenovej
kalkulácie. Bez odsúhlaseného DNR sa vývoj nezačína.

Vstupom je **ľubovoľná kombinácia**:

- 📁 priečinok s podkladmi (kickoff notes, kalkulácia, e-maily, návrhy),
- 📄 jednotlivé súbory (`.docx`, `.pdf`, `.md`, `.txt`),
- 💬 voľný textový popis priamo v prompte od používateľa,
- 🏗 kontext **existujúceho projektu** — ak sa skill spúšťa v git repe,
  automaticky doňho zaňhne hlbšie (moduly, Laravel layout, deps).

Výstupom je `.docx` v WAME brand identity (zelená `#20E87A`, navy `#091145`,
font Inter), s povinnými sekciami a v jazyku klienta.

## Argumenty

Používateľ to spustil ako: `$ARGUMENTS`

Akceptované formy:

- `/dnr-business <cesta>` — jeden súbor alebo priečinok
- `/dnr-business <cesta1> <cesta2> ...` — viac vstupov
- `/dnr-business` — bez vstupu, opieraj sa o popis v prompte a aktuálny repo
- `/dnr-business --output=docs/DNR.docx` — vlastná výstupná cesta
- `/dnr-business --lang=sk|cs|en` — vynúť jazyk dokumentu
- `/dnr-business --client="Firma s.r.o."` — preplň meno klienta
- `/dnr-business --project=web|eshop|system|app` — typ projektu
- `/dnr-business --init` — vytvor per-project `config.json`
- `/dnr-business --from-json=plan.json` — preskoč LLM, znova vyrender z plánu
- `/dnr-business --dry-run` — ulož len `plan.json`, `.docx` nevytváraj

## Krok za krokom

### Step 1 — Nájdi orchestrátorský skript

```bash
SCRIPT=$(find ~/.claude/plugins -path "*/dnr-business/skills/*/scripts/dnr_to_docx.py" -print -quit 2>/dev/null | head -1)
if [ -z "$SCRIPT" ]; then
    # Claude.ai cloud fallback: skript je vedľa SKILL.md
    SCRIPT="$(dirname "$0")/scripts/dnr_to_docx.py"
fi
test -f "$SCRIPT" || { echo "dnr-business plugin nie je správne nainštalovaný"; exit 1; }
PROMPT_DIR="$(dirname "$SCRIPT")/../prompts"
```

Ak skript chýba, oznám používateľovi a zastav.

### Step 2 — Spracuj `--init`

Ak používateľ poslal `--init`:

```bash
python3 "$SCRIPT" --init
```

Vypíš výslednú cestu ku konfigu. Stop.

### Step 3 — Spracuj `--from-json`

Ak používateľ poslal `--from-json=<cesta>`:

- Spusti `python3 "$SCRIPT" --validate --json <cesta>`. Ak validácia zlyhá,
  vypíš chyby a stop.
- Pokračuj rovno na **Step 8 (Render)**.

### Step 4 — Zber vstupov

Sparsuj argumenty na cesty (pozitívne argumenty, čokoľvek čo nezačína `--`).
Pre každú cestu over že existuje. Ak je to priečinok, skript ho prejde
rekurzívne (max 20 súborov, 200 KB každý).

```bash
python3 "$SCRIPT" --read-inputs --paths <p1> <p2> ... --pretty > /tmp/dnr_inputs.json
```

Výstup je `{"inputs":[{"path","text","warning"}]}`. Načítaj cez `Read` a
maj plain text všetkých podkladov pripravený na extrakciu.

Ak používateľ neposlal žiadnu cestu **a** v prompte nie je voľný popis,
opýtaj sa cez `AskUserQuestion`: kde sú podklady (cesta) alebo „popíš
projekt v skratke".

### Step 5 — Kontext repozitára (ak je git repo)

Over rýchlo:

```bash
git -C "$(pwd)" rev-parse --is-inside-work-tree 2>/dev/null && IS_REPO=1 || IS_REPO=0
```

Ak `IS_REPO=1`:

```bash
python3 "$SCRIPT" --scan-repo --root "$(pwd)" --pretty > /tmp/dnr_repo.json
```

Skripty vráti tree, ekosystém (Laravel/Vue/Next/…), package súbory, moduly
(`wamesk/*`, `Modules/*`, `app/Models`), a krátky výňatok z README. Pre
**relevantné moduly** ešte cez `Read` otvor 2–4 kľúčové súbory (modely,
servisné triedy, najväčšie controllery) — popis aktuálneho stavu v DNR
sekcii `vychodiskovy_stav` musí odrážať reálny kód, nie len README.

Ak `IS_REPO=0`, sekciu preskoč.

### Step 6 — Zber chýbajúcich informácií

Po prečítaní všetkých vstupov si pozri, či máš odpovede na týchto **5
kľúčových otázok**:

1. **Klient** — firma, kontaktná osoba, e-mail / telefón.
2. **Typ projektu** — web / eshop / systém / app / mixed.
3. **Hlavný biznis cieľ** — 1 vetou, prečo to klient potrebuje.
4. **Out of scope** — čo sa explicitne **NEbude** riešiť.
5. **Termín** — orientačné očakávané spustenie.

Ak chýba viac ako 2 z nich, **opýtaj sa naraz cez `AskUserQuestion`** (max
4 otázky v jednom volaní). Nikdy si neodpovede neodhaduj a nevymýšľaj
údaje — radšej použi reťazec `[DOPLNIŤ]` v JSONe a v záverečnom súhrne
ich vypíš ako otvorené body.

Argumenty z CLI majú prednosť: `--client="..."`, `--project=eshop`,
`--lang=sk` preplnia detegované hodnoty.

### Step 7 — Vygeneruj DNR JSON plán

Načítaj inštrukcie z `${PROMPT_DIR}/extract_inputs_to_json.md` a schému z
`${PROMPT_DIR}/dnr_json_schema.json`.

Ty (Claude) teraz robíš extrakciu:

1. Použiješ vstupy zo Step 4 + repo kontext zo Step 5 + odpovede zo Step 6.
2. Postupne vyplníš každú sekciu schémy.
3. Pre každú **technickú voľbu** zapíšeš biznis zdôvodnenie.
4. Sekcie 09 (Fázy) a 10 (Riziká) **nikdy** nevynechávaj — schéma to neprijme.
5. Polia ktoré nevieš vyplniť ostávajú s `[DOPLNIŤ]`.
6. Ulož ako `/tmp/dnr_plan.json`.

Validuj:

```bash
python3 "$SCRIPT" --validate --json /tmp/dnr_plan.json
```

Ak vráti chyby, oprav JSON a skús znova (max 3 pokusy). Typické chyby:

- chýbajúce povinné pole → doplň,
- `rizika` má < 5 položiek → doplň aspoň 5,
- nesprávny enum (`stav`, `dopad`, `pravdepodobnost`) → použi povolené hodnoty.

### Step 8 — Potvrdenie pred zápisom

Ukáž používateľovi kompaktný súhrn:

```
Klient:       <company>
Projekt:      <type> · <title>
Jazyk:        <lang>
Verzia:       v1.0  ·  Dátum: <date>

Sekcie:       12 povinných + N voliteľných
Fázy:         M (cca <total> týždňov)
Riziká:       K
Otvorené body (chýbajúce informácie): X

Výstup:       <output_path>
```

Ak používateľ poslal `--dry-run`, ulož len `plan.json` (vedľa output cesty)
a stop.

### Step 9 — Render do .docx

```bash
python3 "$SCRIPT" --build --json /tmp/dnr_plan.json --output "<output_path>"
```

Skript vyrobí finálny WAME-branded `.docx`. Vypíše:

```
{"ok": true, "output": "<absolútna cesta>"}
```

### Step 10 — Záverečný report

Ukáž:

```
✅ DNR vygenerované: <path>.docx

📋 Otvorené body — doplň pred odoslaním klientovi:
  - [DOPLNIŤ] kontakt-e-mail
  - [DOPLNIŤ] presný termín spustenia
  - ...

Ďalšie kroky:
  1. Prejdi dokument, doplň otvorené body.
  2. Verziu nastav na v1.1 pri prvej revízii po klientovom feedbacku.
  3. Po schválení môžeš použiť `/teamwork-tasks-from-dnr <path>.docx` na rozpísanie taskov.
```

## Voliteľné sekcie (A–E)

Ak je relevantné, naplň aj `volitelne.*` v JSONe:

- `wireframy` — pre projekty s dizajnovou fázou.
- `datovy_model` — pre komplexné systémy (popíš laicky, nie SQL).
- `seo` — kľúčové slová, URL štruktúra, schema markup.
- `migracia` — čo sa migruje, ako, kto, riziká.
- `skolenie` — plán školenia tímu klienta, support po spustení.

## Chyby a edge cases

- **DOCX vstup sa nepodarilo prečítať** → odporúč `pandoc <file>.docx -o <file>.md`.
- **PDF bez `pdftotext`** → odporúč `brew install poppler` alebo prevod na DOCX.
- **Žiadne vstupy, žiaden popis, žiadne repo** → cez `AskUserQuestion` pýtaj
  buď cestu k podkladom, alebo „povedz mi v 3 vetách čo klient chce" — bez
  tohoto nedáva zmysel pokračovať.
- **Validácia padá opakovane** → ulož partial JSON do `/tmp/dnr_plan_partial.json`,
  vypíš diff voči schéme, stop.
- **Klient neuviedol jazyk** → detekuj z podkladov (sk/cs/en heuristikou
  podľa stopwords). CLI `--lang=` preplní.

## Konfigurácia

Per-project config:

```
~/.claude/plugins/data/dnr-business-wamesk/<project-hash>/config.json
```

Vytvoríš cez `/dnr-business --init`. Kľúčové polia:

- `output_dir` — kam ukladať `.docx` (default `docs`).
- `language` — `auto` (detekcia) alebo `sk`/`cs`/`en`. `--lang` preplní.
- `default_version` — `v1.0`.
- `client.*` — predvyplnené údaje klienta pre rýchly opakovaný použitie.

## Pravidlá obsahu

- Každú technickú voľbu **zdôvodni biznis prínosom** pre klienta.
- Vyhýbaj sa technickým skratkám bez vysvetlenia.
- Namiesto „cenová ponuka" píš vždy **„cenová kalkulácia"**.
- Tón: odborný, ľudský, sebavedomý — bez buzzwordov.
- Diakritiku zachovávaj — žiadne ASCII náhrady.
- `verzia` začína `v1.0`, pri zásadnej revízii bump na `v1.1` / `v2.0`.

## Súvisiace skilly

- `/teamwork-tasks-from-dnr` — z hotového DNR `.docx` vygeneruje Teamwork
  import-ready XLSX + Markdown plán.
- `/teamwork-task` — implementuje tasky vytvorené z DNR v repe.
