"""Livara Studio: bounded, local utilities with no network requests or shell eval.

Private notes and focus records are permission-protected, not encrypted. File
utilities are read-only and never follow symbolic links inside scanned folders.
"""

from __future__ import annotations

import ast
import base64
import binascii
import colorsys
import csv
import difflib
import hashlib
import html
import io
import ipaddress
import json
import math
import mimetypes
import operator
import os
import re
import secrets
import stat
import string
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote_to_bytes, urlsplit

MAX_TEXT = 1024 * 1024
MAX_FILES = 5000
MAX_SCAN_BYTES = 256 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024


def _tool(identifier, name, category, hint, sample="", option_label="", option_default="", input_kind="text"):
    return {"id": identifier, "name": name, "category": category, "hint": hint,
            "sample": sample, "option_label": option_label,
            "option_default": option_default, "input_kind": input_kind}


TOOLS = (
    _tool("unicode", "Unicode lens", "Text", "Count text and inspect Unicode code points, names, and categories.", "Hello, Livara 👋"),
    _tool("cleanup", "Line workshop", "Text", "Clean a list without changing the original file. Modes run in the entered order.", "  aurora\nprism\naurora\n\n", "Modes: trim, nonempty, deduplicate, sort", "trim,nonempty,deduplicate"),
    _tool("diff", "Text comparison", "Text", "Compare two texts with a unified line diff.", "First line\nOriginal line\n", "Second text", "First line\nUpdated line\n"),
    _tool("html", "HTML entity desk", "Text", "Encode text for HTML, or decode character entities. This does not sanitize HTML.", '<a title="Livara">', "Mode: encode or decode", "encode"),
    _tool("base64", "Base64 desk", "Text", "Encode UTF-8 text or decode strictly validated Base64 back to UTF-8.", "Hello from Livara", "Mode: encode or decode", "encode"),
    _tool("urlencode", "URL component encoder", "Text", "Percent-encode a single URL component, or decode percent escapes as UTF-8.", "Livara research / notes", "Mode: encode or decode", "encode"),
    _tool("textcase", "Case & naming", "Text", "Change case or turn a phrase into a Unicode-aware snake_case or kebab-case name.", "Build Something Beautiful", "Mode: upper, lower, title, casefold, snake, or kebab", "snake"),
    _tool("hex", "UTF-8 hex desk", "Text", "View the exact UTF-8 bytes of text, or strictly decode hexadecimal bytes back to UTF-8.", "Livara ✨", "Mode: encode or decode", "encode"),
    _tool("markdown", "Markdown outline", "Text", "Extract a lightweight heading/link outline or readable plain text. This is not a complete Markdown renderer.", "# A little possibility\n\n## Next steps\nWrite **one good idea**.\n\n[Livara](https://livara.org)\n", "Mode: outline or plain", "outline"),
    _tool("json", "JSON formatter", "Data", "Validate strict JSON, sort keys, and format it with your chosen indentation.", '{"workspace":"Livara","ready":true}', "Indentation: 0–8", "2"),
    _tool("jsonpath", "JSON path lens", "Data", "Extract one JSON value with a dotted/index path or a JSON Pointer; no expressions are executed.", '{"workspace":{"name":"Livara"},"items":[{"ready":true}]}', "Path, e.g. workspace.name, items[0].ready, or /workspace/name", "workspace.name"),
    _tool("csv", "CSV ↔ JSON table", "Data", "Convert a CSV table with a header to JSON, or a JSON array of objects to CSV.", "name,role\nLivara,workbench\n", "Mode: to-json or from-json", "to-json"),
    _tool("toml", "TOML inspector", "Data", "Validate TOML and display its parsed structure as JSON.", '[workspace]\nname = "Livara"\n'),
    _tool("jwt", "JWT reader", "Data", "Decode a token's header and payload locally. Signatures are NOT verified.", "", "", ""),
    _tool("regex", "Pattern lab", "Data", "Find matches with a 1-second process deadline and bounded inputs. Multiline mode is enabled.", "Livara 2026\nCase 42", "Regular expression", r"\d+"),
    _tool("password", "Password forge", "Create", "Generate a random password with Python's cryptographic secrets source.", "24", "Alphabet: all, letters, or alphanumeric", "all"),
    _tool("uuid", "Identity seeds", "Create", "Create random UUID version 4 identifiers. These are not passwords.", "5"),
    _tool("digest", "Text fingerprint", "Create", "Hash exact UTF-8 text locally with SHA-256, SHA-512, or BLAKE2b. This does not authenticate the text's origin.", "A good idea starts here.", "Algorithm: sha256, sha512, or blake2b", "sha256"),
    _tool("calculator", "Safe calculator", "Create", "Arithmetic, pi/e/tau, and abs, round, sqrt, sin, cos, tan, log, log10, floor, ceil. No Python evaluation.", "sqrt(144) + 2**8"),
    _tool("units", "Unit bridge", "Create", "Convert length, temperature, or binary storage units.", "100", "Conversion, e.g. km -> mi, C -> F, GiB -> MiB", "km -> mi"),
    _tool("time", "Time bridge", "Create", "Convert Unix seconds or an ISO 8601 date/time. An omitted timezone means UTC.", "2026-01-01T12:00:00+00:00"),
    _tool("subnet", "Subnet notebook", "Network", "Calculate a CIDR network locally. No network scan or connection is made.", "192.168.10.15/24"),
    _tool("urlparts", "URL anatomy", "Network", "Inspect URL parts, Unicode hostnames, and query fields without opening a connection.", "https://chat.livara.org/research?topic=linux&view=glass"),
    _tool("idna", "Domain alphabet", "Network", "Show a domain in Unicode and ASCII IDNA form without a DNS request.", "münich.example"),
    _tool("color", "Color prism", "Design", "Convert #RGB, #RRGGBB, or rgb(r,g,b) to RGB, HSL, HSV, and relative luminance.", "#c5a3ff"),
    _tool("contrast", "Contrast lens", "Design", "Calculate WCAG contrast for two opaque sRGB colors.", "#c5a3ff #11223e"),
    _tool("fileinfo", "File passport", "Files", "Read size, guessed MIME type, permissions, and filesystem timestamps. No file is changed.", "", input_kind="file"),
    _tool("inventory", "Folder map", "Files", "Summarize a directory and its largest files. Scans at most 5,000 regular files; symlinks are skipped.", "", input_kind="directory"),
    _tool("duplicates", "Duplicate finder", "Files", "Find equal-size files with equal SHA-256 content hashes. Read-only, up to 5,000 files and 256 MiB hashed.", "", input_kind="directory"),
    _tool("logtail", "Log window", "Files", "Read the last lines of a text file, bounded to its last 1 MiB.", "", "Lines: 1–2000", "100", "file"),
)


