"""
Wouri — Comptage des lignes logiques d'un fichier de code (ADR-0051 §6.1, issue #621).

Une ligne logique est une ligne physique qui porte du code : ni commentaire, ni
ligne vide, ni chaîne de documentation. Le plafond de l'ADR-0051 porte sur ce
nombre, pour sanctionner la complexité et non l'explication.

Règle par langage :
  - Python : découpage par le `tokenize` et l'`ast` de Python lui-même. Les
    docstrings au sens PEP 257 — première instruction d'un module, d'une classe
    ou d'une fonction — sont exclues ; toute autre chaîne, SQL compris, compte.
  - JavaScript : hors commentaires `//` et `/* */`. Un analyseur lexical reconnaît
    chaînes, gabarits et expressions régulières, pour qu'un `//` ou un `/*` placé
    dans l'un d'eux ne soit pas pris pour un commentaire.
  - Vue : le bloc `template` ignore `<!-- -->`, `script` suit la règle JavaScript,
    `style` ignore `/* */` ; les balises de bloc comptent. Ce qui est hors des
    blocs suit la règle du `template`.

Limite connue, assumée : sans analyse syntaxique complète, un `/` est lu comme le
début d'une regex ou comme une division selon le jeton qui le précède — la règle
des analyseurs lexicaux JavaScript. Après `)` ou `}`, il est lu comme division.

Fonctions pures : aucune lecture de fichier ici (voir check_line_budget.py).
"""
from __future__ import annotations

import ast
import bisect
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import PurePosixPath


class LogicalLineError(ValueError):
    """La source ne peut pas être mesurée (syntaxe invalide, bloc non fermé, extension inconnue)."""


# ─────────────────────────────────────────────
# Python
# ─────────────────────────────────────────────

_PYTHON_NON_CODE = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
        tokenize.ENCODING,
    }
)
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

Position = tuple[int, int]  # (ligne, colonne en caractères), comme tokenize


def _char_column(lines: list[str], lineno: int, byte_offset: int) -> int:
    """ast donne des colonnes en octets UTF-8, tokenize en caractères."""
    return len(lines[lineno - 1].encode("utf-8")[:byte_offset].decode("utf-8"))


def _docstring_spans(tree: ast.AST, lines: list[str]) -> list[tuple[Position, Position]]:
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, _DOCSTRING_OWNERS) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            value = first.value
            start = (value.lineno, _char_column(lines, value.lineno, value.col_offset))
            end = (value.end_lineno, _char_column(lines, value.end_lineno, value.end_col_offset))
            spans.append((start, end))
    return spans


def python_logical_lines(source: str) -> int:
    source = source.replace("\r\n", "\n")
    try:
        tree = ast.parse(source)
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (SyntaxError, tokenize.TokenError, ValueError) as exc:
        raise LogicalLineError(f"source Python illisible : {exc}") from exc

    docstrings = _docstring_spans(tree, source.split("\n"))
    code_lines: set[int] = set()
    for tok in tokens:
        if tok.type in _PYTHON_NON_CODE:
            continue
        if tok.type == tokenize.STRING and any(
            start <= tok.start and tok.end <= end for start, end in docstrings
        ):
            continue
        code_lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(code_lines)


# ─────────────────────────────────────────────
# JavaScript, CSS, HTML : un analyseur lexical paramétré
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class _Syntax:
    block_comment: tuple[str, str]
    line_comment: str | None
    quotes: str
    template_literals: bool
    regex_literals: bool


_JS = _Syntax(("/*", "*/"), "//", "'\"", template_literals=True, regex_literals=True)
_CSS = _Syntax(("/*", "*/"), None, "'\"", template_literals=False, regex_literals=False)
_HTML = _Syntax(("<!--", "-->"), None, "", template_literals=False, regex_literals=False)

# Après ces mots-clés, un `/` ouvre une expression régulière, pas une division.
_REGEX_AFTER_KEYWORDS = frozenset(
    {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
     "throw", "case", "do", "else", "yield", "await"}
)
_WORD = re.compile(r"[\w$]+")


