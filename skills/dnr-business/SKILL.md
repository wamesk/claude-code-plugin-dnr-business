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
font Calibri s Carlito fallback), s povinnými sekciami a v jazyku klienta.

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

## WAME estimate methodology

> Block version `wame-estimate-v2`. Shared **verbatim** across the plugins
> `teamwork-task-analyze`, `teamwork-tasks-from-dnr`, `teamwork-tasks-from-desk`,
> `teamwork-tasks-from-session` and `dnr-business`. Change it in all five or in
> none — a per-plugin variant is how two skills start quoting different numbers
> for the same task.

**Estimate one number, directly.** Do not produce a "traditional" estimate and
then multiply it by a speedup and a buffer. Two percentages stacked on a guess
open a band almost twice as wide as the guess itself, and in a negotiation the
widest end of that band always wins. Name the minutes the work takes and defend
that number.

**Who does the work.** A senior engineer who already knows this codebase,
directing Claude Code. Claude Code writes the implementation and the tests; the
engineer decides, reviews and runs the suite. There is no separate QA pass and
no handover to a second person.

**What the number covers**

- Reading the relevant code and reproducing the reported behaviour
- The implementation itself
- Writing or extending the test, and running the affected tests
- Self-review and the fixes it produces
- One round of review feedback

**What the number never covers** — estimate each of these as its own task instead
of folding it in

- Deployment, running the migration on production, fixing production data
- Talking to the client or the PO, and waiting for the answer
- Any work that sits behind an unanswered `[OTVORENÉ]` question
- Anything the task itself declares out of scope

**Shape of the number**

- A multiple of 15 minutes. Never below 15.
- Above 240 minutes: propose a split into 2–6 atomic subtasks. That threshold is
  `propose_split_threshold_minutes` and it is the real ceiling in daily use.
- 480 minutes is a hard cap. Work that will not fit under it is not a task yet.

**Anchors.** These are finished outcomes, not categories of feeling. Pick the
closest line and move by at most one 15-minute step. If the number you want is
more than one step away from every anchor, write down in the reasoning what makes
this case different — that sentence is what a reviewer checks.

| Finished work | Minutes |
|---|---|
| Text, label, translation key or config value, plus the test that guards it | 15 |
| One field, filter or validation rule on one screen, plus a test | 30 |
| Bug with a stack trace or a one-line repro: fix plus regression test | 60 |
| Vue/React component wired to an API that already exists, plus a test | 90 |
| Bug that reproduces but spans 2–3 layers: fix plus tests | 120 |
| One CRUD endpoint or one screen end to end, plus tests | 120 |
| Bug with no repro yet: investigate, then fix | 180 |
| Schema migration with a data backfill and a copy-back assertion | 180 |
| New module in `wamesk/*` (model, migration, Nova screen, policy, tests) | 300 |

**Uncertainty is an open question, not a surcharge.** When you cannot size the
work, you have found something the task does not say yet. Write that question
into the task, estimate the investigation that answers it, and state in the
reasoning what the fix costs under each likely answer. A number with a written
assumption survives review. A number padded for "unknown unknowns" does not, and
it hides the question that was worth asking.

**Do not pad a task because it is labelled TBD**, and do not shrink a real
multi-layer bug so the list looks cheap. Both errors cost the same trust.

**Why this replaced the old rule.** Hand-written estimates used to run about
twice the real cost, which lost us work we should have won. The first fix was a
30–50 % speedup factor with a 15–30 % buffer on top — but that chain put the
padding straight back while sounding rigorous, and it produced a 0.58×–0.91×
band on every single task. The anchors above carry the same judgement as one
number. The measured feedback loop is the `teamwork-tasks-from-session` plugin,
which shows the methodology estimate and the real logged session time side by
side. When those two drift apart on the same kind of work, change the anchors
here — never re-introduce a buffer percentage.

### Applying this to DNR phase durations

Phase `trvanie` is the sum of the per-task estimates above, rolled up to weeks
and written as a range. The range must come from something the DNR can name.

- Sum the task minutes in the phase using the rules above (15-minute step,
  ≤ 480 min per task, anchors as the sanity check).
- Convert to working days at 6 productive hours per day (360 min/day).
- Convert to working weeks at 5 days per week, rounded **up** to whole weeks.
  That is the lower bound.
- The upper bound is the lower bound **plus the work that is not decided yet**:
  add the estimated minutes of every open question, every `[DOPLNIŤ]` item and
  every client-side dependency that sits in this phase, then round up to whole
  weeks again. The gap between the two numbers is then a thing you can point at
  in a meeting.
- When a phase has no open items, the range is still two numbers, one week
  apart — whole-week rounding is itself an honest ±1 week. Never publish a
  single week number; it claims a precision nobody has.

**Do not add a flat percentage on top.** Version 1.2.x told you to add 25–35 %
to the rolled-up figure. Together with the speedup-and-buffer chain the old
methodology used, a client-facing duration could land *above* a plain
hand-written estimate — the exact outcome the methodology was written to stop.
The per-task numbers already carry their own judgement; padding them a second
time at the phase level is padding the same risk twice.

Tasks that fall outside the calibration anchors go in the follow-up section by
name. Never widen a phase quietly to cover them.

---

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

### Step 7.5 — Vizuály: obrázky a wireframe placeholdery

Pre každý modul v `popis_riesenia.moduly` rozhodni, či má dostať **obrázok**:

**Ak vo vstupoch (Step 4) sú obrázky/screenshoty** (PNG/JPG priložené v podklade
alebo extrahované z `.docx`):