def search_tools(query="", category="All", favorite_ids=None):
    """Filter the actual catalog; all search words must occur in its metadata."""
    if not isinstance(query, str) or not isinstance(category, str):
        raise ValueError("Search and category must be text")
    if len(query) > 256:
        raise ValueError("Search is limited to 256 characters")
    categories = {tool["category"] for tool in TOOLS}
    if category not in categories | {"All", "Favorites"}:
        raise ValueError("Unknown Studio category")
    favorites = set(favorite_ids or ())
    words = unicodedata.normalize("NFC", query).casefold().split()
    result = []
    for tool in TOOLS:
        if category == "Favorites" and tool["id"] not in favorites:
            continue
        if category not in ("All", "Favorites") and tool["category"] != category:
            continue
        haystack = unicodedata.normalize("NFC", " ".join(str(tool.get(key, "")) for key in ("id", "name", "category", "hint"))).casefold()
        if all(word in haystack for word in words):
            result.append(tool)
    return result


def _json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, default=lambda x: x.isoformat())


def _strict_json(text):
    def invalid(value):
        raise ValueError(f"Non-JSON numeric constant: {value}")
    return json.loads(text, parse_constant=invalid)


def _integer(value, minimum, maximum, name):
    try:
        number = int(str(value).strip())
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def unicode_report(text):
    points = []
    for character in dict.fromkeys(text):
        if len(points) == 128:
            break
        points.append({"character": character, "code_point": f"U+{ord(character):04X}",
                       "name": unicodedata.name(character, "UNNAMED"),
                       "category": unicodedata.category(character)})
    return _json({"code_points": len(text), "utf8_bytes": len(text.encode("utf-8")),
                  "words": len(text.split()), "lines": len(text.splitlines()),
                  "unique_code_points": len(set(text)), "normalized_nfc": unicodedata.is_normalized("NFC", text),
                  "first_128_unique_characters": points})


def clean_lines(text, modes):
    lines = text.splitlines()
    for mode in (value.strip() for value in modes.split(",")):
        if mode == "trim":
            lines = [line.strip() for line in lines]
        elif mode == "nonempty":
            lines = [line for line in lines if line]
        elif mode == "deduplicate":
            lines = list(dict.fromkeys(lines))
        elif mode == "sort":
            lines = sorted(lines, key=str.casefold)
        else:
            raise ValueError("Choose trim, nonempty, deduplicate, and/or sort")
    return "\n".join(lines)


def _encode_decode(kind, text, mode):
    if mode not in ("encode", "decode"):
        raise ValueError("Mode must be encode or decode")
    if kind == "html":
        return html.escape(text, quote=True) if mode == "encode" else html.unescape(text)
    if kind == "base64":
        return base64.b64encode(text.encode()).decode("ascii") if mode == "encode" else base64.b64decode("".join(text.split()), validate=True).decode("utf-8")
    if mode == "encode":
        return quote(text, safe="")
    if re.search(r"%(?![0-9a-fA-F]{2})", text):
        raise ValueError("Invalid URL percent escape")
    return unquote_to_bytes(text).decode("utf-8")


def text_case(text, mode):
    if mode in ("upper", "lower", "title", "casefold"):
        return getattr(text, mode)()
    if mode not in ("snake", "kebab"):
        raise ValueError("Choose upper, lower, title, casefold, snake, or kebab")
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[^\W_]+", separated, flags=re.UNICODE)
    return ("_" if mode == "snake" else "-").join(word.casefold() for word in words)


def utf8_hex(text, mode):
    if mode == "encode":
        return " ".join(f"{value:02x}" for value in text.encode("utf-8"))
    if mode != "decode":
        raise ValueError("Mode must be encode or decode")
    try:
        return bytes.fromhex(text).decode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise ValueError("Use complete hexadecimal byte pairs encoding valid UTF-8") from error


def text_fingerprint(text, algorithm):
    if algorithm not in ("sha256", "sha512", "blake2b"):
        raise ValueError("Choose sha256, sha512, or blake2b")
    original = text.encode("utf-8")
    return _json({"algorithm": algorithm, "utf8_bytes": len(original),
                  "hex": hashlib.new(algorithm, original).hexdigest()})


