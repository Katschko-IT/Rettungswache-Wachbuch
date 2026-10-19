"""Katalogwerkzeug fuer das Wachbuch: Strings extrahieren und .mo kompilieren.

Hintergrund: Im Auslieferungscontainer stehen weder ``xgettext`` noch
``msgfmt`` (GNU gettext) zur Verfuegung. ``django-admin makemessages`` und
``compilemessages`` scheitern dort. Dieses Skript ersetzt beide Schritte
reproduzierbar mit der Standardbibliothek:

* ``extract``  sammelt alle markierten Strings aus Python-, Template- und
  JavaScript-Dateien und schreibt/aktualisiert ``.po``-Dateien. Bereits
  vorhandene Uebersetzungen bleiben erhalten.
* ``compile``  prueft die Kataloge (Platzhalter, Pluralformen, fehlende
  Uebersetzungen) und schreibt GNU-kompatible ``.mo``-Dateien.
* ``check``    prueft nur, ohne zu schreiben; vergleicht zusaetzlich die
  eingecheckten ``.mo``-Dateien mit den ``.po``-Quellen.

Wichtig fuer ``{% blocktranslate %}``: Django ersetzt ``{{ variable }}`` zur
Laufzeit durch ``%(variable)s``. Der Katalog muss daher genau diese Form
enthalten, sonst findet die Uebersetzung nie statt (stille Mischsprache).

Die .mo-Dateien werden von ``gettext.GNUTranslations`` gelesen; die
Django-Tests laden sie ueber den echten Uebersetzungsstapel. Beim Build
wird kein GNU-gettext benoetigt, weil die .mo-Dateien eingecheckt sind.
Ist ``msgfmt`` vorhanden, prueft der Test ``core.test_i18n_catalog``
zusaetzlich die GNU-Kompatibilitaet der erzeugten Datei.

Aufruf:
    python scripts/i18n_catalog.py extract
    python scripts/i18n_catalog.py compile
    python scripts/i18n_catalog.py check
"""

from __future__ import annotations

import argparse
import ast
import gettext
import re
import struct
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / "locale"
SOURCE_DIRS = ("core", "config", "templates")
SKIP_PARTS = {"__pycache__", "migrations", "staticfiles", "node_modules", ".venv"}
LANGUAGES = ("de", "en")
DOMAIN = "django"

PLACEHOLDER_RE = re.compile(
    r"%(?:\((?P<name>[^)]+)\)[sdfr]|(?P<plain>[sdfr]))"
    r"|(?<!\{)\{(?P<brace>[A-Za-z_][A-Za-z0-9_]*)\}(?!\})"
)

# Fuer {% blocktranslate %}: Django rendert {{ var }} zu %(var)s.
BLOCK_VAR_RE = re.compile(r"{{\s*(?P<expr>[^{}]+?)\s*}}")
PLAIN_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

TEMPLATE_TRANS_RE = re.compile(
    r"{%\s*(?:translate|trans)\s+(?P<q>[\"'])(?P<text>.*?)(?P=q)"
    r"(?:\s+context\s+(?P<cq>[\"'])(?P<context>.*?)(?P=cq))?\s*[^%]*%}"
)
TEMPLATE_BLOCK_RE = re.compile(
    r"{%\s*blocktranslate(?P<opts>[^%]*)%}(?P<body>.*?){%\s*endblocktranslate\s*%}"
    r"|{%\s*blocktrans(?P<opts2>[^%]*)%}(?P<body2>.*?){%\s*endblocktrans\s*%}",
    re.DOTALL,
)
TEMPLATE_PLURAL_RE = re.compile(
    r"{%\s*plural\s*%}(?P<plural>.*)$", re.DOTALL
)

JS_TRANS_RE = re.compile(r"gettext\(\s*(?P<q>[\"'])(?P<text>.*?)(?P=q)")


class CatalogError(RuntimeError):
    """Struktureller Katalogfehler (kein stilles Ueberspringen)."""


def iter_source_files():
    for directory in SOURCE_DIRS:
        root = BASE_DIR / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix not in {".py", ".html", ".js"}:
                continue
            yield path


GETTEXT_CALLS = {
    "gettext": (0, None),
    "_": (0, None),
    "gettext_lazy": (0, None),
    "ngettext": (0, 1),
    "ngettext_lazy": (0, 1),
    "pgettext": (1, None),
    "pgettext_lazy": (1, None),
    "npgettext": (1, 2),
    "npgettext_lazy": (1, 2),
}


