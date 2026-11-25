"""Download dos Dados Abertos do CNPJ a partir do compartilhamento público da Receita Federal.

Os arquivos ficam num compartilhamento Nextcloud (link do tipo ``https://host/index.php/s/<token>``)
com uma pasta por competência (``2026-11/``) contendo os ZIPs (``Empresas0.zip`` ... ``Socios9.zip``).
A listagem usa a interface WebDAV pública do Nextcloud (``/public.php/dav/files/<token>/``),
que informa nome, tamanho, data de modificação e ETag de cada arquivo.

Garantias do download:
- arquivo é baixado como ``<nome>.part`` e só renomeado depois de validado (tamanho + CRC do ZIP);
- download interrompido é retomado de onde parou (HTTP Range); se o servidor ignorar o Range,
  recomeça do zero em vez de corromper o arquivo;
- falhas de rede são repetidas com espera crescente;
- um manifesto (``_manifesto.json``) registra o ETag de cada arquivo validado, de modo que uma nova
  execução não baixa de novo o que já está correto, mas baixa se a Receita republicar o arquivo.
"""

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

DEFAULT_SHARE_URL = "https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9"
MANIFEST_NAME = "_manifesto.json"
COMPETENCIA = re.compile(r"\d{4}-\d{2}")
# Tabelas que precisam estar presentes para a competência ser considerada publicada.
REQUIRED_PREFIXES = (
    "Empresas", "Estabelecimentos", "Socios", "Simples",
    "Cnaes", "Motivos", "Municipios", "Naturezas", "Paises", "Qualificacoes",
)
USER_AGENT = "cnpj-dados-abertos-sync/1.0"
CHUNK = 1 << 20
TIMEOUT = 60  # segundos sem receber dados antes de considerar a conexão perdida

log = logging.getLogger("receita.download")
_DAV = {"d": "DAV:"}
_PROPFIND_BODY = (
    b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
    b"<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><d:getetag/>"
    b"</d:prop></d:propfind>"
)
_NETWORK_ERRORS = (urllib.error.URLError, HTTPException, ConnectionError, TimeoutError, OSError)


class DownloadError(Exception):
    pass


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    is_dir: bool
    size: int
    modified: datetime
    etag: str


def dav_base_url(share_url: str) -> str:
    """``https://host/index.php/s/TOKEN?dir=/x`` -> ``https://host/public.php/dav/files/TOKEN``."""
    parts = urlsplit(share_url)
    match = re.search(r"/s/([^/?#]+)", parts.path)
    if not match:
        raise ValueError(f"link de compartilhamento inválido (esperado .../s/<token>): {share_url}")
    return f"{parts.scheme}://{parts.netloc}/public.php/dav/files/{match[1]}"


def parse_propfind(xml_bytes: bytes) -> list[RemoteEntry]:
    """Entradas de uma resposta PROPFIND (Depth: 1), sem a própria pasta consultada."""
    entries = []
    responses = ET.fromstring(xml_bytes).findall("d:response", _DAV)
    for response in responses[1:]:  # o primeiro item é a pasta consultada
        href = unquote(response.findtext("d:href", "", _DAV)).rstrip("/")
        prop = response.find("d:propstat/d:prop", _DAV)
        if prop is None:
            continue
        modified = prop.findtext("d:getlastmodified", "", _DAV)
        entries.append(
            RemoteEntry(
                name=href.rsplit("/", 1)[-1],
                is_dir=prop.find("d:resourcetype/d:collection", _DAV) is not None,
                size=int(prop.findtext("d:getcontentlength", "0", _DAV) or 0),
                modified=parsedate_to_datetime(modified) if modified else datetime.min.replace(tzinfo=timezone.utc),
                etag=prop.findtext("d:getetag", "", _DAV).strip('"'),
            )
        )
    return entries


def _request(url: str, method: str = "GET", headers: dict | None = None, data: bytes | None = None):
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _with_retries(action, what: str, attempts: int):
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except _NETWORK_ERRORS as exc:
            permanent = isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code not in (408, 429)
            if permanent or attempt == attempts:
                raise DownloadError(f"{what}: {exc!r}") from exc
            wait = min(300, 10 * 2 ** (attempt - 1))
            log.warning("%s falhou (%r); tentativa %d/%d em %ds", what, exc, attempt + 1, attempts, wait)
            time.sleep(wait)
    raise AssertionError("inalcançável")


class ReceitaShare:
    def __init__(self, share_url: str = DEFAULT_SHARE_URL, attempts: int = 5):
        self.base = dav_base_url(share_url)
        self.attempts = attempts

    def url(self, *parts: str) -> str:
        return "/".join([self.base, *(quote(p) for p in parts)])

    def list_dir(self, *parts: str) -> list[RemoteEntry]:
        def propfind():
            with _request(self.url(*parts) + "/", "PROPFIND", {"Depth": "1", "Content-Type": "application/xml"},
                          _PROPFIND_BODY) as resp:
                return resp.read()

        return parse_propfind(_with_retries(propfind, f"listagem de /{'/'.join(parts)}", self.attempts))

    def releases(self) -> list[RemoteEntry]:
        """Pastas de competência (AAAA-MM), da mais antiga para a mais recente."""
        return sorted((e for e in self.list_dir() if e.is_dir and COMPETENCIA.fullmatch(e.name)), key=lambda e: e.name)

    def release_files(self, competencia: str) -> list[RemoteEntry]:
        return sorted((e for e in self.list_dir(competencia) if not e.is_dir), key=lambda e: e.name)