def json_path(text, expression):
    """Read object/list values without evaluating JavaScript or Python syntax."""
    value = _strict_json(text)
    if not expression or expression == "$":
        return _json(value)
    if len(expression) > 512:
        raise ValueError("JSON paths are limited to 512 characters")
    if expression.startswith("/"):
        if re.search(r"~(?![01])", expression):
            raise ValueError("JSON Pointer escapes must be ~0 or ~1")
        fields = [part.replace("~1", "/").replace("~0", "~") for part in expression[1:].split("/")]
    else:
        fields, position = [], 0
        field_pattern = re.compile(r"(?:[^\W\d]|_)[\w-]*", re.UNICODE)
        while position < len(expression):
            if expression[position] == "[":
                match = re.match(r"\[(0|[1-9]\d*)\]", expression[position:])
                if not match:
                    raise ValueError("Array paths use nonnegative indexes such as items[0]")
                fields.append(match.group(1))
                position += match.end()
            else:
                match = field_pattern.match(expression, position)
                if not match:
                    raise ValueError("Use a dotted/index path or a JSON Pointer beginning with /")
                fields.append(match.group())
                position = match.end()
            if position < len(expression):
                next_character = expression[position]
                if next_character == ".":
                    position += 1
                    if position == len(expression) or expression[position] == "[":
                        raise ValueError("A dotted path must name an object field after each dot")
                elif next_character != "[":
                    raise ValueError("Use dots between fields and brackets around array indexes")
    if len(fields) > 32:
        raise ValueError("JSON paths are limited to 32 steps")
    for field in fields:
        if isinstance(value, dict):
            if field not in value:
                raise ValueError(f"Object has no field {field!r}")
            value = value[field]
        elif isinstance(value, list):
            if not re.fullmatch(r"0|[1-9]\d*", field) or len(field) > 12 or int(field) >= len(value):
                raise ValueError("Array index is outside the available values")
            value = value[int(field)]
        else:
            raise ValueError("The path continues beyond an object or array")
    return _json(value)


def markdown_outline(text, mode):
    if mode not in ("outline", "plain"):
        raise ValueError("Choose outline or plain")
    headings, links, fenced, code_blocks = [], [], None, 0
    for line_number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            character = marker.group(1)[0]
            if fenced is None:
                fenced, code_blocks = character, code_blocks + 1
            elif fenced == character:
                fenced = None
            continue
        if fenced:
            continue
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading and len(headings) < 200:
            headings.append({"level": len(heading.group(1)), "text": heading.group(2), "line": line_number})
        if len(links) < 200:
            for match in re.finditer(r"(?<!!)\[([^\]\n]{0,200})\]\(([^)\n]{1,1000})\)", line):
                links.append({"label": match.group(1), "destination": match.group(2)})
                if len(links) == 200:
                    break
    if mode == "outline":
        words = len(text.split())
        return _json({"words": words, "lines": len(text.splitlines()),
                      "reading_minutes_at_200_words_per_minute": round(words / 200, 2),
                      "headings": headings, "links": links, "fenced_code_blocks": code_blocks,
                      "scope": "Lightweight outline, capped at 200 headings and 200 links; not a full Markdown parser."})
    plain = re.sub(r"^\s{0,3}(?:`{3,}|~{3,}).*$", "", text, flags=re.MULTILINE)
    plain = re.sub(r"^\s{0,3}#{1,6}\s+", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"!?\[([^\]\n]*)\]\([^)\n]*\)", r"\1", plain)
    plain = re.sub(r"(`+)([^`\n]+)\1", r"\2", plain)
    plain = re.sub(r"(\*\*|__)(.+?)\1", r"\2", plain)
    return plain