1. Skontroluj priečinok podkladov aj `media/` priečinok rozbaleného `.docx`
   (cez `unzip -l <file>.docx | grep -i media`). Obrázky vyextrahuj cez:
   ```bash
   unzip -j -o <input>.docx 'word/media/*' -d /tmp/dnr_images/
   ```
2. Pre každý obrázok rozhodni, **ku ktorému modulu / sekcii sa hodí** (názov
   súboru, kontext v okolitom texte, OCR ak treba).
3. V JSON pláne pridaj k modulu pole `obrazok` (absolútna cesta) a voliteľne
   `obrazok_popis` (popisok pod obrázok).
   ```json
   {
     "nazov": "Marketingové súhlasy",
     "popis": "...",
     "obrazok": "/tmp/dnr_images/image3.png",
     "obrazok_popis": "Obrazovka súhlasov v admin paneli"
   }
   ```

**Obrázky skopíruj vedľa výstupného dokumentu, nenechávaj ich v `/tmp`.** Plán je
trvalý artefakt — `--from-json` z neho rendruje znova aj o mesiac — ale `/tmp` sa
vyprázdni. Cesta v `obrazok`, ktorá už neexistuje, prejde cez `register_image()`
ako `None` a obrázok aj s popisom z dokumentu ticho vypadne. Presuň ich do
`<output_dir>/images/` a v pláne uveď tú cestu.

**Ak obrázky nie sú dostupné, ale wireframe by bol vhodný** (typicky pre nové
UI obrazovky, nové user flows, dôležité formuláre), pridaj `wireframe` blok
namiesto `obrazok`:

```json
{
  "nazov": "Prihlásenie cez OTP",
  "popis": "...",
  "wireframe": {
    "title": "Obrazovka zadania OTP kódu",
    "description": "Wireframe ukáže layout obrazovky, kde používateľ zadáva 6-miestny OTP kód doručený SMS.",
    "checklist": [
      "Pole pre 6-miestny OTP kód (oddelené boxy alebo jedno pole)",
      "Tlačidlo 'Overiť kód' (primárne)",
      "Odkaz 'Poslať znova' s 60s odpočtom",
      "Indikátor zostávajúceho času platnosti kódu",
      "Tlačidlo 'Späť' k zadávaniu čísla"
    ]
  }
}
```

Skript ho vyrenderuje ako **zvýraznený blok so zelenou ľavou hranou** —
vizuálne odlíšený od bežného textu, aby bolo jasné, že tam má prísť reálny
wireframe.

**Kedy pridať wireframe placeholder:** ak modul popisuje obrazovku/UI/flow,
ktorý nie je triviálny (login formulár nie, viacstupňový wizard áno). Ak je
modul čisto backendový (cron, API endpoint, integrácia), placeholder
nepridávaj.

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

**Existujúci dokument nikdy neprepíš.** `--build` otvára výstupný súbor v režime
`"w"` (`write_docx()` → `zipfile.ZipFile(out_path, "w")`), takže čokoľvek na tej
ceste zmaže celé — vrátane ručne doplnených `[DOPLNIŤ]` položiek, vložených
screenshotov a poznámok, ktoré do `.docx` pridal človek po predchádzajúcom behu.
Step 10 pritom presne to odporúča, takže druhý beh nad tou istou cestou je bežný
scenár, nie výnimka. Pred renderom over:

```bash
test -e "<output_path>" && echo EXISTS || echo FREE
```

Ak vypíše `EXISTS`, **nerenderuj**. Cez `AskUserQuestion` sa opýtaj, či má nová
verzia ísť vedľa (`DNR_v1.1.docx` — odporúčané), alebo sa má pôvodný súbor
prepísať; prepíš len na výslovné potvrdenie.

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

## Číslované vs. odrážkové zoznamy

Skript automaticky **čísluje** (1., 2., 3.) tieto zoznamy:

- `ciele.biznis`, `ciele.technicke`, `ciele.out_of_scope`
- `popis_riesenia.moduly[].funkcie`, `sitemap`, `user_flows`
- `fazy[].vystupy`

Tieto zoznamy sú **odrážkové** (●):

- `vychodiskovy_stav.co_zostava`
- `popis_riesenia.moduly[].priklady`
- `technicke_riesenie.bezpecnost`, `gdpr.osobne_udaje`
- `podmienky.wame_zavazky`, `podmienky.klient_zavazky`
- `fazy[].zodpovednost.{wame,klient}`

Heuristika: **enumerable kroky/výstupy** (kde poradie alebo počet má váhu)
sú číslované, **kvalitatívne popisy** sú s odrážkami.

**Každý číslovaný zoznam štartuje od 1.** Od verzie 1.1.2 nepokračujú čísla
naprieč zoznamami: napr. `funkcie` modulu 2 začínajú znova od 1., nie od
počtu položiek modulu 1. Pod kapotou skript alokuje samostatnú `<w:num>`
inštanciu (zdieľa rovnaký abstract numFormat) pre každý logický zoznam, takže
Word udržiava nezávislé počítadlo per-list. Pre sub-položky (nested
`{"text": "...", "level": 1}` v rámci toho istého zoznamu) sa použije `a)`,
`b)`, `c)` — ide o pokračujúce číslovanie v rámci toho istého zoznamu.

## Súvisiace skilly

- `/teamwork-tasks-from-dnr` — z hotového DNR `.docx` vygeneruje Teamwork
  import-ready XLSX + Markdown plán.
- `/teamwork-task` — implementuje tasky vytvorené z DNR v repe.