def missing_tables(files: Iterable[RemoteEntry]) -> list[str]:
    """Tabelas obrigatórias sem nenhum arquivo na competência."""
    names = [f.name for f in files]
    return [p for p in REQUIRED_PREFIXES if not any(re.fullmatch(rf"{p}\d*\.zip", n) for n in names)]


# --------------------------------------------------------------------------- download


def read_manifest(folder: Path) -> dict[str, dict]:
    try:
        return json.loads((folder / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def is_current(folder: Path, entry: RemoteEntry, manifest: dict[str, dict]) -> bool:
    """O arquivo local é a mesma versão do remoto e já foi validado."""
    local = folder / entry.name
    record = manifest.get(entry.name)
    return (
        record is not None
        and local.exists()
        and local.stat().st_size == entry.size
        and record.get("etag") == entry.etag
    )


def verify_zip(path: Path) -> None:
    """Lê o ZIP inteiro conferindo o CRC de cada arquivo interno."""
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        raise DownloadError(f"{path.name}: ZIP inválido ({exc!r})") from exc
    if bad is not None:
        raise DownloadError(f"{path.name}: CRC incorreto em {bad}")


def _fetch(url: str, part: Path, size: int) -> None:
    """Uma tentativa de download, retomando ``part`` se já houver bytes baixados."""
    offset = part.stat().st_size if part.exists() else 0
    if offset > size:
        part.unlink()
        offset = 0
    if offset == size:
        return
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with _request(url, headers=headers) as resp:
        if offset and resp.status != 206:
            log.info("%s: servidor ignorou a retomada; baixando do início", part.name)
            offset = 0
        elif offset and not resp.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise DownloadError(f"{part.name}: Content-Range inesperado: {resp.headers.get('Content-Range')}")
        with open(part, "r+b" if offset else "wb") as out:
            out.seek(offset)
            out.truncate()
            while chunk := resp.read(CHUNK):
                out.write(chunk)
    if (got := part.stat().st_size) != size:
        raise ConnectionError(f"{part.name}: recebidos {got:,} de {size:,} bytes")


def download_file(url: str, target: Path, size: int, attempts: int = 5) -> None:
    """Baixa ``url`` para ``target`` com retomada, retentativas e validação do ZIP."""
    part = target.with_name(target.name + ".part")
    for attempt in range(1, attempts + 1):
        _with_retries(lambda: _fetch(url, part, size), f"download de {target.name}", attempts)
        try:
            verify_zip(part)
        except DownloadError as exc:
            part.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            log.warning("%s; baixando de novo (%d/%d)", exc, attempt + 1, attempts)
            continue
        os.replace(part, target)
        return


def download_release(
    share: ReceitaShare,
    competencia: str,
    files: list[RemoteEntry],
    folder: Path,
    workers: int = 4,
) -> dict[str, dict]:
    """Baixa os ``files`` da competência para ``folder``, pulando os que já estão corretos."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(folder)
    lock = threading.Lock()
    pending = [e for e in files if not is_current(folder, e, manifest)]
    skipped = len(files) - len(pending)
    total = sum(e.size for e in pending)
    log.info("Competência %s: %d arquivo(s) a baixar (%.2f GB); %d já baixado(s)",
             competencia, len(pending), total / 1e9, skipped)

    def one(entry: RemoteEntry) -> None:
        started = time.perf_counter()
        download_file(share.url(competencia, entry.name), folder / entry.name, entry.size, share.attempts)
        elapsed = time.perf_counter() - started
        log.info("  ok  %s (%.1f MB em %.0fs, %.1f MB/s)", entry.name, entry.size / 1e6, elapsed,
                 entry.size / 1e6 / max(elapsed, 1e-3))
        with lock:  # manifesto gravado a cada arquivo: uma interrupção não perde o progresso
            record = asdict(entry) | {"modified": entry.modified.isoformat(), "validado_em": datetime.now().isoformat()}
            manifest[entry.name] = record
            tmp = folder / (MANIFEST_NAME + ".tmp")
            tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            os.replace(tmp, folder / MANIFEST_NAME)

    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Maiores primeiro, para não terminar com um único download gigante em andamento.
        futures = {pool.submit(one, e): e for e in sorted(pending, key=lambda e: e.size, reverse=True)}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures[futures[future].name] = repr(exc)
                log.error("falha no download de %s: %r", futures[future].name, exc)
    if failures:
        raise DownloadError(f"{len(failures)} arquivo(s) não baixado(s): {', '.join(sorted(failures))}")
    return manifest