def csv_convert(text, mode):
    if mode == "to-json":
        rows = list(csv.reader(io.StringIO(text)))
        if not rows or not rows[0] or any(not item for item in rows[0]) or len(set(rows[0])) != len(rows[0]):
            raise ValueError("CSV requires a header with nonempty, unique column names")
        if len(rows) > 5001 or len(rows[0]) > 100:
            raise ValueError("Table exceeds 5,000 rows or 100 columns")
        if any(len(row) != len(rows[0]) for row in rows[1:]):
            raise ValueError("Every CSV row must have the same number of fields as its header")
        return _json([dict(zip(rows[0], row)) for row in rows[1:]])
    if mode != "from-json":
        raise ValueError("Mode must be to-json or from-json")
    rows = _strict_json(text)
    if not isinstance(rows, list) or not rows or len(rows) > 5000 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Use a nonempty JSON array of up to 5,000 objects")
    headers = list(dict.fromkeys(key for row in rows for key in row))
    if not headers or len(headers) > 100:
        raise ValueError("Table requires 1–100 columns")
    if any(isinstance(value, (list, dict)) for row in rows for value in row.values()):
        raise ValueError("CSV cells must be scalar values, not arrays or objects")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def jwt_read(text):
    fields = text.strip().split(".")
    if len(fields) != 3 or any(not field for field in fields[:2]):
        raise ValueError("Use a three-part compact JWT")
    decoded = []
    for part in fields[:2]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
            raise ValueError("JWT header and payload must be Base64url")
        value = _strict_json(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JWT header and payload must be JSON objects")
        decoded.append(value)
    return _json({"signature_verified": False, "notice": "Decoded information only. Do not trust this token without signature and claim verification.",
                  "header": decoded[0], "payload": decoded[1]})


_REGEX_PROGRAM = r'''
import json,re,sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
except ImportError:
    pass
try:
    data=json.load(sys.stdin)
    matches=[]
    capped=False
    for match in re.finditer(data['pattern'],data['text'],re.MULTILINE):
        if len(matches)==200:
            capped=True
            break
        matches.append({'start':match.start(),'end':match.end(),'match':match.group()[:500],'groups':[g[:500] if g is not None else None for g in match.groups()[:20]]})
    print(json.dumps({'matches':matches,'limited_to_200_matches':capped},ensure_ascii=False))
except Exception as error:
    print(json.dumps({'error':str(error)}))
'''


def regex_matches(text, pattern):
    if len(text) > 20000 or len(pattern) > 512:
        raise ValueError("Pattern lab allows 20,000 input characters and a 512-character pattern")
    try:
        result = subprocess.run([sys.executable, "-I", "-c", _REGEX_PROGRAM],
                                input=json.dumps({"pattern": pattern, "text": text}), text=True,
                                capture_output=True, timeout=1.0, check=False)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Pattern exceeded its 1-second time limit; simplify the expression") from error
    if result.returncode != 0 or not result.stdout:
        raise ValueError("Pattern exceeded the worker's resource limit")
    response = json.loads(result.stdout)
    if "error" in response:
        raise ValueError(response["error"])
    return _json(response)


def generate_password(length, alphabet):
    length = _integer(length, 8, 256, "Password length")
    sets = {"letters": string.ascii_letters, "alphanumeric": string.ascii_letters + string.digits,
            "all": string.ascii_letters + string.digits + "!#$%&()*+,-./:;<=>?@[]^_{|}~"}
    if alphabet not in sets:
        raise ValueError("Alphabet must be all, letters, or alphanumeric")
    characters = sets[alphabet]
    password = "".join(secrets.choice(characters) for _ in range(length))
    return f"{password}\n\nRandom-source entropy: {length * math.log2(len(characters)):.1f} bits\nGenerated locally with secrets.choice; no password is saved automatically."


_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
           ast.Pow: operator.pow}
_FUNCTIONS = {"abs": abs, "round": round, "sqrt": math.sqrt, "sin": math.sin,
              "cos": math.cos, "tan": math.tan, "log": math.log, "log10": math.log10,
              "floor": math.floor, "ceil": math.ceil}


def calculate(expression):
    if len(expression) > 512:
        raise ValueError("Expression is limited to 512 characters")
    tree = ast.parse(expression.strip(), mode="eval")
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Expression is too complex")

    def bounded(value):
        if type(value) not in (int, float) or abs(value) > 1e100 or not math.isfinite(value):
            raise ValueError("Result must be finite and no larger than 1e100")
        return value

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            return bounded(node.value)
        if isinstance(node, ast.Name) and node.id in ("pi", "e", "tau"):
            return getattr(math, node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return bounded(evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e12):
                raise ValueError("Powers require an exponent ≤100 and base ≤1e12 in magnitude")
            return bounded(_BINARY[type(node.op)](left, right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS and not node.keywords and len(node.args) <= 3:
            return bounded(_FUNCTIONS[node.func.id](*(evaluate(arg) for arg in node.args)))
        raise ValueError("Only arithmetic, named constants, and the listed math functions are allowed")
    return str(evaluate(tree))


def convert_units(text, conversion):
    value = float(text.strip())
    if not math.isfinite(value) or abs(value) > 1e100:
        raise ValueError("Enter a finite value no larger than 1e100")
    parts = [part.strip() for part in conversion.split("->")]
    if len(parts) != 2:
        raise ValueError("Write a conversion such as km -> mi")
    source, target = parts
    lengths = {"m": 1, "km": 1000, "cm": .01, "mm": .001, "ft": .3048, "in": .0254, "mi": 1609.344}
    storage = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
    if source in lengths and target in lengths:
        result = value * lengths[source] / lengths[target]
    elif source in storage and target in storage:
        result = value * storage[source] / storage[target]
    elif source in ("C", "F", "K") and target in ("C", "F", "K"):
        kelvin = value if source == "K" else value + 273.15 if source == "C" else (value - 32) * 5 / 9 + 273.15
        if kelvin < -1e-10:
            raise ValueError("Temperature cannot be below absolute zero")
        result = kelvin if target == "K" else kelvin - 273.15 if target == "C" else (kelvin - 273.15) * 9 / 5 + 32
    else:
        raise ValueError("Use compatible units: m/km/cm/mm/ft/in/mi; C/F/K; B/KiB/MiB/GiB/TiB")
    return f"{value:.12g} {source} = {result:.12g} {target}"


def convert_time(text):
    text = text.strip()
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        value = datetime.fromtimestamp(float(text), timezone.utc)
    else:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
    return _json({"unix_seconds": value.timestamp(), "utc": value.astimezone(timezone.utc).isoformat(),
                  "local": value.astimezone().isoformat(), "weekday_utc": value.astimezone(timezone.utc).strftime("%A"),
                  "timezone_rule": "Input without a timezone is interpreted as UTC"})


def subnet_report(text):
    network = ipaddress.ip_network(text.strip(), strict=False)
    count = network.num_addresses
    first = network.network_address if network.prefixlen >= network.max_prefixlen - 1 else network.network_address + 1
    last = network.broadcast_address if network.version == 6 or network.prefixlen >= network.max_prefixlen - 1 else network.broadcast_address - 1
    return _json({"network": str(network), "version": network.version, "prefix_length": network.prefixlen,
                  "network_address": str(network.network_address), "last_address": str(network.broadcast_address),
                  "netmask": str(network.netmask), "address_count": count,
                  "first_host": str(first), "last_host": str(last), "private": network.is_private,
                  "note": "No hosts were scanned. IPv4 /31 and /32 follow point-to-point/host route conventions."})


def url_report(text):
    url = urlsplit(text.strip())
    if url.scheme.lower() not in ("http", "https", "ftp", "file"):
        raise ValueError("Use an absolute http, https, ftp, or file URL")
    if url.scheme != "file" and not url.hostname:
        raise ValueError("URL requires a hostname")
    return _json({"scheme": url.scheme, "hostname": url.hostname, "port": url.port,
                  "username_present": url.username is not None, "password_present": url.password is not None,
                  "path": url.path, "query_fields": parse_qsl(url.query, keep_blank_values=True, max_num_fields=1000),
                  "fragment": url.fragment, "network_request_made": False})


def domain_report(text):
    name = text.strip().rstrip(".")
    if not name or len(name) > 253 or any(character in name for character in "/:@ \t\r\n"):
        raise ValueError("Enter a domain name without a URL, port, or whitespace")
    ascii_name = name.encode("idna").decode("ascii").lower()
    if len(ascii_name) > 253:
        raise ValueError("ASCII hostname exceeds 253 characters")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in ascii_name.split(".")):
        raise ValueError("Domain labels must be 1–63 valid hostname characters")
    return _json({"unicode": ascii_name.encode("ascii").decode("idna"), "ascii": ascii_name,
                  "labels": len(ascii_name.split(".")), "dns_request_made": False,
                  "note": "Python's built-in IDNA codec is used. This does not establish domain ownership or safety."})


def parse_color(text):
    text = text.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", text):
        text = "#" + "".join(character * 2 for character in text[1:])
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return tuple(int(text[offset:offset + 2], 16) for offset in (1, 3, 5))
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", text)
    if match:
        values = tuple(map(int, match.groups()))
        if max(values) <= 255:
            return values
    raise ValueError("Use #RGB, #RRGGBB, or rgb(r,g,b), with channels from 0 to 255")


def luminance(rgb):
    channels = [value / 255 for value in rgb]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055)**2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))


