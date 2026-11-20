"""Correção de defeitos de codificação presentes na origem (arquivos latin-1 da Receita).

Defeitos tratados:
- Mojibake: trechos gravados em UTF-8 dentro do arquivo latin-1 ("RaÃ­zes" -> "Raízes").
- Caracteres de controle: TAB/NBSP -> espaço; NUL, DEL, C1 (0x80-0x9F) e hífen invisível removidos;
  SUB (0x1A, "caractere desconhecido") -> "?" para ser tratado como acento perdido.
- Acento perdido na exportação, gravado como "?" ("S?O", "IRM?O", "COM?RCIO"):
  reconstituído a partir de um vocabulário de palavras acentuadas extraído dos próprios arquivos.
  Palavras sem correspondência inequívoca permanecem como estão.
- Apóstrofo gravado como "?" ("KID?S", "D?ALHO") -> "'".
- Ordinal gravado como "?" ("N? 01", "2?ANDAR") -> "º".
- "?" restante sem correspondência segura (ex.: "?" real em "QUE TAL?") é mantido.
"""

import json
import re
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Letras acentuadas em latin-1 (exclui × e ÷).
_ACCENTED = "À-ÖØ-öø-ÿ"
_ACCENTED_BYTES = re.compile(rb"[\xC0-\xD6\xD8-\xF6\xF8-\xFF]+")
_LETTER_BYTES = frozenset(range(0x41, 0x5B)) | frozenset(range(0x61, 0x7B)) | (
    frozenset(range(0xC0, 0x100)) - {0xD7, 0xF7}
)
_ACCENTED_CHAR = re.compile(f"[{_ACCENTED}]")
_TOKEN_WITH_QUESTION = re.compile(f"[A-Za-z{_ACCENTED}]*\\?[A-Za-z{_ACCENTED}?]*")
_MOJIBAKE = re.compile("[Â-ô][\u0080-¿]")
# "KID?S" -> "KID'S". Exclui letras que em português antecedem -ÊS/-ÁS/-ÕES (JAPON?S, INGL?S, PORTUGU?S).
_APOSTROPHE_S = re.compile(r"(?<=[A-Za-z]{2}[ABDFGHIJKMPQRSTVWXYZabdfghijkmpqrstvwxyz])\?(?=[Ss]$)")
# "D?AGUA" -> "D'AGUA", "L?OSPEDALE" -> "L'OSPEDALE".
_APOSTROPHE_PREFIX = re.compile(r"^([DLdl])\?(?=[AEIOUHaeiouh])")
# Ordinal perdido: "N? 01", "APT? 101", "2?ANDAR" -> "Nº 01", "APTº 101", "2ºANDAR".
_ORDINAL = re.compile(r"(\d)\?|\b([A-Za-z]{1,4})\?(?=\s*\d)")

_CONTROL_TABLE = str.maketrans(
    {
        **{c: None for c in [*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x1A), *range(0x1B, 0x20)]},
        0x09: " ",  # TAB
        0x1A: "?",  # SUB: caractere perdido na origem
        0x7F: None,  # DEL
        **{c: None for c in range(0x80, 0xA0)},  # C1 (não imprimíveis)
        0xA0: " ",  # espaço não separável
        0xAD: None,  # hífen invisível
    }
)
_CONTROL_CHARS = frozenset(chr(c) for c in _CONTROL_TABLE)

# Critérios para aceitar uma palavra do vocabulário como correção.
MIN_OCCURRENCES = 3
MIN_SHARE = 0.9


# --------------------------------------------------------------------------- vocabulário


def _skeleton(word: str) -> str:
    return _ACCENTED_CHAR.sub("?", word.upper())


def _scan_accented_words(path: Path) -> Counter:
    words: Counter = Counter()
    with open(path, "rb") as f:
        carry = b""
        while chunk := f.read(64 << 20):
            data = carry + chunk
            cut = data.rfind(b"\n") + 1
            data, carry = data[:cut], data[cut:]
            last_end = 0
            for m in _ACCENTED_BYTES.finditer(data):
                start, end = m.start(), m.end()
                if start < last_end:
                    continue
                while start > 0 and data[start - 1] in _LETTER_BYTES:
                    start -= 1
                while end < len(data) and data[end] in _LETTER_BYTES:
                    end += 1
                last_end = end
                words[data[start:end].decode("latin-1").upper()] += 1
    return words


def build_vocabulary(files: Iterable[Path], workers: int) -> dict[str, str]:
    """Mapeia esqueleto ("S?O") -> palavra acentuada dominante ("SÃO")."""
    totals: Counter = Counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for words in pool.map(_scan_accented_words, files):
            totals.update(words)

    by_skeleton: dict[str, Counter] = {}
    for word, count in totals.items():
        by_skeleton.setdefault(_skeleton(word), Counter())[word] = count

    vocabulary = {}
    for skeleton, candidates in by_skeleton.items():
        (best, best_count), total = candidates.most_common(1)[0], candidates.total()
        if best_count >= MIN_OCCURRENCES and best_count / total >= MIN_SHARE:
            vocabulary[skeleton] = best
    return vocabulary


def load_or_build_vocabulary(path: Path, files: list[Path], workers: int, rebuild: bool) -> dict[str, str]:
    if path.exists() and not rebuild:
        return json.loads(path.read_text(encoding="utf-8"))
    vocabulary = build_vocabulary(files, workers)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vocabulary, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return vocabulary


# --------------------------------------------------------------------------- correção


class TextFixer:
    def __init__(self, vocabulary: dict[str, str] | None):
        self.vocabulary = vocabulary or {}

    def fix(self, value: str, stats: Counter) -> str:
        if _MOJIBAKE.search(value):
            try:
                value = value.encode("latin-1").decode("utf-8")
                stats["enc_mojibake_fixed"] += 1
            except UnicodeError:
                pass  # é latin-1 legítimo (ex.: "NÃO"), não mexe

        if not _CONTROL_CHARS.isdisjoint(value):
            value = value.translate(_CONTROL_TABLE)
            stats["enc_control_chars_fixed"] += 1

        if "?" in value:
            value, n = _ORDINAL.subn(lambda m: (m[1] or m[2]) + "º", value)
            if n:
                stats["enc_ordinal_restored"] += n
            value = _TOKEN_WITH_QUESTION.sub(lambda m: self._repair_token(m[0], stats), value)
        return value

    def _repair_token(self, token: str, stats: Counter) -> str:
        if not any(c.isascii() and c.isalpha() for c in token):
            return token  # "?" isolado ou sem letras: não há o que reconstituir
        candidate = self.vocabulary.get(_skeleton(token))
        if candidate:
            stats["enc_accent_restored"] += 1
            # Vocabulário está em maiúsculas; segue a caixa da letra anterior no texto original.
            return "".join(
                (fix.lower() if i and token[i - 1].islower() else fix) if ch == "?" else ch
                for i, (ch, fix) in enumerate(zip(token, candidate))
            )
        fixed = _APOSTROPHE_PREFIX.sub(r"\1'", _APOSTROPHE_S.sub("'", token))
        stats["enc_apostrophe_restored" if fixed != token else "enc_question_mark_kept"] += 1
        return fixed
