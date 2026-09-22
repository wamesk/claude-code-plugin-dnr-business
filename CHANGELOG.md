# Changelog

All notable changes to the `dnr-business` plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] — 2026-09-22

### Fixed
- **Client screenshots disappeared from the DNR without a word.** `register_image()`
  returns `None` for a missing file or any extension outside `{png,jpg,jpeg,gif,svg}`,
  and the caller simply skipped the paragraph — so the image **and its caption** vanished
  while `--build` still printed `{"ok": true}`. Step 7.5 tells the model to unzip
  `word/media/*` out of the client's own `.docx`, and Word's media folder routinely holds
  `.emf`, `.wmf`, `.webp` and `.bmp`. Dropped images are now collected and reported on
  stderr and in the JSON as `image_warnings`.
- **A second path produced a document Word offers to repair.** `write_docx()` caught
  `OSError` and passed when copying an image binary into `word/media/`, but the
  relationship and the `<w:drawing>` were already committed to `word/document.xml` — so
  the result was a dangling rId, reported as success. Those are now `image_errors`, and
  `--build` exits non-zero: a corrupt document is a failure, a missing picture is a
  warning.
- Step 9 gained a render gate for a neighbouring loss: `--build` opens the output path
  with `zipfile.ZipFile(out_path, "w")`, so a second run wipes whatever a human added to
  the previous `.docx` — filled-in `[DOPLNIŤ]` items, pasted screenshots, notes. Step 10
  recommends exactly that second run, so it is the normal case, not an edge one. The
  skill now checks for an existing file and asks before overwriting it.

### Changed
- Images extracted to `/tmp/dnr_images/` are referenced by absolute path in the durable
  plan, so a later `--from-json` re-render silently loses every one of them once `/tmp`
  is swept. Called out where the extraction is described.

## [1.3.0] — 2026-09-22

### Changed
- **Estimate methodology replaced — `wame-estimate-v2`.** The old rule produced a
  "traditional" estimate, cut it by 30–50 % for Claude Code, then added a 15–30 %
  buffer on top. Two percentages stacked on a guess give a 0.58×–0.91× band on
  every task, so the same work could legitimately be quoted at 60 or at 95
  minutes and the wider end always won the argument. The methodology now
  estimates **one number directly** against a table of finished-outcome anchors.
  The anchors are tighter (a single figure each, adjust by at most one 15-minute
  step) and the block states explicitly what the number covers — reproduce,
  implement, test, run the suite, self-review, one review round — and what it
  never covers: deployment, production data fixes, client communication, and any
  work behind an unanswered `[OTVORENÉ]` question.
- **Uncertainty is now an open question, not a surcharge.** Where the old text
  told you to pad for "unknown unknowns", the new one tells you to write the
  question into the task, estimate the investigation that answers it, and state
  what the fix costs under each answer.
- **The 240-minute split threshold is now named as the working ceiling**, so it
  no longer contradicts the 480-minute hard cap sitting in the same paragraph.
- The methodology block is byte-identical across `teamwork-task-analyze`,
  `teamwork-tasks-from-dnr`, `teamwork-tasks-from-desk`,
  `teamwork-tasks-from-session` and `dnr-business`, and now carries a version
  marker so a drifted copy is visible.

### Fixed
- **The client-facing phase duration was padded three times over.** Per-task
  minutes already carried the old 30–50 % cut and 15–30 % buffer; the phase
  roll-up then added a further **+25–35 %** as the upper bound of the published
  range. A duration shown to a client could therefore land *above* a plain
  hand-written estimate — the exact outcome the methodology exists to prevent.
  The flat percentage is gone. The lower bound is the rolled-up figure rounded up
  to whole weeks; the upper bound adds the estimated minutes of the work that is
  **not decided yet** — every open question, every `[DOPLNIŤ]`, every client-side
  dependency in that phase — rounded up again. The gap between the two numbers is
  now a thing you can point at in a meeting.
- A phase with no open items still publishes a two-number range one week wide.
  Whole-week rounding is itself an honest ±1 week, and a single week number
  claims a precision nobody has.
- `prompts/extract_inputs_to_json.md` carried the same chain in Slovak and is
  updated to match.