def color_report(text):
    rgb = parse_color(text)
    channels = [value / 255 for value in rgb]
    hue, lightness, saturation = colorsys.rgb_to_hls(*channels)
    hsv = colorsys.rgb_to_hsv(*channels)
    return _json({"hex": "#%02x%02x%02x" % rgb, "rgb": list(rgb),
                  "hsl": [round(hue * 360, 3), round(saturation * 100, 3), round(lightness * 100, 3)],
                  "hsv": [round(hsv[0] * 360, 3), round(hsv[1] * 100, 3), round(hsv[2] * 100, 3)],
                  "relative_luminance": luminance(rgb)})


def contrast_report(text):
    colors = re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgb\([^)]*\)", text)
    if len(colors) != 2:
        raise ValueError("Enter exactly two opaque colors, for example #ffffff #11223e")
    values = sorted(luminance(parse_color(color)) for color in colors)
    ratio = (values[1] + .05) / (values[0] + .05)
    return _json({"ratio": round(ratio, 4), "AA_normal_text": ratio >= 4.5,
                  "AA_large_text": ratio >= 3, "AAA_normal_text": ratio >= 7,
                  "AAA_large_text": ratio >= 4.5, "scope": "Opaque sRGB color pair; not an audit of an entire interface"})


def _regular_path(text):
    path = Path(text).expanduser()
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Choose a regular file, not a symbolic link or special file")
    return path


def file_report(text):
    path = _regular_path(text)
    info = path.stat()
    return _json({"path": str(path.absolute()), "bytes": info.st_size,
                  "mime_type_guess": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                  "permissions": oct(stat.S_IMODE(info.st_mode)), "owner_uid": info.st_uid, "group_gid": info.st_gid,
                  "modified_utc": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                  "metadata_changed_utc": datetime.fromtimestamp(info.st_ctime, timezone.utc).isoformat(),
                  "note": "Linux ctime is metadata-change time, not file-creation time"})


def _scan_directory(text):
    root = Path(text).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Choose a directory, not a symbolic link")
    root = root.resolve()
    files = []
    skipped = 0
    def onerror(error):
        raise ValueError(f"Cannot inspect directory: {error.filename}") from error
    for current, dirs, names in os.walk(root, followlinks=False, onerror=onerror):
        symbolic_dirs = [name for name in dirs if (Path(current) / name).is_symlink()]
        skipped += len(symbolic_dirs)
        dirs[:] = sorted(set(dirs) - set(symbolic_dirs))
        for name in sorted(names):
            path = Path(current) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                skipped += 1
                continue
            files.append((path, info))
            if len(files) > MAX_FILES:
                raise ValueError(f"Folder exceeds the {MAX_FILES:,}-file limit; choose a smaller folder")
    return root, files, skipped


def directory_report(text):
    root, files, skipped = _scan_directory(text)
    types = Counter(path.suffix.lower() or "(no extension)" for path, info in files)
    return _json({"directory": str(root), "regular_files": len(files), "total_bytes": sum(info.st_size for path, info in files),
                  "symlinks_and_special_files_skipped": skipped, "extensions": dict(types.most_common()),
                  "largest_files": [{"path": str(path.relative_to(root)), "bytes": info.st_size} for path, info in sorted(files, key=lambda row: row[1].st_size, reverse=True)[:20]]})


