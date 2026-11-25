"""Localiza os arquivos de uma competência da Receita Federal e dá acesso uniforme a eles.

A entrada padrão é a pasta da competência exatamente como baixada do site da Receita:

    data/raw/2026-11/
    ├── Cnaes.zip            -> F.K03200$Z.D61114.CNAECSV
    ├── Empresas0.zip        -> K3241.K03200Y0.D61114.EMPRECSV
    ├── ...
    └── Socios9.zip          -> K3241.K03200Y9.D61114.SOCIOCSV

Cada ZIP é lido diretamente (sem extrair para o disco). A tabela é identificada pelo nome do ZIP
("Estabelecimentos3.zip" -> estabelecimentos) e, se não bater, pelo nome do arquivo interno.
Arquivos já extraídos (soltos) continuam aceitos, identificados pela pasta ou pelo nome.
"""

import io
import logging
import re
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from rf_layout import LAYOUTS, detect_layout

# Arquivos que podem estar na pasta da competência e não são dados (download em andamento, manifestos).
IGNORED_SUFFIXES = frozenset({".part", ".json", ".log", ".tmp"})
_ZIP_TABLE = re.compile(r"([A-Za-z]+)\d*")
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    path: Path  # arquivo no disco: o ZIP ou o arquivo solto
    member: str | None  # nome do arquivo dentro do ZIP; None para arquivo solto
    table: str
    size: int  # tamanho descompactado, em bytes

    @property
    def label(self) -> str:
        """Identificação legível: "Empresas0.zip/K3241.K03200Y0.D61114.EMPRECSV"."""
        return f"{self.path.name}/{self.member}" if self.member else self.path.name

    @property
    def output_stem(self) -> str:
        """Nome base do arquivo gerado: o nome do ZIP ("Empresas0") ou do arquivo solto."""
        return self.path.stem if self.member else self.path.name

    @contextmanager
    def open_binary(self) -> Iterator[IO[bytes]]:
        if self.member is None:
            with open(self.path, "rb") as f:
                yield f
        else:
            # ZipExtFile confere o CRC ao chegar ao fim do arquivo: leitura corrompida gera erro.
            with zipfile.ZipFile(self.path) as archive, archive.open(self.member) as f:
                yield f

    @contextmanager
    def open_text(self, encoding: str) -> Iterator[IO[str]]:
        with self.open_binary() as raw:
            yield io.TextIOWrapper(raw, encoding=encoding, newline="")


def table_for_zip(zip_name: str) -> str | None:
    """"Estabelecimentos3.zip" -> "estabelecimentos"; None se o nome não corresponder a uma tabela."""
    match = _ZIP_TABLE.fullmatch(Path(zip_name).stem)
    if match and match[1].lower() in LAYOUTS:
        return match[1].lower()
    return None


def _zip_sources(path: Path) -> list[Source]:
    with zipfile.ZipFile(path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
    sources = []
    for info in members:
        table = table_for_zip(path.name)
        if table is None:
            layout = detect_layout("", info.filename)
            table = layout.name if layout else None
        if table is None:
            log.warning("tabela não identificada, ignorando: %s/%s", path.name, info.filename)
            continue
        sources.append(Source(path, info.filename, table, info.file_size))
    return sources


def discover_sources(input_dir: Path) -> list[Source]:
    """Todos os arquivos de dados de ``input_dir``: membros de ZIPs e arquivos soltos."""
    sources: list[Source] = []
    for path in sorted(p for p in input_dir.rglob("*") if p.is_file()):
        if path.suffix.lower() in IGNORED_SUFFIXES or path.name.startswith(("_", ".")):
            continue
        if path.suffix.lower() == ".zip":
            sources.extend(_zip_sources(path))
            continue
        layout = detect_layout(path.parent.name, path.name)
        if layout is None:
            log.warning("tabela não identificada, ignorando: %s", path)
            continue
        sources.append(Source(path, None, layout.name, path.stat().st_size))
    return sources