### Removed
- The flat +25–35 % phase reserve, and the config keys `estimate.buffer_pct_min`, `estimate.buffer_pct_max`,
  `estimate.speedup_pct_min` and `estimate.speedup_pct_max`. The config
  migration deletes them from files written by earlier versions and renames
  `methodology` from `wame_senior_claude_code` to `wame_estimate_v2` — a stale
  `buffer_pct_max` left in the file reads like a rule somebody still follows.

## [1.2.1] — 2026-06-11

### Fixed
- **Risk-level enum mismatch that failed JSON validation on nearly every
  run.** The schema in `prompts/dnr_json_schema.json` defined the `rizika[]`
  `dopad` and `pravdepodobnost` enums in ASCII (`nizky`/`stredny`/`vysoky`,
  `nizka`/`stredna`/`vysoka`), while the extraction prompt
  (`prompts/extract_inputs_to_json.md`) and the global "keep diacritics" rule
  steer the model to emit the diacritic forms (`nízky`/`stredný`/`vysoký`,
  `nízka`/`stredná`/`vysoká`). The unconditional enum validator in
  `scripts/dnr_to_docx.py` then rejected the valid output. The schema enums
  now use the diacritic forms, matching the prompt and the diacritics rule.
  The docx renderer prints the risk values verbatim, so the table output maps
  correctly without further changes.

## [1.2.0] — 2026-06-04

### Added
- **WAME estimate methodology** is now documented as an explicit
  `## WAME estimate methodology` H2 block in `SKILL.md`, placed before
  Step 7 (the DNR JSON extraction step). It defines the senior-engineer +
  Claude Code model: per-task estimates are 30–50% lower than legacy
  hand-written ones, padded with a 15–30% buffer for risk, capped at 480 min
  per task and rounded to 15-min steps. Six calibration anchors (CRUD
  endpoint, Vue component, new `wamesk/*` module, schema migration, bugfix
  with repro, bugfix without repro) are listed as sanity checks.
- The same block is byte-identical with the corresponding section in the
  `teamwork-task-analyze` v1.0.0 and `teamwork-tasks-from-dnr` v1.2.0
  plugins — one source of truth, three places to keep in sync.
- New derived sub-block `### Applying this to DNR phase durations`
  immediately after the methodology, which maps the per-task minute
  estimates onto **phase** `trvanie`: sum task minutes per phase, convert
  at 6 productive hours/day × 5 days/week, and **always express as a range**
  (e.g. "3–4 weeks") with the upper bound +25–35% above the rolled-up
  lower bound. The range itself is the client-visible buffer — single-number
  durations are explicitly forbidden.
- `prompts/extract_inputs_to_json.md` rule 6 ("Sekcia Fázy") now references
  the methodology and the derived phase-duration rules, so the LLM
  extraction produces ranges that are reproducible across runs and across
  engineers.

### Changed
- No JSON schema change — `trvanie` remains a free-form string. The
  methodology only constrains **how** the model writes the string, not the
  contract.
- Rationale captured directly in SKILL.md: legacy estimates were ~2× too
  high and not competitive; manual reductions were the workaround. The
  methodology encodes the same judgement so two analysts produce the same
  range for the same scope and so the client always sees the buffer
  baked into the dates.

## [1.1.2] — 2026-06-03

Fix runaway numbering across independent lists.

### Fixed
- **Numbered lists no longer share a global counter.** Previously every
  decimal list referenced `numId=2`, so `funkcie` in module 5 would render as
  `28.`, `29.`, `30.` instead of `1.`, `2.`, `3.`. Every `_render_list(...,
  numbered=True)` call now allocates its own `<w:num>` instance that shares
  the existing decimal `<w:abstractNumId>` — Word maintains an independent
  counter per instance, so each list visibly restarts at 1.
- This affects every numbered section in the document: `ciele.{biznis,
  technicke, out_of_scope}`, per-module `funkcie`, `sitemap`, `user_flows`,
  and per-phase `vystupy`. Sub-levels (a/b/c, i/ii/iii) still continue
  within their own list as before.

### Changed
- `NUMBERING_XML` is now generated by `_numbering_xml()` at render time. The
  two reserved IDs (`numId=1` bullets, `numId=2` legacy decimal) are kept;
  freshly allocated IDs start at 100 and are appended for each list used.