def _content_hash(path, expected):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_ino != expected.st_ino or before.st_size != expected.st_size:
            raise ValueError(f"File changed during scan: {path.name}")
        digest = hashlib.sha256()
        remaining = before.st_size
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f"File changed during scan: {path.name}")
            remaining -= len(chunk)
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError(f"File changed during scan: {path.name}")
        return digest.hexdigest()


def duplicate_report(text):
    root, files, skipped = _scan_directory(text)
    sizes = defaultdict(list)
    for path, info in files:
        sizes[info.st_size].append((path, info))
    groups = []
    bytes_hashed = 0
    for size, candidates in sorted(sizes.items()):
        if len(candidates) < 2:
            continue
        hashes = defaultdict(list)
        for path, info in candidates:
            bytes_hashed += size
            if bytes_hashed > MAX_SCAN_BYTES:
                raise ValueError("Duplicate scan exceeds its 256 MiB read budget; choose a smaller folder")
            hashes[_content_hash(path, info)].append(str(path.relative_to(root)))
        for digest, paths in hashes.items():
            if len(paths) > 1:
                groups.append({"bytes_each": size, "sha256": digest, "paths": paths})
    return _json({"directory": str(root), "files_examined": len(files), "bytes_hashed": bytes_hashed,
                  "symlinks_and_special_files_skipped": skipped, "duplicate_groups": groups,
                  "note": "Read-only report. No file was deleted, moved, or linked."})


def log_tail(text, lines):
    count = _integer(lines, 1, 2000, "Line count")
    path = _regular_path(text)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Choose a regular text file")
        size = info.st_size
        start = max(0, size - MAX_LOG_BYTES)
        stream.seek(start)
        raw = stream.read(MAX_LOG_BYTES)
    if b"\0" in raw:
        raise ValueError("This appears to be a binary file; choose a text log")
    values = raw.decode("utf-8", errors="replace").splitlines()
    if start:
        values = values[1:]
    return ("[Read bounded to the last 1 MiB]\n" if start else "") + "\n".join(values[-count:])


def run_tool(tool_id: str, text: str, option: str = "") -> str:
    """Run one explicitly selected local utility; returned text is never executed."""
    if not isinstance(text, str) or not isinstance(option, str):
        raise ValueError("Tool input must be text")
    if len(text.encode("utf-8")) > MAX_TEXT or len(option.encode("utf-8")) > MAX_TEXT:
        raise ValueError("Input is limited to 1 MiB per field")
    spec = next((tool for tool in TOOLS if tool["id"] == tool_id), None)
    if spec is None:
        raise ValueError("Unknown Studio tool")
    option = option if option else spec["option_default"]
    try:
        if tool_id == "unicode": return unicode_report(text)
        if tool_id == "cleanup": return clean_lines(text, option)
        if tool_id == "textcase": return text_case(text, option.strip())
        if tool_id == "hex": return utf8_hex(text, option.strip())
        if tool_id == "digest": return text_fingerprint(text, option.strip())
        if tool_id == "jsonpath": return json_path(text, option.strip())
        if tool_id == "markdown": return markdown_outline(text, option.strip())
        if tool_id == "diff": return "".join(difflib.unified_diff(text.splitlines(keepends=True), option.splitlines(keepends=True), fromfile="First text", tofile="Second text")) or "The texts are identical."
        if tool_id in ("html", "base64", "urlencode"): return _encode_decode(tool_id, text, option.strip())
        if tool_id == "json": return json.dumps(_strict_json(text), indent=_integer(option, 0, 8, "Indentation"), sort_keys=True, ensure_ascii=False, allow_nan=False)
        if tool_id == "csv": return csv_convert(text, option.strip())
        if tool_id == "toml":
            try: import tomllib
            except ImportError as error: raise ValueError("TOML support requires Python 3.11 or newer") from error
            return _json(tomllib.loads(text))
        if tool_id == "jwt": return jwt_read(text)
        if tool_id == "regex": return regex_matches(text, option)
        if tool_id == "password": return generate_password(text, option.strip())
        if tool_id == "uuid": return "\n".join(str(uuid.uuid4()) for _ in range(_integer(text, 1, 100, "Identifier count")))
        if tool_id == "calculator": return calculate(text)
        if tool_id == "units": return convert_units(text, option)
        if tool_id == "time": return convert_time(text)
        if tool_id == "subnet": return subnet_report(text)
        if tool_id == "urlparts": return url_report(text)
        if tool_id == "idna": return domain_report(text)
        if tool_id == "color": return color_report(text)
        if tool_id == "contrast": return contrast_report(text)
        if tool_id == "fileinfo": return file_report(text)
        if tool_id == "inventory": return directory_report(text)
        if tool_id == "duplicates": return duplicate_report(text)
        if tool_id == "logtail": return log_tail(text, option)
    except (OSError, UnicodeError, binascii.Error, SyntaxError, ArithmeticError, TypeError, RecursionError) as error:
        raise ValueError(str(error)) from error
    raise ValueError("Unsupported Studio tool")


def studio_directory():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "livara/studio"


def _private_directory(path):
    if path.is_symlink():
        raise ValueError("Private storage must not be a symbolic link")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def _atomic_private(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".studio-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_private(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Private record is not a regular file")
        text = stream.read(MAX_TEXT + 1)
        if len(text) > MAX_TEXT:
            raise ValueError("Private record exceeds its size limit")
        return _strict_json(text)