class _Scanner:
    """Parcourt source[start:end] et note les lignes qui portent du code."""

    def __init__(self, source: str, line_starts: list[int], syntax: _Syntax):
        self.src = source
        self.line_starts = line_starts
        self.syntax = syntax
        self.lines: set[int] = set()
        self.regex_allowed = True  # en début de source, un `/` ouvre une regex
        self.template_braces: list[int] = []  # accolades ouvertes par `${` imbriqué

    def _line(self, index: int) -> int:
        return bisect.bisect_right(self.line_starts, index)

    def _mark(self, start: int, end: int) -> None:
        self.lines.update(range(self._line(start), self._line(max(start, end - 1)) + 1))

    def scan(self, start: int, end: int) -> set[int]:
        i = start
        while i < end:
            i = self._step(i, end)
        return self.lines

    def _step(self, i: int, end: int) -> int:
        src, syn = self.src, self.syntax
        char = src[i]
        if char.isspace():
            return i + 1
        opening, closing = syn.block_comment
        if src.startswith(opening, i):
            close = src.find(closing, i + len(opening), end)
            return end if close < 0 else close + len(closing)
        if syn.line_comment and src.startswith(syn.line_comment, i):
            newline = src.find("\n", i, end)
            return end if newline < 0 else newline
        if char in syn.quotes:
            return self._string(i, end, char)
        if syn.template_literals and (char == "`" or (char == "}" and self.template_braces[-1:] == [0])):
            if char == "}":
                self.template_braces.pop()
            return self._template(i, end)
        if syn.regex_literals and char == "/" and self.regex_allowed:
            regex_end = self._regex_end(i, end)
            if regex_end is not None:
                self._mark(i, regex_end)
                self.regex_allowed = False
                return regex_end
        word = _WORD.match(src, i, end)
        if word:
            self._mark(i, word.end())
            self.regex_allowed = word.group() in _REGEX_AFTER_KEYWORDS
            return word.end()
        self._mark(i, i + 1)
        if self.template_braces and char in "{}":
            self.template_braces[-1] += 1 if char == "{" else -1
        self.regex_allowed = char not in ")]}"
        return i + 1

    def _string(self, i: int, end: int, quote: str) -> int:
        j = i + 1
        while j < end and self.src[j] not in (quote, "\n"):
            j += 2 if self.src[j] == "\\" else 1
        j = min(j + 1 if j < end and self.src[j] == quote else j, end)
        self._mark(i, j)
        self.regex_allowed = False
        return j

    def _template(self, i: int, end: int) -> int:
        """Texte de gabarit, depuis le « ` » ou le « } » qui le rouvre, jusqu'à « ` » ou « ${ »."""
        j = i + 1
        while j < end:
            if self.src[j] == "\\":
                j += 2
            elif self.src[j] == "`":
                j += 1
                break
            elif self.src.startswith("${", j):
                j += 2
                self.template_braces.append(0)
                break
            else:
                j += 1
        j = min(j, end)
        self._mark(i, j)
        self.regex_allowed = self.src[j - 1] == "{"
        return j

    def _regex_end(self, i: int, end: int) -> int | None:
        """Fin de l'expression régulière ouverte en i (drapeaux compris), ou None si elle n'est pas fermée sur la ligne."""
        j, in_class = i + 1, False
        while j < end and self.src[j] != "\n":
            char = self.src[j]
            if char == "\\":
                j += 2
                continue
            if char == "/" and not in_class:
                flags = _WORD.match(self.src, j + 1, end)
                return flags.end() if flags else j + 1
            if char in "[]":
                in_class = char == "["
            j += 1
        return None


def _line_starts(source: str) -> list[int]:
    return [0] + [m.end() for m in re.finditer("\n", source)]


def _count(source: str, syntax: _Syntax) -> int:
    source = source.replace("\r\n", "\n")
    return len(_Scanner(source, _line_starts(source), syntax).scan(0, len(source)))


def javascript_logical_lines(source: str) -> int:
    return _count(source, _JS)


# ─────────────────────────────────────────────
# Vue
# ─────────────────────────────────────────────

_VUE_BLOCK_OPEN = re.compile(r"^<(template|script|style)\b[^>]*>", re.MULTILINE)
_VUE_BLOCK_SYNTAX = {"template": _HTML, "script": _JS, "style": _CSS}


def _vue_block_close(source: str, kind: str, body_start: int) -> tuple[int, int]:
    """(début, fin) de la balise fermant le bloc ; un `template` peut en imbriquer d'autres."""
    tags = re.compile(rf"<{kind}\b[^>]*?(/?)>|</{kind}\s*>")
    depth = 1
    for tag in tags.finditer(source, body_start):
        if tag.group().startswith("</"):
            depth -= 1
            if depth == 0:
                return tag.start(), tag.end()
        elif kind == "template" and not tag.group(1):
            depth += 1
    raise LogicalLineError(f"bloc <{kind}> non fermé")


def vue_logical_lines(source: str) -> int:
    source = source.replace("\r\n", "\n")
    starts = _line_starts(source)
    lines: set[int] = set()
    cursor = 0
    for opening in _VUE_BLOCK_OPEN.finditer(source):
        if opening.start() < cursor:  # balise située à l'intérieur d'un bloc déjà traité
            continue
        kind = opening.group(1)
        close_start, close_end = _vue_block_close(source, kind, opening.end())
        lines |= _Scanner(source, starts, _HTML).scan(cursor, opening.end())
        lines |= _Scanner(source, starts, _VUE_BLOCK_SYNTAX[kind]).scan(opening.end(), close_start)
        lines |= _Scanner(source, starts, _HTML).scan(close_start, close_end)
        cursor = close_end
    lines |= _Scanner(source, starts, _HTML).scan(cursor, len(source))
    return len(lines)


# ─────────────────────────────────────────────
# Aiguillage
# ─────────────────────────────────────────────

_COUNTERS = {
    ".py": python_logical_lines,
    ".js": javascript_logical_lines,
    ".vue": vue_logical_lines,
}
SUPPORTED_EXTENSIONS = frozenset(_COUNTERS)


def count_logical_lines(filename: str, source: str) -> int:
    """Nombre de lignes logiques de `source`, selon l'extension de `filename`."""
    suffix = PurePosixPath(filename).suffix
    counter = _COUNTERS.get(suffix)
    if counter is None:
        raise LogicalLineError(f"extension non prise en charge : {suffix or '(aucune)'}")
    return counter(source)
