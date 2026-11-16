"""Part B: turn a typed condition into a search condition tuple (see model.search).

Grammar (precedence from highest to lowest: !, &&, ||):
    condition := and_expr ( "||" and_expr )*
    and_expr  := unary ( "&&" unary )*
    unary     := "!" unary | "(" condition ")" | predicate
    predicate := type "=" NAME
               | TEXT_FIELD contains "text"
               | TIME_FIELD ( "<" | "=" | ">" ) "YYYY-MM-DD HH:MM"
Strings are double-quoted; inside them \\" and \\\\ are escapes. Keywords and field names
ignore case. Errors raise ValueError with a 1-based position.
"""

from typing import List, Optional, Tuple

from . import FIELDS, TEXT_FIELDS, TIME_FIELDS, Condition
from .record_manager import check_time

Token = Tuple[str, str, int]  # (kind: "sym" | "str" | "word", text, 0-based position)

MAX_TOKENS = 200
_SYMBOLS = ("&&", "||", "!", "(", ")", "<", ">", "=")


def _error(message: str, position: int) -> ValueError:
    return ValueError(f"{message.rstrip('.')} (at position {position + 1})")


def _tokenize(text: str) -> List[Token]:
    tokens, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == '"':
            start, chars, i = i, [], i + 1
            while True:
                if i >= len(text):
                    raise _error("Missing closing quote", start)
                if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in '"\\':
                    chars.append(text[i + 1])
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    chars.append(text[i])
                    i += 1
            tokens.append(("str", "".join(chars), start))
        elif text[i:i + 2] in ("&&", "||"):
            tokens.append(("sym", text[i:i + 2], i))
            i += 2
        elif ch in _SYMBOLS:
            tokens.append(("sym", ch, i))
            i += 1
        elif ch.isascii() and (ch.isalpha() or ch == "_"):
            start = i
            while i < len(text) and text[i].isascii() and (text[i].isalnum() or text[i] == "_"):
                i += 1
            tokens.append(("word", text[start:i], start))
        else:
            raise _error(f"Unexpected character {ch!r}", i)
        if len(tokens) > MAX_TOKENS:
            raise _error(f"Condition is too long (limit {MAX_TOKENS} items)", i)
    return tokens


class _Parser:
    def __init__(self, tokens: List[Token], end: int) -> None:
        self.tokens, self.index, self.end = tokens, 0, end

    def peek(self) -> Optional[Token]:
        """The next token, or None at the end."""
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, expected: str) -> Token:
        """Consume and return the next token; raise ValueError if the condition ended."""
        token = self.peek()
        if token is None:
            raise _error(f"Expected {expected} but the condition ended", self.end)
        self.index += 1
        return token

    def at(self, symbol: str) -> bool:
        """True if the next token is the given symbol."""
        token = self.peek()
        return token is not None and token[0] == "sym" and token[1] == symbol

    def condition(self, depth: int = 0) -> Condition:
        """condition := and_expr ( || and_expr )*"""
        if depth > 40:
            token = self.peek()
            raise _error("Parentheses are nested too deeply", token[2] if token else self.end)
        node = self.and_expr(depth)
        while self.at("||"):
            self.index += 1
            node = ("or", node, self.and_expr(depth))
        return node

    def and_expr(self, depth: int) -> Condition:
        """and_expr := unary ( && unary )*"""
        node = self.unary(depth)
        while self.at("&&"):
            self.index += 1
            node = ("and", node, self.unary(depth))
        return node

    def unary(self, depth: int) -> Condition:
        """unary := ! unary | ( condition ) | predicate"""
        if self.at("!"):
            self.index += 1
            return ("not", self.unary(depth + 1))
        if self.at("("):
            self.index += 1
            node = self.condition(depth + 1)
            kind, value, position = self.take('")"')
            if (kind, value) != ("sym", ")"):
                raise _error('Expected ")"', position)
            return node
        return self.predicate()

    def symbol(self, allowed: str, expected: str) -> str:
        """Consume one of the allowed symbols; raise ValueError otherwise."""
        kind, value, position = self.take(expected)
        if kind != "sym" or value not in allowed:
            raise _error(f"Expected {expected}", position)
        return value

    def string(self, expected: str) -> Tuple[str, int]:
        """Consume a quoted string and return (text, position)."""
        kind, value, position = self.take(expected)
        if kind != "str":
            raise _error(f"Expected {expected} in double quotes", position)
        return value, position

    def predicate(self) -> Condition:
        """predicate := type = NAME | TEXT_FIELD contains STRING | TIME_FIELD op STRING"""
        kind, word, position = self.take("a field name or type")
        field = word.lower()
        if kind != "word":
            raise _error("Expected a field name or type", position)
        if field == "type":
            self.symbol("=", '"="')
            kind, name, name_position = self.take("a record type")
            if kind != "word" or name.lower() not in FIELDS:
                raise _error(f"Type must be one of: {', '.join(FIELDS)}", name_position)
            return ("type", name.lower())
        if field in TEXT_FIELDS:
            kind, keyword, keyword_position = self.take('"contains"')
            if kind != "word" or keyword.lower() != "contains":
                raise _error(f'Expected "contains" after {field}', keyword_position)
            return ("contains", field, self.string("text to find")[0])
        if field in TIME_FIELDS:
            operator = self.symbol("<=>", "one of < = >")
            value, value_position = self.string('a time like "2026-12-01 09:00"')
            try:
                check_time(value)
            except ValueError as error:
                raise _error(str(error), value_position) from None
            return ("time", field, operator, value)
        valid = ", ".join(("type",) + TEXT_FIELDS + TIME_FIELDS)
        raise _error(f"Unknown field {word!r}. Valid fields: {valid}", position)


def parse_condition(text: str) -> Condition:
    """Parse a typed condition into a tuple accepted by model.search.search_records.

    Raises:
        ValueError: the condition is empty or malformed; the message gives a 1-based position.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Enter a condition, for example: type = task && deadline < "
                         '"2026-12-01 09:00"')
    tokens = _tokenize(text)
    parser = _Parser(tokens, len(text.rstrip()))
    node = parser.condition()
    leftover = parser.peek()
    if leftover is not None:
        raise _error(f"Unexpected {leftover[1]!r}; use && or || between conditions", leftover[2])
    return node


def _any_of(conditions: List[Condition]) -> Condition:
    """Join conditions with "or" in a balanced tree, so long lists stay shallow."""
    if len(conditions) == 1:
        return conditions[0]
    middle = len(conditions) // 2
    return ("or", _any_of(conditions[:middle]), _any_of(conditions[middle:]))


def keywords_condition(text: str) -> Condition:
    """Build the quick-search condition: any text field contains any of the phrases.

    Phrases are separated by "|"; matching ignores case. Blank text matches every record.

    Raises:
        ValueError: a phrase between separators is empty, for example "milk |".
    """
    if not text.strip():
        return _any_of([("type", kind) for kind in FIELDS])
    phrases = [part.strip() for part in text.split("|")]
    if not all(phrases):
        raise ValueError("A phrase is empty. Put a phrase on each side of |.")
    return _any_of([("contains", field, phrase) for field in TEXT_FIELDS for phrase in phrases])