- `_numbered(text, num_id=2)` accepts a `num_id` parameter; default keeps
  backward compatibility for any direct caller.

---

## [1.1.1] — 2026-05-29

Visual polish driven by direct feedback against the WAME brand reference.

### Changed
- **Font**: switched from `Inter` to `Calibri` for universal availability across
  Windows/Mac, MS Office, LibreOffice and Google Docs. Declared `fontTable.xml`
  with `Carlito` → `Arial` fallback chain so layout stays consistent on systems
  without Calibri (metric-identical substitution under LibreOffice).
- **Cover logo**: replaced the green-dot pattern with `WAME` (navy bold) +
  ` s.r.o.` (green bold) — same treatment applied to the page header.
- **Header hairline**: `single` 1.5pt navy (`sz=12`, `space=4`) instead of the
  thin 0.5pt grey line that some renderers anti-aliased into an "embossed"
  look.
- **Footer**: now includes the project title and version —
  `Dôverné — interný dokument WAME s.r.o. · DNR — {title} · {version}`.
- **Footer hairline**: navy 1.5pt single line (matches header).
- **Signature page**: simplified to a single tall row per party
  (~5 cm, `trHeight=3000`) with `Meno / Funkcia / Dátum` on top and a `Podpis`
  line at the bottom; plenty of vertical breathing room for the handwritten
  signature without burning a whole page.

### Added
- **`WameTable` style** in `styles.xml` with `tblStyleRowBandSize=1`,
  `firstRow` (navy fill, white bold) and `band1Horz` (light tint)
  conditional formatting. Tables are emitted with `<w:tblStyle>` +
  `<w:tblLook>` so rows added manually in Word inherit the next band's tint
  automatically.
- **Belt-and-suspenders banding**: existing rows also receive inline
  `<w:shd>` matching the `band1Horz` fill so banding is visible in readers
  that don't render custom table styles (older LibreOffice, Google Docs).
- **`<w:updateFields w:val="true"/>`** in `settings.xml` — Word now recalculates
  `PAGE` / `NUMPAGES` automatically on first open, so the footer shows the
  real page count without `Ctrl+A → F9`.
- **Robust bullet styling**: numbering definitions now carry `<w:nsid>`,
  `<w:tplc>` template codes, and `<w:rFonts w:hint="default"/>` on every
  level so the green `●` bullet stays green when a user presses Enter to add
  a new row.

### Fixed
- `WAME_LIGHT` palette token (`F4F5F8` → `EAEEF4`) — visibly tinted band fill.

---

## [1.1.0] — 2026-05-28

Refined the WAME-branded DOCX renderer against the
`DNR_Marketing_Consent_v2.0` reference document.

### Added
- **Schema**: cover `subtitle` + header `confidentiality` fields on `meta`;
  per-module `obrazok` / `obrazok_popis` and `wireframe` placeholder block;
  signatory fields accept a string or `{meno, funkcia, datum}` object.
- **Renderer**: PNG/JPG image embedding with optional captions inside module
  blocks; wireframe placeholders rendered as highlighted, left-bordered
  callout blocks.
- **SKILL.md**: Step 7.5 (visuals), wireframe guidance, numbered vs.
  bulleted list rules, configuration notes.

### Changed
- Brand palette, cover page, headers and table styling calibrated to the
  reference document.
- Numbered vs. bulleted list heuristics aligned with the SKILL specification.

---

## [1.0.0] — 2026-05-28

Initial release.

### Added
- WAME DNR generator delivered as a Claude Code plugin **and** a Claude.ai
  skill that produces a branded `.docx` Detailný návrh riešenia from a
  folder, file(s), free-form description, and the existing project context
  when invoked inside a Git repo.
- Stdlib-only OOXML generator (`zipfile` + `xml.etree`) — no external
  dependencies, no template files.
- WAME palette (`#20E87A` accent, `#091145` navy) with Inter as the working
  font.
- Schema-enforced mandatory sections including Fázy and Riziká
  (min. 5 entries).
- Input reader for `.docx` / `.md` / `.txt` / `.pdf`, repo deep-scan helper,
  JSON validator, and per-project config init.

[1.2.1]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.2.1
[1.1.2]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.1.2
[1.1.1]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.1.1
[1.1.0]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.1.0
[1.0.0]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.0.0
