#!/usr/bin/env python3
"""WAME DNR (Detailny navrh riesenia) generator.

Stdlib-only orchestrator for the dnr-business Claude Code skill.

Subcommands
-----------
--read-inputs --paths <p1> [<p2> ...]
    Dump plain text from supported files (.docx/.md/.txt; .pdf if pdftotext is
    available). Result is printed as JSON {"inputs":[{"path","text","warning"}]}.

--scan-repo --root <dir>
    Detect language ecosystem, top-level dirs (depth 3, ignoring vendor/node_modules),
    list of Laravel/PHP modules (wamesk/*, Modules/*, app/Models), package files,
    short README excerpt. Prints JSON.

--validate --json <path>
    Validate a DNR plan JSON against the bundled schema. Prints
    {"ok":bool,"errors":[...]} and exits 0/1.

--build --json <path> --output <docx_path>
    Render the DNR JSON as a WAME-branded .docx file.

--init
    Copy config.example.json into the per-project config dir.

Designed to run on Python 3.8+ without external dependencies.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
PROMPTS_DIR = SKILL_ROOT / "prompts"
SCHEMA_PATH = PROMPTS_DIR / "dnr_json_schema.json"

# WAME brand palette
WAME_GREEN = "20E87A"
WAME_NAVY = "091145"
WAME_LIGHT = "F4F5F8"
WAME_TEXT = "1A1A1A"
WAME_MUTED = "5C6679"
WAME_FONT = "Inter"
WAME_FONT_FALLBACK = "Calibri"


# ---------------------------------------------------------------------------
# Input reading
# ---------------------------------------------------------------------------

def _read_docx_text(path: Path) -> Tuple[str, Optional[str]]:
    """Extract plain text from a .docx by walking word/document.xml."""
    try:
        with zipfile.ZipFile(path) as zf:
            with zf.open("word/document.xml") as fh:
                tree = ET.parse(fh)
    except (zipfile.BadZipFile, KeyError) as exc:
        return ("", f"docx parse failed: {exc}")

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines: List[str] = []
    for para in tree.iter(f"{{{ns['w']}}}p"):
        chunks = [t.text or "" for t in para.iter(f"{{{ns['w']}}}t")]
        line = "".join(chunks).strip()
        if line:
            lines.append(line)
    return ("\n".join(lines), None)


def _read_pdf_text(path: Path) -> Tuple[str, Optional[str]]:
    if not shutil.which("pdftotext"):
        return ("", "pdftotext (poppler) not installed; convert to .docx or .md")
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True, capture_output=True, text=True, timeout=60,
        )
        return (out.stdout, None)
    except subprocess.CalledProcessError as exc:
        return ("", f"pdftotext exit {exc.returncode}: {exc.stderr.strip()[:120]}")
    except subprocess.TimeoutExpired:
        return ("", "pdftotext timeout")


def _read_text_file(path: Path) -> Tuple[str, Optional[str]]:
    try:
        return (path.read_text(encoding="utf-8", errors="replace"), None)
    except OSError as exc:
        return ("", str(exc))


def read_inputs(paths: Iterable[str], max_bytes: int = 200_000) -> List[Dict[str, Any]]:
    """Walk the given paths (files or dirs) and extract plain text."""
    results: List[Dict[str, Any]] = []
    supported = {".docx", ".md", ".markdown", ".txt", ".pdf", ".rtf", ".csv"}
    files: List[Path] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            results.append({"path": str(p), "text": "", "warning": "not found"})
            continue
        if p.is_file():
            files.append(p)
        else:
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in supported and ".git" not in f.parts:
                    files.append(f)
                    if len(files) >= 20:
                        break
    for f in files:
        size = f.stat().st_size
        if size > max_bytes:
            results.append({
                "path": str(f),
                "text": "",
                "warning": f"file too large ({size} bytes); skipped",
            })
            continue
        suf = f.suffix.lower()
        if suf == ".docx":
            text, warn = _read_docx_text(f)
        elif suf == ".pdf":
            text, warn = _read_pdf_text(f)
        else:
            text, warn = _read_text_file(f)
        results.append({"path": str(f), "text": text, "warning": warn})
    return results


# ---------------------------------------------------------------------------
# Repository deep scan
# ---------------------------------------------------------------------------

def scan_repo(root: Path) -> Dict[str, Any]:
    """Detect ecosystem + key project landmarks for richer DNR context."""
    out: Dict[str, Any] = {"root": str(root), "ecosystem": [], "modules": [], "tree": []}
    ignore = {"node_modules", "vendor", ".git", ".idea", "build", "dist", "__pycache__",
              ".pytest_cache", "storage", "bootstrap", ".venv", "venv"}

    # ecosystem detection
    landmarks = {
        "composer.json": "php/laravel",
        "package.json": "node/js",
        "requirements.txt": "python",
        "pyproject.toml": "python",
        "go.mod": "go",
        "Cargo.toml": "rust",
        "Gemfile": "ruby",
        "artisan": "laravel",
        "next.config.js": "nextjs",
        "nuxt.config.ts": "nuxtjs",
        "vite.config.ts": "vite",
    }
    for name, eco in landmarks.items():
        if (root / name).is_file():
            out["ecosystem"].append(eco)
            if name in ("composer.json", "package.json"):
                try:
                    data = json.loads((root / name).read_text(encoding="utf-8"))
                    out.setdefault("package_files", {})[name] = {
                        "name": data.get("name"),
                        "deps": list((data.get("require") or data.get("dependencies") or {}).keys())[:25],
                    }
                except (OSError, json.JSONDecodeError):
                    pass

    # tree (depth 3)
    def _walk(p: Path, depth: int = 0) -> List[str]:
        if depth > 2:
            return []
        items: List[str] = []
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except OSError:
            return items
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in (".env.example",):
                continue
            if entry.name in ignore:
                continue
            rel = entry.relative_to(root)
            items.append(("  " * depth) + ("📁 " if entry.is_dir() else "• ") + str(rel))
            if entry.is_dir():
                items.extend(_walk(entry, depth + 1))
            if len(items) > 250:
                break
        return items

    out["tree"] = _walk(root)[:250]

    # modular Laravel detection
    for candidate in ("wamesk", "Modules", "app/Modules"):
        d = root / candidate
        if d.is_dir():
            mods = [x.name for x in sorted(d.iterdir()) if x.is_dir()]
            if mods:
                out["modules"].append({"layout": candidate, "modules": mods})
    models = root / "app" / "Models"
    if models.is_dir():
        out["models"] = [x.stem for x in sorted(models.glob("*.php"))]

    # README excerpt
    for candidate in ("README.md", "Readme.md", "readme.md"):
        rp = root / candidate
        if rp.is_file():
            try:
                out["readme_excerpt"] = rp.read_text(encoding="utf-8")[:4000]
            except OSError:
                pass
            break

    return out


# ---------------------------------------------------------------------------
# JSON schema validation (minimal, no jsonschema dep)
# ---------------------------------------------------------------------------

def _type_ok(value: Any, expected: str) -> bool:
    return {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
        "null": value is None,
    }.get(expected, True)


def _validate_node(value: Any, schema: Dict[str, Any], path: str, errors: List[str]) -> None:
    if "type" in schema and not _type_ok(value, schema["type"]):
        errors.append(f"{path}: expected {schema['type']}, got {type(value).__name__}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: '{value}' not in {schema['enum']}")
    if schema.get("type") == "object":
        for req in schema.get("required", []):
            if req not in (value or {}):
                errors.append(f"{path}: missing required '{req}'")
        for k, sub in schema.get("properties", {}).items():
            if k in (value or {}):
                _validate_node(value[k], sub, f"{path}.{k}", errors)
    elif schema.get("type") == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: minItems={schema['minItems']}, got {len(value)}")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate_node(item, schema["items"], f"{path}[{i}]", errors)


def validate_plan(plan: Dict[str, Any]) -> List[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: List[str] = []
    _validate_node(plan, schema, "$", errors)
    return errors


# ---------------------------------------------------------------------------
# DOCX rendering (stdlib OOXML)
# ---------------------------------------------------------------------------

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _para(text: str, *, style: Optional[str] = None, bold: bool = False,
          color: Optional[str] = None, size: Optional[int] = None,
          align: Optional[str] = None, font: Optional[str] = None) -> str:
    """Build a <w:p> XML string."""
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    align_xml = f'<w:jc w:val="{align}"/>' if align else ""
    rpr_parts: List[str] = []
    if bold:
        rpr_parts.append("<w:b/>")
    if color:
        rpr_parts.append(f'<w:color w:val="{color}"/>')
    if size:
        rpr_parts.append(f'<w:sz w:val="{size * 2}"/>')
    if font:
        rpr_parts.append(
            f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
        )
    rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>" if rpr_parts else ""
    safe = _xml_escape(text)
    # respect newlines inside the same paragraph via <w:br/>
    parts = safe.split("\n")
    runs: List[str] = []
    for i, segment in enumerate(parts):
        if i:
            runs.append(f"<w:r>{rpr}<w:br/></w:r>")
        runs.append(
            f'<w:r>{rpr}<w:t xml:space="preserve">{segment}</w:t></w:r>'
        )
    return (
        f"<w:p><w:pPr>{style_xml}{align_xml}</w:pPr>{''.join(runs)}</w:p>"
    )


def _heading(text: str, level: int = 1) -> str:
    style = {1: "Heading1", 2: "Heading2", 3: "Heading3"}.get(level, "Heading1")
    return _para(text, style=style)


def _bullet(text: str, level: int = 0) -> str:
    safe = _xml_escape(text)
    return (
        '<w:p>'
        f'<w:pPr><w:pStyle w:val="ListBullet"/>'
        f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="1"/></w:numPr>'
        '</w:pPr>'
        f'<w:r><w:t xml:space="preserve">{safe}</w:t></w:r>'
        '</w:p>'
    )


def _spacer() -> str:
    return '<w:p><w:pPr><w:spacing w:after="120"/></w:pPr></w:p>'


def _table(rows: List[List[str]], *, header: bool = True,
           col_widths: Optional[List[int]] = None) -> str:
    """Build a <w:tbl> with WAME styling. Widths in twentieths of a point (1/20 pt)."""
    if not rows:
        return ""
    n_cols = max(len(r) for r in rows)
    if col_widths is None:
        # Default: equally distribute 9000 twips (~6.25 inches) across columns
        col_widths = [9000 // n_cols] * n_cols
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in col_widths)
    tbl_pr = (
        "<w:tblPr>"
        '<w:tblW w:type="dxa" w:w="9000"/>'
        '<w:tblBorders>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{WAME_MUTED}"/>'
        f'<w:left w:val="single" w:sz="6" w:space="0" w:color="{WAME_MUTED}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{WAME_MUTED}"/>'
        f'<w:right w:val="single" w:sz="6" w:space="0" w:color="{WAME_MUTED}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{WAME_MUTED}"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="{WAME_MUTED}"/>'
        "</w:tblBorders>"
        "</w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>"
    )

    tr_parts: List[str] = []
    for i, row in enumerate(rows):
        is_header = header and i == 0
        cells: List[str] = []
        for j in range(n_cols):
            text = row[j] if j < len(row) else ""
            shade = WAME_NAVY if is_header else "FFFFFF"
            color = "FFFFFF" if is_header else WAME_TEXT
            bold = is_header
            tc_pr = (
                f'<w:tcW w:type="dxa" w:w="{col_widths[j]}"/>'
                f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>'
                '<w:tcMar><w:top w:w="80" w:type="dxa"/>'
                '<w:left w:w="120" w:type="dxa"/>'
                '<w:bottom w:w="80" w:type="dxa"/>'
                '<w:right w:w="120" w:type="dxa"/></w:tcMar>'
            )
            content = _para(
                text, bold=bold, color=color, size=10, font=WAME_FONT,
            )
            cells.append(f"<w:tc><w:tcPr>{tc_pr}</w:tcPr>{content}</w:tc>")
        tr_parts.append(f"<w:tr>{''.join(cells)}</w:tr>")
    return f"<w:tbl>{tbl_pr}{''.join(tr_parts)}</w:tbl>"


def _section_title(idx: str, text: str) -> str:
    return _heading(f"{idx} — {text}", level=1)


# ---------- DOCX skeleton parts ----------

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
'''

ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
'''

DOC_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>
'''

SETTINGS_XML = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="{W_NS}">
  <w:defaultTabStop w:val="708"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
  <w:compat>
    <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
  </w:compat>
</w:settings>
'''

NUMBERING_XML = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{W_NS}">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="{WAME_FONT}" w:hAnsi="{WAME_FONT}" w:cs="{WAME_FONT}" w:hint="default"/><w:color w:val="{WAME_GREEN}"/></w:rPr>
    </w:lvl>
    <w:lvl w:ilvl="1">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="◦"/>
      <w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="1440" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>
'''


def _styles_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="{WAME_FONT}" w:hAnsi="{WAME_FONT}" w:cs="{WAME_FONT}"/>
        <w:sz w:val="22"/>
        <w:color w:val="{WAME_TEXT}"/>
        <w:lang w:val="sk-SK"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr><w:spacing w:after="120" w:line="288" w:lineRule="auto"/></w:pPr>
    </w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="0" w:after="240"/><w:jc w:val="left"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="56"/><w:color w:val="{WAME_NAVY}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle">
    <w:name w:val="Subtitle"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="0" w:after="240"/></w:pPr>
    <w:rPr><w:sz w:val="28"/><w:color w:val="{WAME_MUTED}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="Heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="360" w:after="160"/><w:keepNext/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/><w:color w:val="{WAME_NAVY}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="Heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="240" w:after="120"/><w:keepNext/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="{WAME_NAVY}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="Heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:before="200" w:after="80"/><w:keepNext/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="22"/><w:color w:val="{WAME_GREEN}"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListBullet">
    <w:name w:val="List Bullet"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="60"/><w:ind w:left="720" w:hanging="360"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Quote">
    <w:name w:val="Quote"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="160"/><w:ind w:left="480"/></w:pPr>
    <w:rPr><w:i/><w:color w:val="{WAME_MUTED}"/></w:rPr>
  </w:style>
</w:styles>
'''


def _header_xml(meta: Dict[str, Any]) -> str:
    title = _xml_escape(meta.get("title") or "")
    client = _xml_escape((meta.get("client") or {}).get("company") or "")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{W_NS}">
  <w:p>
    <w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{WAME_GREEN}"/></w:pBdr></w:pPr>
    <w:r><w:rPr><w:b/><w:color w:val="{WAME_NAVY}"/></w:rPr><w:t xml:space="preserve">WAME </w:t></w:r>
    <w:r><w:rPr><w:color w:val="{WAME_MUTED}"/></w:rPr><w:t xml:space="preserve">— Detailný návrh riešenia · {title}{' · ' + client if client else ''}</w:t></w:r>
  </w:p>
</w:hdr>
'''


def _footer_xml(meta: Dict[str, Any]) -> str:
    version = _xml_escape(meta.get("version") or "v1.0")
    date = _xml_escape(meta.get("date") or "")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{W_NS}">
  <w:p>
    <w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="1" w:color="{WAME_GREEN}"/></w:pBdr><w:jc w:val="center"/></w:pPr>
    <w:r><w:rPr><w:color w:val="{WAME_MUTED}"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">WAME s.r.o.  ·  wame.sk  ·  info@wame.sk  ·  {version}  ·  {date}</w:t></w:r>
  </w:p>
</w:ftr>
'''


def _core_xml(meta: Dict[str, Any]) -> str:
    title = _xml_escape(meta.get("title") or "DNR")
    client = _xml_escape((meta.get("client") or {}).get("company") or "")
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{title}</dc:title>
  <dc:creator>WAME s.r.o.</dc:creator>
  <dc:subject>Detailný návrh riešenia — {client}</dc:subject>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
'''


APP_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>WAME DNR Generator</Application>
  <Company>WAME s.r.o.</Company>
</Properties>
'''


# ---------- Section builders ----------

def _build_title_page(meta: Dict[str, Any]) -> str:
    client = meta.get("client") or {}
    title = meta.get("title") or "Detailný návrh riešenia"
    version = meta.get("version") or "v1.0"
    date = meta.get("date") or ""
    prepared = meta.get("prepared_by") or "WAME s.r.o."
    parts: List[str] = []
    parts.append(_para("WAME", bold=True, color=WAME_GREEN, size=14, font=WAME_FONT))
    parts.append(_para("Detailný návrh riešenia", style="Subtitle"))
    parts.append(_para(title, style="Title"))
    if client.get("company"):
        parts.append(_para(f"Klient: {client['company']}", size=13, color=WAME_NAVY, bold=True))
    if client.get("contact_name"):
        parts.append(_para(
            f"Kontakt: {client['contact_name']}"
            + (f" · {client.get('contact_email')}" if client.get("contact_email") else "")
            + (f" · {client.get('contact_phone')}" if client.get("contact_phone") else ""),
            color=WAME_MUTED,
        ))
    parts.append(_spacer())
    parts.append(_para(f"Dátum:    {date}", color=WAME_MUTED))
    parts.append(_para(f"Verzia:  {version}", color=WAME_MUTED))
    parts.append(_para(f"Vypracoval: {prepared}", color=WAME_MUTED))
    parts.append(_page_break())
    return "".join(parts)


def _page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _build_uvod(s: Dict[str, Any]) -> str:
    return _section_title("01", "Úvod a účel dokumentu") + _para(s.get("text", ""))


def _build_vychodiskovy(s: Dict[str, Any]) -> str:
    out = [_section_title("02", "Východiskový stav"), _para(s.get("text", ""))]
    co_zostava = s.get("co_zostava") or []
    if co_zostava:
        out.append(_heading("Čo zostáva v platnosti", level=2))
        out.extend(_bullet(x) for x in co_zostava)
    return "".join(out)


def _build_ciele(s: Dict[str, Any]) -> str:
    out = [_section_title("03", "Ciele projektu")]
    out.append(_heading("Biznis ciele", level=2))
    out.extend(_bullet(x) for x in s.get("biznis", []))
    out.append(_heading("Technické ciele", level=2))
    out.extend(_bullet(x) for x in s.get("technicke", []))
    out.append(_heading("Out of scope (v tejto fáze sa NEbude riešiť)", level=2))
    out.extend(_bullet(x) for x in s.get("out_of_scope", []))
    return "".join(out)


def _build_popis(s: Dict[str, Any]) -> str:
    out = [_section_title("04", "Popis riešenia a rozsah"), _para(s.get("uvod", ""))]
    for mod in s.get("moduly", []):
        out.append(_heading(mod.get("nazov", "Modul"), level=2))
        out.append(_para(mod.get("popis", "")))
        if mod.get("funkcie"):
            out.append(_heading("Kľúčové funkcie", level=3))
            out.extend(_bullet(x) for x in mod["funkcie"])
        if mod.get("priklady"):
            out.append(_heading("Príklady použitia", level=3))
            out.extend(_bullet(x) for x in mod["priklady"])
    if s.get("sitemap"):
        out.append(_heading("Sitemap", level=2))
        out.extend(_bullet(x) for x in s["sitemap"])
    if s.get("user_flows"):
        out.append(_heading("User flows", level=2))
        out.extend(_bullet(x) for x in s["user_flows"])
    return "".join(out)


def _build_roly(roly: List[Dict[str, Any]]) -> str:
    out = [_section_title("05", "Používateľské roly a prístupy")]
    rows = [["Rola", "Kto to je", "Čo vidí / čo môže robiť"]]
    for r in roly:
        rows.append([r.get("rola", ""), r.get("kto", ""), r.get("opravnenia", "")])
    out.append(_table(rows, col_widths=[2000, 2500, 4500]))
    return "".join(out)


def _build_technicke(s: Dict[str, Any]) -> str:
    out = [_section_title("06", "Technické riešenie")]
    plat = s.get("platforma", {})
    out.append(_heading("Platforma a technológie", level=2))
    rows = [["Vrstva", "Technológia"]]
    for label, key in (
        ("Backend", "backend"), ("Frontend", "frontend"), ("Databáza", "databaza"),
        ("Hosting", "hosting"), ("Mobilná aplikácia", "mobilna_app"),
    ):
        if plat.get(key):
            rows.append([label, plat[key]])
    if len(rows) > 1:
        out.append(_table(rows, col_widths=[3000, 6000]))
    if plat.get("zdovodnenie"):
        out.append(_heading("Zdôvodnenie volieb", level=3))
        out.append(_para(plat["zdovodnenie"]))

    if s.get("integracie"):
        out.append(_heading("Integrácie s externými systémami", level=2))
        rows = [["Systém", "Účel", "Smer dát", "Poznámka"]]
        for i in s["integracie"]:
            rows.append([
                i.get("system", ""), i.get("ucel", ""),
                i.get("smer_dat", ""), i.get("poznamka", ""),
            ])
        out.append(_table(rows, col_widths=[2200, 2700, 1700, 2400]))

    if s.get("bezpecnost"):
        out.append(_heading("Bezpečnosť", level=2))
        out.extend(_bullet(x) for x in s["bezpecnost"])
    return "".join(out)


def _build_gdpr(s: Dict[str, Any]) -> str:
    out = [_section_title("07", "GDPR a právne požiadavky"), _para(s.get("text", ""))]
    if s.get("osobne_udaje"):
        out.append(_heading("Zbierané osobné údaje", level=3))
        out.extend(_bullet(x) for x in s["osobne_udaje"])
    if s.get("doba_uchovavania"):
        out.append(_heading("Doba uchovávania", level=3))
        out.append(_para(s["doba_uchovavania"]))
    if s.get("cookies"):
        out.append(_heading("Cookies a súhlas", level=3))
        out.append(_para(s["cookies"]))
    return "".join(out)


def _build_podklady(items: List[Dict[str, Any]]) -> str:
    label_map = {"dodane": "✅ Dodané", "v_priprave": "⏳ V príprave", "chybajuce": "❌ Chýbajúce"}
    out = [_section_title("08", "Podklady od klienta")]
    rows = [["Podklad", "Formát", "Termín", "Stav"]]
    for p in items:
        rows.append([
            p.get("podklad", ""), p.get("format", ""),
            p.get("termin", ""), label_map.get(p.get("stav", ""), p.get("stav", "")),
        ])
    out.append(_table(rows, col_widths=[3200, 1800, 1800, 2200]))
    return "".join(out)


def _build_fazy(items: List[Dict[str, Any]]) -> str:
    out = [_section_title("09", "Fázy projektu a harmonogram")]
    rows = [["#", "Fáza", "Trvanie", "Platobný míľnik"]]
    for i, f in enumerate(items, 1):
        rows.append([
            str(i), f.get("nazov", ""), f.get("trvanie", ""),
            f.get("platobny_milnik", ""),
        ])
    out.append(_table(rows, col_widths=[500, 4000, 2000, 2500]))
    for i, f in enumerate(items, 1):
        out.append(_heading(f"Fáza {i} — {f.get('nazov', '')}", level=2))
        if f.get("popis"):
            out.append(_para(f["popis"]))
        if f.get("vystupy"):
            out.append(_heading("Výstupy", level=3))
            out.extend(_bullet(x) for x in f["vystupy"])
        zod = f.get("zodpovednost") or {}
        if zod.get("wame") or zod.get("klient"):
            out.append(_heading("Zodpovednosti", level=3))
            if zod.get("wame"):
                out.append(_para("WAME:", bold=True, color=WAME_NAVY))
                out.extend(_bullet(x) for x in zod["wame"])
            if zod.get("klient"):
                out.append(_para("Klient:", bold=True, color=WAME_NAVY))
                out.extend(_bullet(x) for x in zod["klient"])
    return "".join(out)


def _build_rizika(items: List[Dict[str, Any]]) -> str:
    out = [_section_title("10", "Riziká a ich riadenie")]
    rows = [["Riziko", "Dopad", "Pravdepodobnosť", "Prevencia / riešenie"]]
    for r in items:
        rows.append([
            r.get("riziko", ""), r.get("dopad", ""),
            r.get("pravdepodobnost", ""), r.get("prevencia", ""),
        ])
    out.append(_table(rows, col_widths=[3000, 1200, 1800, 3000]))
    return "".join(out)


def _build_podmienky(s: Dict[str, Any]) -> str:
    out = [_section_title("11", "Podmienky a záväzky")]
    out.append(_heading("WAME sa zaväzuje", level=2))
    out.extend(_bullet(x) for x in s.get("wame_zavazky", []))
    out.append(_heading("Klient sa zaväzuje", level=2))
    out.extend(_bullet(x) for x in s.get("klient_zavazky", []))
    if s.get("zmeny_scope"):
        out.append(_heading("Zmeny rozsahu", level=2))
        out.append(_para(s["zmeny_scope"]))
    else:
        out.append(_heading("Zmeny rozsahu", level=2))
        out.append(_para(
            "Akékoľvek zmeny nad rámec tohto DNR sa riešia formou písomného "
            "dodatku — zahŕňa aj odhad pracnosti a aktualizovaný harmonogram."
        ))
    return "".join(out)


def _build_volitelne(s: Dict[str, Any]) -> str:
    if not s:
        return ""
    out: List[str] = []
    section_id = ord("A")
    mapping = [
        ("wireframy", "Wireframy a UX flows"),
        ("datovy_model", "Dátový model"),
        ("seo", "SEO stratégia"),
        ("migracia", "Migrácia dát"),
        ("skolenie", "Školenie a odovzdanie"),
    ]
    for key, title in mapping:
        if s.get(key):
            out.append(_heading(f"{chr(section_id)} — {title}", level=1))
            out.append(_para(s[key]))
            section_id += 1
    return "".join(out)


def _build_schvalenie(s: Dict[str, Any]) -> str:
    out = [_section_title("12", "Schválenie dokumentu")]
    out.append(_para(f"Dátum: {s.get('datum', '')}"))
    rows = [
        ["Za klienta", "Za WAME"],
        [s.get("za_klienta") or "[Meno, funkcia]", s.get("za_wame") or "[Meno, funkcia]"],
        ["", ""],
        ["______________________", "______________________"],
        ["podpis", "podpis"],
    ]
    out.append(_table(rows, header=True, col_widths=[4500, 4500]))
    return "".join(out)


def build_document_xml(plan: Dict[str, Any]) -> str:
    meta = plan.get("meta", {})
    body_parts: List[str] = [_build_title_page(meta)]
    body_parts.append(_build_uvod(plan.get("uvod", {})))
    body_parts.append(_build_vychodiskovy(plan.get("vychodiskovy_stav", {})))
    body_parts.append(_build_ciele(plan.get("ciele", {})))
    body_parts.append(_build_popis(plan.get("popis_riesenia", {})))
    body_parts.append(_build_roly(plan.get("pouzivatelske_roly", [])))
    body_parts.append(_build_technicke(plan.get("technicke_riesenie", {})))
    body_parts.append(_build_gdpr(plan.get("gdpr", {})))
    body_parts.append(_build_podklady(plan.get("podklady_klienta", [])))
    body_parts.append(_build_fazy(plan.get("fazy", [])))
    body_parts.append(_build_rizika(plan.get("rizika", [])))
    body_parts.append(_build_podmienky(plan.get("podmienky", {})))
    body_parts.append(_build_volitelne(plan.get("volitelne", {}) or {}))
    body_parts.append(_build_schvalenie(plan.get("schvalenie", {})))

    section_props = (
        '<w:sectPr>'
        '<w:headerReference w:type="default" r:id="rId4"/>'
        '<w:footerReference w:type="default" r:id="rId5"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1200" w:bottom="1440" w:left="1200" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="708"/><w:docGrid w:linePitch="360"/>'
        '</w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        f"<w:body>{''.join(body_parts)}{section_props}</w:body>"
        '</w:document>'
    )


def write_docx(plan: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document_xml = build_document_xml(plan)
    meta = plan.get("meta", {})
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", ROOT_RELS)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", DOC_RELS)
        zf.writestr("word/styles.xml", _styles_xml())
        zf.writestr("word/numbering.xml", NUMBERING_XML)
        zf.writestr("word/settings.xml", SETTINGS_XML)
        zf.writestr("word/header1.xml", _header_xml(meta))
        zf.writestr("word/footer1.xml", _footer_xml(meta))
        zf.writestr("docProps/core.xml", _core_xml(meta))
        zf.writestr("docProps/app.xml", APP_XML)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _project_hash(cwd: Path) -> str:
    import hashlib
    return hashlib.sha1(str(cwd).encode("utf-8")).hexdigest()[:12]


def init_config(cwd: Path) -> Path:
    target_dir = Path.home() / ".claude" / "plugins" / "data" / "dnr-business-wamesk" / _project_hash(cwd)
    target_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = target_dir / "config.json"
    if not cfg_file.exists():
        cfg_file.write_text(
            json.dumps({
                "output_dir": "docs",
                "language": "auto",
                "default_version": "v1.0",
                "client": {
                    "company": "",
                    "contact_name": "",
                    "contact_email": "",
                    "contact_phone": ""
                }
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return cfg_file


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="WAME DNR generator")
    parser.add_argument("--read-inputs", action="store_true")
    parser.add_argument("--paths", nargs="*", default=[])
    parser.add_argument("--scan-repo", action="store_true")
    parser.add_argument("--root", default=".")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--output", dest="output_path")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--pretty", action="store_true")

    args = parser.parse_args(argv)

    if args.init:
        cfg = init_config(Path.cwd())
        print(json.dumps({"config_path": str(cfg)}, indent=2, ensure_ascii=False))
        return 0

    if args.read_inputs:
        result = read_inputs(args.paths)
        print(json.dumps({"inputs": result}, indent=2 if args.pretty else None, ensure_ascii=False))
        return 0

    if args.scan_repo:
        result = scan_repo(Path(args.root).resolve())
        print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False))
        return 0

    if args.validate:
        if not args.json_path:
            print("--json <path> required", file=sys.stderr)
            return 2
        plan = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
        errors = validate_plan(plan)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2, ensure_ascii=False))
        return 0 if not errors else 1

    if args.build:
        if not args.json_path or not args.output_path:
            print("--json and --output required", file=sys.stderr)
            return 2
        plan = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
        errors = validate_plan(plan)
        if errors:
            print(json.dumps({"ok": False, "errors": errors}, indent=2, ensure_ascii=False),
                  file=sys.stderr)
            return 1
        out = Path(args.output_path).expanduser().resolve()
        write_docx(plan, out)
        print(json.dumps({"ok": True, "output": str(out)}, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