def _const_str(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_python(path: Path, text: str):
    """Liefert (msgctxt, msgid, msgid_plural, lineno)-Tupel aus gettext-Aufrufen."""
    results = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise CatalogError(f"{path}: Syntaxfehler: {exc}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name not in GETTEXT_CALLS:
            continue
        id_index, plural_index = GETTEXT_CALLS[name]
        if len(node.args) <= id_index:
            continue
        msgid = _const_str(node.args[id_index])
        if msgid is None:
            continue
        context = None
        if id_index == 1:
            context = _const_str(node.args[0])
            if context is None:
                continue
        plural = None
        if plural_index is not None and len(node.args) > plural_index:
            plural = _const_str(node.args[plural_index])
        results.append((context, msgid, plural, getattr(node, "lineno", 0)))
    return results


def blocktranslate_msgid(body: str) -> str:
    """Bildet den Laufzeit-msgid eines blocktranslate-Blocks.

    Django ersetzt jede Variable durch ``%(name)s`` und verdoppelt literale
    Prozentzeichen. Whitespace bleibt erhalten, weil ``render_token_list``
    die Textknoten unveraendert zusammenfuegt.
    """
    escaped = body.replace("%", "%%")

    def replace(match: re.Match) -> str:
        expression = match.group("expr").split("|")[0].strip()
        if PLAIN_VAR_RE.match(expression):
            name = expression
        else:
            name = re.sub(r"\W", "_", expression).strip("_") or "value"
        return f"%({name})s"

    return BLOCK_VAR_RE.sub(replace, escaped)


def extract_template(path: Path, text: str):
    results = []
    for match in TEMPLATE_TRANS_RE.finditer(text):
        results.append(
            (
                match.group("context"),
                match.group("text"),
                None,
                text.count("\n", 0, match.start()) + 1,
            )
        )
    for match in TEMPLATE_BLOCK_RE.finditer(text):
        body = match.group("body") or match.group("body2") or ""
        line = text.count("\n", 0, match.start()) + 1
        plural_match = TEMPLATE_PLURAL_RE.search(body)
        if plural_match:
            singular = body[: plural_match.start()]
            plural = plural_match.group("plural")
        else:
            singular, plural = body, None
        results.append(
            (
                None,
                blocktranslate_msgid(singular),
                blocktranslate_msgid(plural) if plural is not None else None,
                line,
            )
        )
    return results


def extract_js(path: Path, text: str):
    return [
        (None, match.group("text"), None, text.count("\n", 0, match.start()) + 1)
        for match in JS_TRANS_RE.finditer(text)
    ]


def collect():
    """Sammelt (msgctxt, msgid, msgid_plural) -> Liste von Fundstellen."""
    found: dict[tuple, list[str]] = {}
    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            entries = extract_python(path, text)
        elif path.suffix == ".html":
            entries = extract_template(path, text)
        else:
            entries = extract_js(path, text)
        relative = path.relative_to(BASE_DIR).as_posix()
        for context, msgid, plural, line in entries:
            found.setdefault((context, msgid, plural), []).append(f"{relative}:{line}")
    return found


def po_header(language: str) -> str:
    team = {"de": "German", "en": "English"}.get(language, language)
    return (
        "Project-Id-Version: Wachbuch\n"
        "Report-Msgid-Bugs-To: \n"
        "POT-Creation-Date: 2026-10-19 00:00+0000\n"
        "PO-Revision-Date: 2026-10-19 00:00+0000\n"
        "Last-Translator: Wachbuch Team\n"
        f"Language-Team: {team}\n"
        f"Language: {language}\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        "Plural-Forms: nplurals=2; plural=(n != 1);\n"
    )


def _blank() -> dict:
    return {
        "refs": [],
        "fuzzy": False,
        "msgctxt": None,
        "msgid": "",
        "plural": None,
        "msgstr": "",
        "msgstr_plural": {},
    }


def parse_po(path: Path):
    """Minimaler, aber korrekter PO-Parser (msgctxt/msgid_plural/msgstr[n]/fuzzy).

    Kommentare gelten fuer den *folgenden* Eintrag. Ein ``#, fuzzy`` nach dem
    letzten msgstr darf also nicht rueckwirkend den vorherigen Eintrag markieren.
    """
    entries: list[dict] = []
    current = _blank()
    active: str | None = None
    started = False

    def flush() -> None:
        nonlocal current, active, started
        if started:
            entries.append(current)
        current = _blank()
        active = None
        started = False

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if started:
                flush()
            if line.startswith("#,") and "fuzzy" in line:
                current["fuzzy"] = True
            elif line.startswith("#:"):
                current["refs"].append(line[2:].strip())
            continue
        if line.startswith("msgctxt "):
            if started:
                flush()
            current["msgctxt"] = _unquote(line[len("msgctxt ") :])
            active = "msgctxt"
            started = True
            continue
        if line.startswith("msgid_plural "):
            current["plural"] = _unquote(line[len("msgid_plural ") :])
            active = "msgid_plural"
            started = True
            continue
        if line.startswith("msgid "):
            if started and (active not in {None, "msgctxt"} or current["msgstr"] or current["msgstr_plural"]):
                flush()
            current["msgid"] = _unquote(line[len("msgid ") :])
            active = "msgid"
            started = True
            continue
        if line.startswith("msgstr["):
            index = int(line[line.index("[") + 1 : line.index("]")])
            current["msgstr_plural"][index] = _unquote(line.split(" ", 1)[1])
            active = f"msgstr[{index}]"
            started = True
            continue
        if line.startswith("msgstr "):
            current["msgstr"] = _unquote(line[len("msgstr ") :])
            active = "msgstr"
            started = True
            continue
        if line.startswith('"') and started:
            value = _unquote(line)
            if active in {"msgid", None}:
                current["msgid"] += value
            elif active == "msgctxt":
                current["msgctxt"] = (current["msgctxt"] or "") + value
            elif active == "msgid_plural":
                current["plural"] = (current["plural"] or "") + value
            elif active == "msgstr":
                current["msgstr"] += value
            elif active and active.startswith("msgstr["):
                index = int(active[len("msgstr[") : -1])
                current["msgstr_plural"][index] = (
                    current["msgstr_plural"].get(index, "") + value
                )
            continue
    flush()
    return entries


_UNESCAPE = {
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
}


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        inner = token[1:-1]
        out = []
        index = 0
        while index < len(inner):
            char = inner[index]
            if char == "\\" and index + 1 < len(inner):
                nxt = inner[index + 1]
                out.append(_UNESCAPE.get(nxt, "\\" + nxt))
                index += 2
                continue
            out.append(char)
            index += 1
        return "".join(out)
    return token


def _quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def placeholders(text: str) -> list[str]:
    names = []
    for match in PLACEHOLDER_RE.finditer(text):
        if match.group("name"):
            names.append("%(" + match.group("name") + ")s")
        elif match.group("plain"):
            names.append("%" + match.group("plain"))
        else:
            names.append("{" + match.group("brace") + "}")
    return sorted(names)


def entry_key(entry: dict) -> tuple:
    return (entry.get("msgctxt"), entry["msgid"], entry.get("plural"))


def validate(entries, path: Path, *, language: str):
    problems: list[str] = []
    header = next((entry for entry in entries if entry["msgid"] == ""), None)
    if header is None:
        problems.append(f'{path}: Kopfzeile (msgid "") fehlt')
        nplurals = 2
    else:
        match = re.search(r"nplurals\s*=\s*(\d+)", header["msgstr"])
        nplurals = int(match.group(1)) if match else 2
        if "charset=UTF-8" not in header["msgstr"]:
            problems.append(f"{path}: Kopfzeile ohne charset=UTF-8")
        if f"Language: {language}" not in header["msgstr"]:
            problems.append(f"{path}: Kopfzeile nennt nicht Language: {language}")
    seen = set()
    for entry in entries:
        if entry["msgid"] == "":
            continue
        msgid = entry["msgid"]
        key = entry_key(entry)
        if key in seen:
            problems.append(f"{path}: doppelter Eintrag: {msgid[:60]}")
        seen.add(key)
        if entry["fuzzy"]:
            problems.append(f"{path}: fuzzy-Eintrag: {msgid[:60]}")
            continue
        if entry["plural"] is not None:
            missing = [
                index
                for index in range(nplurals)
                if not entry["msgstr_plural"].get(index)
            ]
            if missing:
                problems.append(f"{path}: Pluralform fehlt ({missing}) bei: {msgid[:60]}")
                continue
            expected = placeholders(msgid)
            for index in range(nplurals):
                source = msgid if index == 0 else entry["plural"]
                if placeholders(source) != placeholders(entry["msgstr_plural"][index]):
                    problems.append(
                        f"{path}: Platzhalter im Plural [{index}] weichen ab: {msgid[:50]}"
                    )
            if expected != placeholders(entry["plural"]):
                problems.append(f"{path}: Platzhalter im msgid_plural weichen ab: {msgid[:50]}")
        else:
            if not entry["msgstr"].strip():
                problems.append(f"{path}: Uebersetzung fehlt ({language}): {msgid[:60]}")
            elif placeholders(msgid) != placeholders(entry["msgstr"]):
                problems.append(
                    f"{path}: Platzhalter weichen ab bei {msgid[:50]!r}: "
                    f"{placeholders(msgid)} != {placeholders(entry['msgstr'])}"
                )
    return problems


def mo_key(entry: dict) -> str:
    """GNU-.mo-Schluessel: Kontext, dann msgid, bei Plural '\\x00'+msgid_plural."""
    key = entry["msgid"]
    if entry.get("msgctxt"):
        key = entry["msgctxt"] + "\x04" + key
    if entry["plural"] is not None:
        key = key + "\x00" + entry["plural"]
    return key


def write_mo(entries, target: Path) -> int:
    """Schreibt eine GNU-.mo-Datei (little endian) und liefert die Anzahl."""
    usable = [entry for entry in entries if not entry["fuzzy"]]
    usable.sort(key=lambda entry: mo_key(entry).encode("utf-8"))
    offsets = []
    ids = b""
    strs = b""
    for entry in usable:
        key = mo_key(entry)
        if entry["plural"] is not None:
            plurals = entry["msgstr_plural"]
            value = "\x00".join(plurals[index] for index in sorted(plurals))
        else:
            value = entry["msgstr"]
        key_bytes = key.encode("utf-8")
        value_bytes = value.encode("utf-8")
        offsets.append((len(ids), len(key_bytes), len(strs), len(value_bytes)))
        ids += key_bytes + b"\x00"
        strs += value_bytes + b"\x00"
    count = len(offsets)
    keys_start = 7 * 4 + count * 8 * 2
    values_start = keys_start + len(ids)
    key_table = b""
    value_table = b""
    for id_offset, id_length, str_offset, str_length in offsets:
        key_table += struct.pack("<II", id_length, keys_start + id_offset)
        value_table += struct.pack("<II", str_length, values_start + str_offset)
    payload = b"".join(
        [
            struct.pack("<I", 0x950412DE),
            struct.pack("<I", 0),
            struct.pack("<I", count),
            struct.pack("<I", 7 * 4),
            struct.pack("<I", 7 * 4 + count * 8),
            struct.pack("<I", 0),
            struct.pack("<I", 0),
            key_table,
            value_table,
            ids,
            strs,
        ]
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return count


def merge_po(path: Path, language: str, found: dict[tuple, list[str]]) -> tuple[int, int]:
    """Aktualisiert eine .po-Datei und behaelt bestehende Uebersetzungen.

    Schluessel ist (msgctxt, msgid, msgid_plural), damit Kontext- und
    Plural-Eintraege nicht verloren gehen oder kollidieren.
    """
    existing: dict[tuple, dict] = {}
    if path.exists():
        for entry in parse_po(path):
            if entry["msgid"]:
                existing[entry_key(entry)] = entry
    lines = [
        f"# Katalog fuer Sprache {language} - erzeugt von scripts/i18n_catalog.py.",
        "# Quellsprache ist Deutsch; msgid ist der sichtbare deutsche Text.",
        'msgid ""',
        f"msgstr {_quote(po_header(language))}",
        "",
    ]
    kept = 0
    for key in sorted(found, key=lambda item: ((item[0] or "") + "\x04" + item[1])):
        context, msgid, plural = key
        entry = existing.get(key)
        if entry and (
            entry["msgstr"].strip() or any(value.strip() for value in entry["msgstr_plural"].values())
        ):
            kept += 1
            msgstr = entry["msgstr"]
            msgstr_plural = dict(entry["msgstr_plural"])
        elif language == "de":
            msgstr = msgid
            msgstr_plural = {0: msgid, 1: plural} if plural else {}
        else:
            msgstr = ""
            msgstr_plural = {}
        for ref in found[key]:
            lines.append(f"#: {ref}")
        if entry and entry["fuzzy"]:
            lines.append("#, fuzzy")
        if context:
            lines.append(f"msgctxt {_quote(context)}")
        lines.append(f"msgid {_quote(msgid)}")
        if plural:
            lines.append(f"msgid_plural {_quote(plural)}")
            for index in sorted(msgstr_plural):
                lines.append(f"msgstr[{index}] {_quote(msgstr_plural[index])}")
            if not msgstr_plural:
                lines.append('msgstr[0] ""')
                lines.append('msgstr[1] ""')
        else:
            lines.append(f"msgstr {_quote(msgstr)}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(found), kept


def catalogs():
    for language in LANGUAGES:
        yield LOCALE_DIR / language / "LC_MESSAGES" / f"{DOMAIN}.po", language


def compile_catalog(po: Path, language: str) -> tuple[list[str], int]:
    entries = parse_po(po)
    problems = validate(entries, po, language=language)
    target = po.with_suffix(".mo")
    count = write_mo(entries, target)
    return problems, count


def cmd_extract() -> int:
    found = collect()
    files = len(list(iter_source_files()))
    print(f"{len(found)} eindeutige Strings in {files} Dateien gefunden.")
    for po, language in catalogs():
        total, kept = merge_po(po, language, found)
        print(
            f"{po.relative_to(BASE_DIR)}: {total} Eintraege, "
            f"{kept} bestehende Uebersetzungen behalten."
        )
    return 0


def cmd_compile() -> int:
    problems: list[str] = []
    for po, language in catalogs():
        catalog_problems, count = compile_catalog(po, language)
        problems.extend(catalog_problems)
        print(f"{po.with_suffix('.mo').relative_to(BASE_DIR)}: {count} Eintraege kompiliert.")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    return 0


def mo_catalog(path: Path) -> dict:
    """Liest eine .mo ueber den stdlib-GNU-Parser (kein eigener Parser)."""
    with path.open("rb") as handle:
        return dict(gettext.GNUTranslations(handle)._catalog.items())


def expected_mo_catalog(entries) -> dict:
    expected: dict = {}
    for entry in entries:
        if entry["fuzzy"]:
            continue
        key = mo_key(entry)
        if entry["plural"] is not None:
            # GNUTranslations splittet den msgid am NUL-Byte und legt die
            # Pluralformen unter (msgid, index) ab (siehe _parse).
            base = key.split("\x00", 1)[0]
            for index in sorted(entry["msgstr_plural"]):
                expected[(base, index)] = entry["msgstr_plural"][index]
        else:
            expected[key] = entry["msgstr"]
    return expected


def cmd_check() -> int:
    problems: list[str] = []
    found = collect()
    for po, language in catalogs():
        entries = parse_po(po)
        problems.extend(validate(entries, po, language=language))
        known = {entry_key(entry) for entry in entries if entry["msgid"]}
        missing = sorted(set(found) - known, key=str)
        if missing:
            problems.append(
                f"{po}: {len(missing)} markierte Strings fehlen im Katalog, "
                f"z.B. {missing[0][1][:60]!r}"
            )
        mo = po.with_suffix(".mo")
        if not mo.is_file():
            problems.append(f"{mo}: eingecheckte .mo fehlt")
            continue
        try:
            actual = mo_catalog(mo)
        except (OSError, ValueError) as exc:
            problems.append(f"{mo}: nicht lesbar ({exc})")
            continue
        expected = expected_mo_catalog(entries)
        if actual != expected:
            only_mo = sorted(set(actual) - set(expected))[:3]
            only_po = sorted(set(expected) - set(actual))[:3]
            changed = sorted(
                key
                for key in set(actual) & set(expected)
                if actual[key] != expected[key]
            )[:3]
            problems.append(
                f"{mo}: veraltet gegenueber .po "
                f"(nur .mo: {only_mo}, nur .po: {only_po}, abweichend: {changed})"
            )
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("Kataloge vollstaendig und konsistent; eingecheckte .mo sind aktuell.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=("extract", "compile", "check"))
    args = parser.parse_args(argv)
    if args.command == "extract":
        return cmd_extract()
    if args.command == "compile":
        return cmd_compile()
    return cmd_check()


if __name__ == "__main__":
    raise SystemExit(main())
