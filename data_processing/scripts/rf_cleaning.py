"""Regras de limpeza aplicadas a cada registro dos arquivos da Receita Federal.

Funções puras (sem I/O) para facilitar testes:
- leitura tolerante a ";" e quebras de linha dentro de campos (``iter_records``);
- normalização de datas para AAAAMMDD; vazias/inválidas viram NULL (``normalize_date``);
- vírgula decimal -> ponto (``normalize_decimal``);
- correção de codificação (``rf_encoding.TextFixer``);
- vazio -> NULL (``None``) e formatação de saída com todos os valores como texto (``format_line``).
"""

import csv
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import date
from functools import lru_cache

from rf_encoding import TextFixer

# Máximo de linhas físicas que um único registro pode ocupar antes de ser descartado.
MAX_PHYSICAL_LINES_PER_RECORD = 5

_NEWLINES = re.compile(r"\s*(?:\r\n|\r|\n)\s*")
_BR_DATE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_COMPACT_DATE = re.compile(r"\d{8}")
_ZERO_DATE = re.compile(r"0+")
_DECIMAL = re.compile(r"-?\d+(\.\d+)?")


# --------------------------------------------------------------------------- datas


def _valid(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


@lru_cache(maxsize=200_000)
def normalize_date(value: str) -> tuple[str | None, str]:
    """Converte uma data para AAAAMMDD.

    Retorna (valor_normalizado, status); ``None`` representa NULL. Status:
      "empty"   -> vazio / zeros  -> NULL
      "ok"      -> já estava em AAAAMMDD válido
      "br"      -> estava em DD/MM/AAAA (também aceita "-" e ".") e foi convertida
      "iso"     -> estava em AAAA-MM-DD e foi convertida
      "invalid" -> não é uma data válida -> NULL
    """
    v = value.strip()
    if not v or _ZERO_DATE.fullmatch(v):
        return None, "empty"

    if _COMPACT_DATE.fullmatch(v):
        if _valid(int(v[:4]), int(v[4:6]), int(v[6:])):
            return v, "ok"
        return None, "invalid"

    if m := _BR_DATE.fullmatch(v):
        day, month, year = int(m[1]), int(m[2]), int(m[3])
        if _valid(year, month, day):
            return f"{year:04d}{month:02d}{day:02d}", "br"
        return None, "invalid"

    if m := _ISO_DATE.fullmatch(v):
        year, month, day = int(m[1]), int(m[2]), int(m[3])
        if _valid(year, month, day):
            return f"{year:04d}{month:02d}{day:02d}", "iso"

    return None, "invalid"


# --------------------------------------------------------------------------- decimais


def normalize_decimal(value: str) -> str | None:
    """'1.234,56' / '1234,56' -> '1234.56'. Retorna None se não for um número."""
    v = value.strip()
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    return v if _DECIMAL.fullmatch(v) else None


# --------------------------------------------------------------------------- leitura


def _glue(left: str, right: str) -> str:
    """Une as duas metades de um campo que foi partido por uma quebra de linha."""
    return f"{left} {right}" if left and right else left + right


def iter_records(
    lines: Iterable[str], n_fields: int, stats: Counter, rejects: list[tuple[int, list[str]]]
) -> Iterator[list[str]]:
    """Lê registros ``"campo";"campo"`` respeitando aspas.

    - ";" dentro de aspas faz parte do valor (não é separador).
    - Quebra de linha dentro de aspas é tratada pelo parser CSV (o registro continua).
    - Quebra de linha FORA de aspas (registro partido em 2+ linhas físicas) gera um
      registro com menos colunas; ele é unido às linhas seguintes até completar ``n_fields``.
    - Registros que não fecham com ``n_fields`` colunas vão para ``rejects``.

    ``lines`` deve ser um arquivo aberto com ``newline=""``.
    """
    reader = csv.reader(lines, delimiter=";", quotechar='"', doublequote=True, strict=False)
    pending: list[str] | None = None
    pending_start = 0
    pending_span = 0
    last_line = 0

    for row in reader:
        start, last_line = last_line + 1, reader.line_num
        span = last_line - start + 1
        if not row:  # linha em branco
            continue

        if pending is not None:
            merged = pending[:-1] + [_glue(pending[-1], row[0])] + row[1:]
            if len(merged) <= n_fields:
                row, start, span = merged, pending_start, pending_span + span
            else:
                # A linha atual é um registro novo; o pendente estava truncado.
                rejects.append((pending_start, pending))
                stats["rejected"] += 1
            pending = None

        if len(row) == n_fields:
            if span > 1:
                stats["multiline_records"] += 1
            yield row
        elif len(row) < n_fields and span < MAX_PHYSICAL_LINES_PER_RECORD:
            pending, pending_start, pending_span = row, start, span
        else:
            rejects.append((start, row))
            stats["rejected"] += 1

    if pending is not None:
        rejects.append((pending_start, pending))
        stats["rejected"] += 1


# --------------------------------------------------------------------------- transformação

KIND_TEXT, KIND_DATE, KIND_DECIMAL = 0, 1, 2


def column_kinds(n_fields: int, date_idx: frozenset[int], decimal_idx: frozenset[int]) -> tuple[int, ...]:
    return tuple(
        KIND_DATE if i in date_idx else KIND_DECIMAL if i in decimal_idx else KIND_TEXT
        for i in range(n_fields)
    )


def clean_record(
    row: list[str], kinds: tuple[int, ...], stats: Counter, fixer: TextFixer | None = None
) -> list[str | None]:
    """Aplica as regras de limpeza a um registro. ``None`` representa NULL."""
    out: list[str | None] = []
    for value, kind in zip(row, kinds):
        if "\n" in value or "\r" in value:
            value = _NEWLINES.sub(" ", value).strip()
            stats["newlines_in_field"] += 1

        if kind == KIND_DATE:
            value, status = normalize_date(value)
            if status != "ok":
                stats[f"date_{status}"] += 1
            if value is None:
                stats["nulls"] += 1
            out.append(value)
            continue

        # Atalho: a grande maioria dos valores é ASCII imprimível sem "?" e não precisa de correção.
        if fixer is not None and (not value.isascii() or not value.isprintable() or "?" in value):
            value = fixer.fix(value, stats)

        if not value.strip():
            stats["nulls"] += 1
            out.append(None)
        elif kind == KIND_DECIMAL:
            normalized = normalize_decimal(value)
            if normalized is None:
                stats["decimal_invalid"] += 1
            out.append(normalized)
        else:
            out.append(value)  # códigos permanecem texto: zeros à esquerda preservados
    return out


def format_line(values: Iterable[str | None], delimiter: str, null_marker: str) -> str:
    """Todo valor não nulo sai entre aspas (texto); NULL sai sem aspas como ``null_marker``."""
    return (
        delimiter.join(
            null_marker if v is None else '"' + v.replace('"', '""') + '"' for v in values
        )
        + "\n"
    )
