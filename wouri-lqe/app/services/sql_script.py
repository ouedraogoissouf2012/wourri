"""Decoupage d'un script SQL en statements, conscient des litteraux (issue #493).

Le runner de migrations execute les statements un par un : il doit donc couper le
fichier sur les ';'. Un ';' place dans un litteral ('...', E'...', $tag$...$tag$)
ou dans un identifiant quote ("...") n'est PAS un separateur : le couper produit
deux fragments invalides dont le premier s'execute avant que le second echoue sur
une erreur de syntaxe sans rapport avec la cause reelle.

Choix assume (issue #493, option a) : un tel script est REFUSE avant la moindre
execution, par une erreur qui nomme le fichier et la ligne. Faire passer du contenu
porteur de ';' reste possible, mais c'est une decision de conception a prendre
(un `execute()` par fichier, option c de l'issue), pas un effet de bord silencieux
du decoupage.

Les commentaires sont retires ou qu'ils soient : `-- ...` jusqu'a la fin de ligne
meme apres du code, et `/* ... */` imbricables comme le fait PostgreSQL.
"""
from __future__ import annotations

_LINE_COMMENT = "--"
_BLOCK_OPEN = "/*"
_BLOCK_CLOSE = "*/"


class SqlScriptError(RuntimeError):
    """Script SQL refuse avant execution : indecoupable sans risque de corruption."""


def split_statements(sql: str, *, origin: str) -> list[str]:
    """Retourne les statements de `sql`, commentaires retires, sans les ';' separateurs.

    `origin` (nom du fichier) n'apparait que dans les messages d'erreur.
    Leve `SqlScriptError` si un ';' se trouve dans un litteral, ou si un litteral
    ou un commentaire bloc n'est pas ferme.
    """
    statements: list[str] = []
    current: list[str] = []
    index = 0
    line = 1
    while index < len(sql):
        char = sql[index]
        if char == "\n":
            current.append(char)
            index += 1
            line += 1
        elif sql.startswith(_LINE_COMMENT, index):
            index = _end_of_line(sql, index)
            current.append(" ")
        elif sql.startswith(_BLOCK_OPEN, index):
            index, line = _skip_block_comment(sql, index, line, origin)
            current.append(" ")
        elif char in ("'", '"'):
            index, line = _copy_quoted(sql, index, line, origin, current)
        elif char == "$" and (tag := _dollar_tag(sql, index)):
            index, line = _copy_dollar_quoted(sql, index, line, origin, current, tag)
        elif char == ";":
            statements.append("".join(current).strip())
            current.clear()
            index += 1
        else:
            current.append(char)
            index += 1
    statements.append("".join(current).strip())
    return [statement for statement in statements if statement]


def _end_of_line(sql: str, index: int) -> int:
    """Index du '\n' qui termine la ligne (ou fin du script) : le '\n' reste a traiter."""
    end = sql.find("\n", index)
    return len(sql) if end < 0 else end


def _skip_block_comment(sql: str, index: int, line: int, origin: str) -> tuple[int, int]:
    """Saute un `/* ... */` (imbricable en PostgreSQL). Retourne (index apres, ligne)."""
    start_line = line
    depth = 0
    while index < len(sql):
        if sql.startswith(_BLOCK_OPEN, index):
            depth += 1
            index += 2
        elif sql.startswith(_BLOCK_CLOSE, index):
            depth -= 1
            index += 2
            if depth == 0:
                return index, line
        else:
            if sql[index] == "\n":
                line += 1
            index += 1
    raise _error(origin, start_line, "commentaire bloc `/*` non ferme")


def _copy_quoted(
    sql: str, index: int, line: int, origin: str, out: list[str]
) -> tuple[int, int]:
    """Copie un litteral `'chaine'` ou un identifiant `"quote"`, quotes comprises."""
    quote = sql[index]
    kind = "chaine quotee" if quote == "'" else "identifiant quote"
    start_line = line
    backslash_escapes = quote == "'" and _is_escape_string(sql, index)
    out.append(quote)
    index += 1
    while index < len(sql):
        char = sql[index]
        if char == "\\" and backslash_escapes and index + 1 < len(sql):
            out.append(sql[index : index + 2])
            line += sql[index + 1] == "\n"
            index += 2
        elif char == quote:
            if sql.startswith(quote * 2, index):  # '' / "" = un quote dans le litteral
                out.append(quote * 2)
                index += 2
                continue
            out.append(quote)
            return index + 1, line
        elif char == ";":
            raise _error(
                origin,
                line,
                f"';' dans une {kind} ouverte ligne {start_line} : le runner de"
                " migrations decoupe les fichiers SQL sur ';' et couperait ce statement"
                " en deux. Retirer le ';' du litteral (issue #493).",
            )
        else:
            line += char == "\n"
            out.append(char)
            index += 1
    raise _error(origin, start_line, f"litteral {quote}...{quote} non ferme")


def _is_escape_string(sql: str, index: int) -> bool:
    """`E'...'` : le backslash y echappe le quote suivant (contrairement a `'...'`)."""
    if index == 0 or sql[index - 1] not in ("E", "e"):
        return False
    before = sql[index - 2] if index >= 2 else ""
    return not (before.isalnum() or before == "_")


def _dollar_tag(sql: str, index: int) -> str | None:
    """Tag d'ouverture dollar (`$$` ou `$tag$`) a `index`, sinon None (ex. `$1`)."""
    end = index + 1
    if end < len(sql) and (sql[end].isalpha() or sql[end] == "_"):
        end += 1
        while end < len(sql) and (sql[end].isalnum() or sql[end] == "_"):
            end += 1
    return sql[index : end + 1] if end < len(sql) and sql[end] == "$" else None


def _copy_dollar_quoted(
    sql: str, index: int, line: int, origin: str, out: list[str], tag: str
) -> tuple[int, int]:
    """Copie un litteral dollar `$tag$...$tag$` (aucun echappement a l'interieur)."""
    start_line = line
    index += len(tag)
    close = sql.find(tag, index)
    if close < 0:
        raise _error(origin, start_line, f"litteral dollar {tag}...{tag} non ferme")
    body = sql[index:close]
    if ";" in body:
        raise _error(
            origin,
            start_line + body[: body.index(";")].count("\n"),
            f"';' dans un litteral dollar {tag} ouvert ligne {start_line} : le runner de"
            " migrations decoupe les fichiers SQL sur ';' et couperait ce statement en"
            " deux. Sortir ce contenu des migrations (issue #493).",
        )
    out.append(f"{tag}{body}{tag}")
    return close + len(tag), line + body.count("\n")


def _error(origin: str, line: int, cause: str) -> SqlScriptError:
    return SqlScriptError(f"{origin}:{line} — {cause}")
