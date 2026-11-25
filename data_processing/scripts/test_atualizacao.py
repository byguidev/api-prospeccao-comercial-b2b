"""Testes da leitura dos ZIPs, do download e da atualização mensal.

Executar: python -m unittest discover data_processing/scripts
"""

import json
import os
import tempfile
import threading
import unittest
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import atualizar_receita
from atualizar_receita import prune
from process_receita import Options, processar
from rf_layout import LAYOUTS
from rf_download import (
    DownloadError,
    ReceitaShare,
    RemoteEntry,
    dav_base_url,
    download_file,
    download_release,
    missing_tables,
    parse_propfind,
)
from rf_source import discover_sources, table_for_zip


def make_zip(path: Path, member: str, content: bytes) -> bytes:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, content)
    return path.read_bytes()


class SourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_table_from_zip_name(self):
        self.assertEqual(table_for_zip("Estabelecimentos3.zip"), "estabelecimentos")
        self.assertEqual(table_for_zip("Simples.zip"), "simples")
        self.assertEqual(table_for_zip("Qualificacoes.zip"), "qualificacoes")
        self.assertIsNone(table_for_zip("cnpj.tar.gz"))
        self.assertIsNone(table_for_zip("Outra1.zip"))

    def test_discover_reads_zip_member_and_ignores_auxiliary_files(self):
        make_zip(self.dir / "Cnaes.zip", "F.K03200$Z.D61114.CNAECSV", '"0111301";"Cultivo de arroz"\n'.encode("latin-1"))
        (self.dir / "Empresas0.zip.part").write_bytes(b"incompleto")
        (self.dir / "_manifesto.json").write_text("{}")

        sources = discover_sources(self.dir)

        self.assertEqual([(s.table, s.member, s.output_stem) for s in sources],
                         [("cnaes", "F.K03200$Z.D61114.CNAECSV", "Cnaes")])
        with sources[0].open_text("latin-1") as f:
            self.assertEqual(f.read(), '"0111301";"Cultivo de arroz"\n')

    def test_processing_straight_from_zip(self):
        rows = (
            '"00000000";"BANCO DO BRASIL S?O PAULO";"2038";"10";"1000,50";"05";""\n'
            '"00000001";"SÃO SÃO SÃO";"";"";"";"";""\n'  # "SÃO" frequente: entra no vocabulário de acentos
        )
        (self.dir / "in").mkdir()
        make_zip(self.dir / "in" / "Empresas0.zip", "K3241.K03200Y0.D61114.EMPRECSV", rows.encode("latin-1"))

        report = processar(Options(input=self.dir / "in", output=self.dir / "out", workers=1))

        lines = (self.dir / "out" / "empresas" / "Empresas0.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[1], '"00000000";"BANCO DO BRASIL SÃO PAULO";"2038";"10";"1000.50";"05";NULL')
        self.assertEqual(report["tabelas"]["empresas"]["records"], 2)
        self.assertEqual(report["arquivos"]["empresas/Empresas0"]["origem"], "Empresas0.zip/K3241.K03200Y0.D61114.EMPRECSV")
        self.assertEqual(report["erros"], {})


PROPFIND_SAMPLE = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
 <d:response><d:href>/public.php/dav/files/TOKEN/2026-11/</d:href><d:propstat><d:prop>
  <d:getlastmodified>Mon, 16 Nov 2026 10:10:13 GMT</d:getlastmodified><d:resourcetype><d:collection/></d:resourcetype>
 </d:prop></d:propstat></d:response>
 <d:response><d:href>/public.php/dav/files/TOKEN/2026-11/Cnaes.zip</d:href><d:propstat><d:prop>
  <d:getlastmodified>Mon, 16 Nov 2026 10:00:23 GMT</d:getlastmodified><d:getcontentlength>22078</d:getcontentlength>
  <d:resourcetype/><d:getetag>&quot;87d5&quot;</d:getetag>
 </d:prop></d:propstat></d:response>
 <d:response><d:href>/public.php/dav/files/TOKEN/2026-11/Sub%20Pasta/</d:href><d:propstat><d:prop>
  <d:getlastmodified>Mon, 16 Nov 2026 10:00:00 GMT</d:getlastmodified><d:resourcetype><d:collection/></d:resourcetype>
 </d:prop></d:propstat></d:response>
</d:multistatus>"""


class ListingTest(unittest.TestCase):
    def test_dav_url_from_browser_link(self):
        self.assertEqual(
            dav_base_url("https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9?dir=/2026-11"),
            "https://arquivos.receitafederal.gov.br/public.php/dav/files/YggdBLfdninEJX9",
        )
        with self.assertRaises(ValueError):
            dav_base_url("https://arquivos.receitafederal.gov.br/dados/cnpj/")

    def test_parse_propfind(self):
        entries = parse_propfind(PROPFIND_SAMPLE)
        self.assertEqual([(e.name, e.is_dir, e.size, e.etag) for e in entries],
                         [("Cnaes.zip", False, 22078, "87d5"), ("Sub Pasta", True, 0, "")])
        self.assertEqual(entries[0].modified, datetime(2026, 11, 16, 10, 0, 23, tzinfo=timezone.utc))

    def test_missing_tables(self):
        def entry(name):
            return RemoteEntry(name, False, 1, datetime.now(timezone.utc), "e")

        complete = [entry(n) for n in ("Empresas0.zip", "Estabelecimentos0.zip", "Socios0.zip", "Simples.zip",
                                       "Cnaes.zip", "Motivos.zip", "Municipios.zip", "Naturezas.zip",
                                       "Paises.zip", "Qualificacoes.zip")]
        self.assertEqual(missing_tables(complete), [])
        self.assertEqual(missing_tables(complete[:3]), ["Simples", "Cnaes", "Motivos", "Municipios", "Naturezas",
                                                        "Paises", "Qualificacoes"])


class _Server:
    """Servidor HTTP local que serve ``files`` com suporte (opcional) a Range."""

    def __init__(self, files: dict[str, bytes], honor_range: bool = True):
        server = self
        self.files, self.honor_range, self.requests = files, honor_range, []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = server.files[self.path.rsplit("/", 1)[-1]]
                rng = self.headers.get("Range")
                server.requests.append(rng)
                start = int(rng[6:].split("-")[0]) if rng and server.honor_range else 0
                payload = body[start:]
                self.send_response(206 if start else 200)
                if start:
                    self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        content = os.urandom(20_000).hex().encode()  # pouco compressível: ZIP com ~20 KB
        self.body = make_zip(self.dir / "origem.zip", "F.K03200$Z.D61114.MOTICSV", content)

    def tearDown(self):
        self.tmp.cleanup()

    def serve(self, **kwargs) -> _Server:
        server = _Server({"Motivos.zip": self.body}, **kwargs)
        self.addCleanup(server.close)
        return server

    def test_resumes_partial_download(self):
        server = self.serve()
        target = self.dir / "Motivos.zip"
        (self.dir / "Motivos.zip.part").write_bytes(self.body[:1000])

        download_file(f"{server.url}/Motivos.zip", target, len(self.body))

        self.assertEqual(target.read_bytes(), self.body)
        self.assertEqual(server.requests, ["bytes=1000-"])
        self.assertFalse((self.dir / "Motivos.zip.part").exists())

    def test_restarts_when_server_ignores_range(self):
        server = self.serve(honor_range=False)
        target = self.dir / "Motivos.zip"
        (self.dir / "Motivos.zip.part").write_bytes(b"lixo de uma tentativa anterior")

        download_file(f"{server.url}/Motivos.zip", target, len(self.body))

        self.assertEqual(target.read_bytes(), self.body)

    def test_corrupted_zip_is_rejected(self):
        corrupted = bytearray(self.body)
        corrupted[60] ^= 0xFF  # altera um byte dos dados comprimidos
        server = _Server({"Motivos.zip": bytes(corrupted)})
        self.addCleanup(server.close)
        target = self.dir / "Motivos.zip"

        with self.assertRaises(DownloadError):
            download_file(f"{server.url}/Motivos.zip", target, len(corrupted), attempts=2)
        self.assertFalse(target.exists())
        self.assertEqual(len(server.requests), 2)

    def test_release_download_skips_files_already_validated(self):
        server = self.serve()
        share = ReceitaShare("https://exemplo/index.php/s/TOKEN")
        share.url = lambda *parts: f"{server.url}/{parts[-1]}"
        entry = RemoteEntry("Motivos.zip", False, len(self.body), datetime.now(timezone.utc), "v1")
        folder = self.dir / "2026-11"

        download_release(share, "2026-11", [entry], folder)
        download_release(share, "2026-11", [entry], folder)  # já validado: nenhum novo download
        self.assertEqual(len(server.requests), 1)

        republished = RemoteEntry("Motivos.zip", False, len(self.body), entry.modified, "v2")
        download_release(share, "2026-11", [republished], folder)  # ETag mudou: baixa de novo
        self.assertEqual(len(server.requests), 2)
        self.assertEqual(json.loads((folder / "_manifesto.json").read_text())["Motivos.zip"]["etag"], "v2")


class RetentionTest(unittest.TestCase):
    def test_keeps_latest_and_ignores_other_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "receita-federal-2026-11"):
                (root / name).mkdir()

            prune(root, keep=2, current="2026-11")

            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             ["2026-10", "2026-11", "2026-12", "receita-federal-2026-11"])


class _FakeShare:
    """Compartilhamento da Receita simulado: lista ``entries`` e serve os arquivos pelo ``_Server``."""

    attempts = 1

    def __init__(self, server: _Server, entries: list[RemoteEntry]):
        self.server, self.entries = server, entries

    def releases(self):
        return [RemoteEntry("2026-10", True, 0, OLD, ""), RemoteEntry("2026-11", True, 0, OLD, "")]

    def release_files(self, competencia):
        return list(self.entries)

    def url(self, *parts):
        return f"{self.server.url}/{parts[-1]}"


OLD = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
PARTITIONED = {"empresas", "estabelecimentos", "socios"}


class UpdateFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        files = {}
        for table, layout in LAYOUTS.items():
            name = table.capitalize() + ("0" if table in PARTITIONED else "") + ".zip"
            row = ";".join(f'"{i}"' for i in range(len(layout.columns))) + "\n"
            files[name] = make_zip(self.dir / name, f"ARQUIVO.{table.upper()}", row.encode("latin-1"))
        self.server = _Server(files)
        self.addCleanup(self.server.close)
        self.entries = [RemoteEntry(n, False, len(b), OLD, "v1") for n, b in sorted(files.items())]

    def update(self, entries=None, extra=(), carregar_side_effect=None) -> int:
        share = _FakeShare(self.server, self.entries if entries is None else entries)
        args = atualizar_receita.parse_args([
            "--data-dir", str(self.dir / "data"), "--output-dir", str(self.dir / "output"),
            "--log-dir", str(self.dir / "logs"), "--workers", "1", *extra,
        ])
        # A carga no PostgreSQL é sempre simulada aqui: nenhum psql roda.
        with mock.patch.object(atualizar_receita, "ReceitaShare", lambda url: share), \
                mock.patch.object(atualizar_receita, "Banco") as banco, \
                mock.patch.object(atualizar_receita, "carregar", side_effect=carregar_side_effect) as carregar:
            self.banco, self.carregar = banco, carregar
            return atualizar_receita.run(args)

    def state(self) -> dict:
        return json.loads((self.dir / "output" / "2026-11" / "_atualizacao.json").read_text(encoding="utf-8"))

    def test_full_cycle_then_nothing_to_do(self):
        self.assertEqual(self.update(), 0)
        self.assertEqual(len(self.server.requests), 10)
        self.assertEqual(self.state()["status"], "concluido")
        self.assertEqual(self.state()["registros"], {t: 1 for t in LAYOUTS})
        self.assertTrue((self.dir / "output" / "2026-11" / "empresas" / "Empresas0.csv").exists())

        with self.assertLogs("receita.atualizacao") as logs:
            self.assertEqual(self.update(), 0)
        self.assertIn("nada a fazer", "\n".join(logs.output))
        self.assertEqual(len(self.server.requests), 10)  # nada baixado de novo

    def test_database_is_not_touched_without_the_flag(self):
        self.update()
        self.update()
        self.carregar.assert_not_called()

    def test_database_load_runs_after_processing_and_is_rechecked_on_idle_days(self):
        self.update(extra=["--carregar-banco"])
        self.carregar.assert_called_once()
        args, kwargs = self.carregar.call_args
        self.assertEqual(args[1:3], (self.dir / "output" / "2026-11", "2026-11"))
        self.assertEqual(args[3], self.state()["etags"])  # assinatura dos arquivos publicados
        self.assertFalse(kwargs["force"])
        self.assertTrue((self.dir / "output" / "2026-11" / "relatorio_processamento.json").exists())

        # dia seguinte, nada novo: não baixa nem trata, mas confere o banco (retoma carga interrompida)
        self.update(extra=["--carregar-banco"])
        self.carregar.assert_called_once()
        self.assertEqual(len(self.server.requests), 10)

    def test_database_failure_fails_the_run_and_is_retried_next_time(self):
        with self.assertRaises(RuntimeError):
            self.update(extra=["--carregar-banco"], carregar_side_effect=RuntimeError("banco fora do ar"))
        self.assertEqual(self.state()["status"], "concluido")  # o tratamento não se perde

        self.update(extra=["--carregar-banco"])  # sem baixar/tratar de novo, só a carga
        self.carregar.assert_called_once()
        self.assertEqual(len(self.server.requests), 10)

    def test_republished_file_reloads_the_database(self):
        self.update(extra=["--carregar-banco"])
        changed = [RemoteEntry(e.name, e.is_dir, e.size, e.modified, "v2" if e.name == "Cnaes.zip" else e.etag)
                   for e in self.entries]
        self.update(changed, extra=["--carregar-banco"])
        etags = self.carregar.call_args.args[3]
        self.assertEqual(etags["Cnaes.zip"], "v2")  # nova assinatura => o banco será esvaziado e recarregado

    def test_partial_runs_never_load_the_database(self):
        self.update(extra=["--carregar-banco", "--tables", "cnaes", "--limit", "1"])
        self.carregar.assert_not_called()

    def test_force_is_passed_to_the_loader(self):
        self.update()
        self.update(extra=["--carregar-banco", "--force"])
        self.assertTrue(self.carregar.call_args.kwargs["force"])

    def test_republished_file_is_downloaded_and_processed_again(self):
        self.update()
        changed = [RemoteEntry(e.name, e.is_dir, e.size, e.modified, "v2" if e.name == "Cnaes.zip" else e.etag)
                   for e in self.entries]

        self.assertEqual(self.update(changed), 0)

        self.assertEqual(len(self.server.requests), 11)  # só o arquivo republicado
        self.assertEqual(self.state()["etags"]["Cnaes.zip"], "v2")

    def test_waits_while_release_is_incomplete(self):
        without_socios = [e for e in self.entries if not e.name.startswith("Socios")]
        with self.assertLogs("receita.atualizacao") as logs:
            self.assertEqual(self.update(without_socios), 0)
        self.assertIn("incompleta (faltam: Socios)", "\n".join(logs.output))
        self.assertEqual(self.server.requests, [])

    def test_waits_while_upload_is_recent(self):
        recent = [RemoteEntry(e.name, e.is_dir, e.size, datetime.now(timezone.utc), e.etag) for e in self.entries]
        with self.assertLogs("receita.atualizacao") as logs:
            self.assertEqual(self.update(recent), 0)
        self.assertIn("upload possivelmente em andamento", "\n".join(logs.output))
        self.assertEqual(self.server.requests, [])


if __name__ == "__main__":
    unittest.main()