class WorkspaceState:
    """Private launcher preferences and tool IDs, never tool inputs or results."""

    PREFERENCE_DEFAULTS = {"accent": "violet", "density": "comfortable", "editor-size": 13}

    def __init__(self, root: Path | None = None):
        self.root = (root if root is not None else studio_directory()).expanduser().absolute()
        self.path = self.root / "workspace.json"
        self._prepare_root()

    def _prepare_root(self):
        if any(path.is_symlink() for path in (self.root, *self.root.parents)):
            raise ValueError("Studio workspace storage must not use symbolic links")
        _private_directory(self.root)
        if self.path.is_symlink():
            raise ValueError("Studio workspace preferences must not be a symbolic link")
        if self.path.exists() and not stat.S_ISREG(self.path.stat().st_mode):
            raise ValueError("Studio workspace preferences must be a regular file")

    @classmethod
    def defaults(cls):
        return {"schema": 1, "favorites": ["json", "calculator", "unicode"],
                "recent": [], "preferences": dict(cls.PREFERENCE_DEFAULTS)}

    @staticmethod
    def _tool_id(tool_id):
        if not isinstance(tool_id, str) or tool_id not in {tool["id"] for tool in TOOLS}:
            raise ValueError("Choose a tool from the Studio catalog")
        return tool_id

    @classmethod
    def _preferences(cls, values):
        if not isinstance(values, dict) or set(values) != set(cls.PREFERENCE_DEFAULTS):
            raise ValueError("Studio preferences have unsupported fields")
        if values["accent"] not in ("violet", "ocean", "mint", "rose"):
            raise ValueError("Choose violet, ocean, mint, or rose")
        if values["density"] not in ("comfortable", "compact"):
            raise ValueError("Choose comfortable or compact spacing")
        if type(values["editor-size"]) is not int or not 11 <= values["editor-size"] <= 22:
            raise ValueError("Studio editor size must be between 11 and 22 pixels")
        return dict(values)

    @classmethod
    def _validated(cls, data):
        if not isinstance(data, dict) or set(data) != {"schema", "favorites", "recent", "preferences"} or type(data.get("schema")) is not int or data["schema"] != 1:
            raise ValueError("Studio workspace preferences use an unsupported format")
        favorites = data["favorites"]
        if not isinstance(favorites, list) or len(favorites) > len(TOOLS):
            raise ValueError("Studio favorites are malformed")
        for tool_id in favorites:
            cls._tool_id(tool_id)
        if len(set(favorites)) != len(favorites):
            raise ValueError("Studio favorites contain duplicates")
        recent = data["recent"]
        if not isinstance(recent, list) or len(recent) > 8:
            raise ValueError("Studio recent activity is malformed")
        seen = set()
        normalized = []
        for entry in recent:
            if not isinstance(entry, dict) or set(entry) != {"id", "used_at"}:
                raise ValueError("Studio recent activity can contain only a tool ID and timestamp")
            tool_id = cls._tool_id(entry["id"])
            stamp = entry["used_at"]
            if tool_id in seen or not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\+\d\d:\d\d|Z)", stamp):
                raise ValueError("Studio recent activity has an invalid timestamp or repeated tool")
            try:
                datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("Studio recent activity has an invalid timestamp") from error
            seen.add(tool_id)
            normalized.append({"id": tool_id, "used_at": stamp})
        return {"schema": 1, "favorites": list(favorites), "recent": normalized,
                "preferences": cls._preferences(data["preferences"])}

    def read(self):
        self._prepare_root()
        if not self.path.exists():
            return self.defaults()
        try:
            return self._validated(_read_private(self.path))
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"Studio workspace preferences could not be read; the original file was preserved. {error}") from error

    def _write(self, data):
        checked = self._validated(data)
        self._prepare_root()
        _atomic_private(self.path, checked)
        return checked

    def set_favorite(self, tool_id, enabled):
        tool_id = self._tool_id(tool_id)
        if type(enabled) is not bool:
            raise ValueError("Favorite state must be on or off")
        data = self.read()
        if not enabled:
            data["favorites"] = [item for item in data["favorites"] if item != tool_id]
        elif tool_id not in data["favorites"]:
            data["favorites"].append(tool_id)
        return self._write(data)

    def record_tool(self, tool_id):
        tool_id = self._tool_id(tool_id)
        data = self.read()
        data["recent"] = [{"id": tool_id, "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                          *(item for item in data["recent"] if item["id"] != tool_id)][:8]
        return self._write(data)

    def set_preferences(self, **values):
        if "editor_size" in values:
            if "editor-size" in values:
                raise ValueError("Specify editor size only once")
            values["editor-size"] = values.pop("editor_size")
        if not values or set(values) - set(self.PREFERENCE_DEFAULTS):
            raise ValueError("Choose a supported Studio appearance preference")
        data = self.read()
        data["preferences"] = self._preferences({**data["preferences"], **values})
        return self._write(data)

    def reset_preferences(self):
        data = self.read()
        data["preferences"] = dict(self.PREFERENCE_DEFAULTS)
        return self._write(data)


class NoteStore:
    def __init__(self, root: Path | None = None):
        self.root = (root if root is not None else studio_directory() / "notes").expanduser()
        _private_directory(self.root)
        self.last_errors = []

    def _path(self, note_id):
        if not isinstance(note_id, str) or re.fullmatch(r"[0-9a-f]{32}", note_id) is None:
            raise ValueError("Invalid note identifier")
        path = self.root / (note_id + ".json")
        if path.is_symlink():
            raise ValueError("Notes must not be symbolic links")
        return path

    def save(self, title: str, body: str, note_id: str | None = None):
        if not isinstance(title, str) or not isinstance(body, str):
            raise ValueError("A note title and body must be text")
        title = title.strip()
        if not title or len(title) > 100 or "\n" in title or "\r" in title:
            raise ValueError("Use a single-line note title of 1–100 characters")
        if len(body.encode("utf-8")) > 256 * 1024:
            raise ValueError("A note is limited to 256 KiB of UTF-8 text")
        note_id = note_id or uuid.uuid4().hex
        path = self._path(note_id)
        _atomic_private(path, {"schema": 1, "id": note_id, "title": title, "body": body,
                               "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return note_id

    def read(self, note_id):
        data = _read_private(self._path(note_id))
        return self._validated_note(data, note_id)

    @staticmethod
    def _validated_note(data, note_id):
        if not isinstance(data, dict) or data.get("schema") != 1 or data.get("id") != note_id or any(not isinstance(data.get(field), str) for field in ("title", "body", "updated_at")):
            raise ValueError("Unsupported or malformed note")
        if not data["title"].strip() or len(data["title"]) > 100 or any(value in data["title"] for value in ("\n", "\r")) or len(data["body"].encode("utf-8")) > 256 * 1024:
            raise ValueError("Stored note exceeds the title or body limits")
        return data

    def list_notes(self, query=""):
        notes = []
        self.last_errors = []
        for path in sorted(self.root.glob("*.json")):
            try:
                value = self.read(path.stem)
                if query.casefold() in (value["title"] + "\n" + value["body"]).casefold():
                    notes.append(value)
            except (OSError, ValueError, UnicodeError) as error:
                self.last_errors.append(str(error))
        return sorted(notes, key=lambda note: (note["updated_at"], note["id"]), reverse=True)

    def archive(self, note_id):
        path = self._path(note_id)
        self.read(note_id)
        archive = self.root / "archive"
        _private_directory(archive)
        os.replace(path, archive / path.name)

    def _archive_path(self, note_id):
        destination = self._path(note_id)
        archive = self.root / "archive"
        if archive.is_symlink() or (archive.exists() and not archive.is_dir()):
            raise ValueError("The note archive must be a real directory")
        source = archive / destination.name
        if source.is_symlink():
            raise ValueError("Archived notes must not be symbolic links")
        return source

    def read_archived(self, note_id):
        return self._validated_note(_read_private(self._archive_path(note_id)), note_id)

    def list_archived(self, query=""):
        if not isinstance(query, str) or len(query) > 256:
            raise ValueError("Archive search is limited to 256 text characters")
        archive = self._archive_path("0" * 32).parent
        if not archive.exists():
            return []
        self.last_errors = []
        notes = []
        for number, path in enumerate(archive.glob("*.json")):
            if number == 1000:
                raise ValueError("The archive exceeds the 1,000-note display budget")
            try:
                note = self.read_archived(path.stem)
                if query.casefold() in (note["title"] + "\n" + note["body"]).casefold():
                    notes.append(note)
            except (OSError, ValueError, UnicodeError) as error:
                self.last_errors.append(str(error))
        return sorted(notes, key=lambda note: (note["updated_at"], note["id"]), reverse=True)

    def restore(self, note_id):
        destination = self._path(note_id)
        if destination.exists():
            raise ValueError("A note with this identifier already exists")
        source = self._archive_path(note_id)
        self.read_archived(note_id)
        os.replace(source, destination)


def note_export(note, format="markdown"):
    """Return an explicitly selected note as portable text; do not write a file."""
    if not isinstance(note, dict) or any(not isinstance(note.get(field), str) for field in ("title", "body")):
        raise ValueError("Choose a note with a text title and body")
    title, body = note["title"], note["body"]
    if not title.strip() or len(title) > 100 or any(value in title for value in ("\n", "\r")) or len(body.encode("utf-8")) > 256 * 1024:
        raise ValueError("Note export exceeds the title or body limits")
    if format == "markdown":
        # Escape punctuation in the heading so the title remains literal text.
        heading = re.sub(r"([\\`*{}\[\]()#+.!_<>-])", r"\\\1", title)
        return f"# {heading}\n\n{body}" + ("" if body.endswith("\n") else "\n")
    if format == "text":
        return f"{title}\n{'=' * min(len(title), 80)}\n\n{body}" + ("" if body.endswith("\n") else "\n")
    raise ValueError("Choose markdown or text export")


def record_focus(seconds: int, label: str = ""):
    if type(seconds) is not int or not 1 <= seconds <= 10800:
        raise ValueError("Focus duration must be 1–10,800 seconds")
    if not isinstance(label, str) or len(label) > 100 or any(character in label for character in "\r\n"):
        raise ValueError("Use a single-line session label of up to 100 characters")
    root = studio_directory()
    _private_directory(root)
    record = {"seconds": seconds, "label": label, "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = root / "focus.jsonl"
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Focus history must be a regular file")
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return record


def focus_history(limit=30):
    limit = _integer(limit, 1, 1000, "History count")
    path = studio_directory() / "focus.jsonl"
    if path.is_symlink():
        raise ValueError("Focus history must not be a symbolic link")
    if not path.exists():
        return []
    text = log_tail(str(path), "2000")
    records = []
    for line in text.splitlines():
        try:
            data = _strict_json(line)
            if isinstance(data, dict) and type(data.get("seconds")) is int and 1 <= data["seconds"] <= 10800 and isinstance(data.get("label"), str) and isinstance(data.get("completed_at"), str):
                records.append(data)
        except ValueError:
            continue
    return list(reversed(records[-limit:]))
