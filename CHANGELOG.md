# Changelog

All notable changes to the `dnr-business` plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.1.1]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.1.1
[1.1.0]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.1.0
[1.0.0]: https://github.com/wamesk/claude-code-plugin-dnr-business/releases/tag/v1.0.0
