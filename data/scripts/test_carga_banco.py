"""Testes da carga no PostgreSQL. Usam um banco simulado: nenhum psql é executado de verdade.

Executar: python -m unittest discover data/scripts
"""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import carregar_banco as cb
from carregar_banco import Banco, DbConfig, EstadoCarga, LOAD_ORDER, LoadError, carregar
from rf_layout import LAYOUTS

COMPETENCIA = "2026-11"
ETAGS = {"Empresas0.zip": "a", "Empresas1.zip": "b"}
ASSINATURA = cb.assinatura_de(ETAGS)

# CSVs de cada tabela e quantos registros cada um tem (o conteúdo dos arquivos não importa aqui).
ARQUIVOS = {
    "cnaes": {"Cnaes": 3}, "motivos": {"Motivos": 3}, "municipios": {"Municipios": 3},
    "naturezas": {"Naturezas": 3}, "paises": {"Paises": 3}, "qualificacoes": {"Qualificacoes": 3},
    "empresas": {"Empresas0": 5, "Empresas1": 4}, "estabelecimentos": {"Estabelecimentos0": 7},
    "socios": {"Socios0": 2}, "simples": {"Simples": 1},
}
ESPERADO = {t: sum(f.values()) for t, f in ARQUIVOS.items()}
LINHAS_POR_CSV = {f"{stem}.csv": n for files in ARQUIVOS.values() for stem, n in files.items()}


def make_output(root: Path, erros: dict | None = None, skip_csv: str | None = None) -> Path:
    out = root / COMPETENCIA
    for tabela, files in ARQUIVOS.items():
        (out / tabela).mkdir(parents=True)
        for stem in files:
            if f"{stem}.csv" != skip_csv:
                (out / tabela / f"{stem}.csv").write_text("x", encoding="utf-8")
    report = {
        "tabelas": {t: {"records": n} for t, n in ESPERADO.items()},
        "arquivos": {f"{t}/{stem}": {"records": n} for t, files in ARQUIVOS.items() for stem, n in files.items()},
        "erros": erros or {},
    }
    (out / "relatorio_processamento.json").write_text(json.dumps(report), encoding="utf-8")
    return out


class FakeBanco:
    """Banco em memória com a mesma interface de Banco; registra o que foi feito."""

    def __init__(self, atual=None, contagens=None, ausentes=(), falha_em=None, objetos_pendentes=(), pausa=0.0):
        self.eventos: list = []
        self.atual = atual
        self.tabelas = dict(contagens or {t: 0 for t in LOAD_ORDER})
        self.carregados: set[str] = set()
        self.ausentes = list(ausentes)
        self.falha_em = falha_em
        self.objetos = list(objetos_pendentes)  # (tabela, nome) retirados e ainda não recriados
        self.pausa = pausa
        self._lock = threading.Lock()
        self._ativos = self.max_ativos = 0

    def verificar(self): self.eventos.append("verificar")
    def tabelas_ausentes(self, tabelas): return self.ausentes
    def garantir_controle(self): self.eventos.append("controle")
    def status_atual(self): return self.atual
    def contagens(self, tabelas): return dict(self.tabelas)
    def arquivos_carregados(self, competencia): return set(self.carregados)
    def analisar(self, tabelas): self.eventos.append("analisar")

    def iniciar_carga(self, competencia, assinatura):
        self.eventos.append("truncate")
        self.tabelas = {t: 0 for t in LOAD_ORDER}
        self.carregados = set()
        self.atual = EstadoCarga(competencia, assinatura, "carregando")

    def registrar_inicio(self, competencia, assinatura):
        self.eventos.append("registrar_inicio")
        self.atual = EstadoCarga(competencia, assinatura, "carregando")

    def desmontar(self, tabelas):
        self.eventos.append(("desmontar", tuple(tabelas)))
        self.objetos += [(t, f"{t}_pkey") for t in tabelas] + [("estabelecimentos", "fk_estab_empresa")]

    def objetos_pendentes(self):
        return list(self.objetos)

    def restaurar(self, tabela, nome):
        self.eventos.append(("restaurar", nome))
        self.objetos.remove((tabela, nome))

    def carregar_arquivo(self, tabela, colunas, csv, competencia):
        with self._lock:
            self._ativos += 1
            self.max_ativos = max(self.max_ativos, self._ativos)
        try:
            if self.pausa:
                time.sleep(self.pausa)
            if csv.name == self.falha_em:
                raise LoadError("falha simulada")
            with self._lock:
                self.eventos.append(("carga", csv.name))
                self.tabelas[tabela] += LINHAS_POR_CSV[csv.name]
                self.carregados.add(csv.name)
        finally:
            with self._lock:
                self._ativos -= 1

    def concluir(self, competencia):
        self.eventos.append("concluir")
        self.atual = EstadoCarga(competencia, self.atual.assinatura, "concluida")

    def adotar(self, competencia, assinatura):
        self.eventos.append("adotar")
        self.atual = EstadoCarga(competencia, assinatura, "concluida")

    def cargas(self):
        return [e[1] for e in self.eventos if isinstance(e, tuple) and e[0] == "carga"]

    def indice(self, evento):
        return self.eventos.index(evento)


class CarregarTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = make_output(Path(self._tmp.name))

    def run_carga(self, banco, etags=ETAGS, force=False, jobs=1):
        return carregar(banco, self.out, COMPETENCIA, etags, force=force, jobs=jobs)

    def test_first_load_truncates_drops_constraints_loads_then_restores(self):
        banco = FakeBanco()
        self.assertEqual(self.run_carga(banco), "carregada")
        self.assertEqual(banco.eventos[:3], ["verificar", "controle", "truncate"])
        self.assertEqual(len(banco.cargas()), sum(len(f) for f in ARQUIVOS.values()))

        # as chaves saem ANTES de qualquer carga e voltam DEPOIS de todas, antes de ANALYZE/conclusão
        desmontar = ("desmontar", ("empresas", "estabelecimentos", "socios", "simples"))
        primeira = min(banco.indice(("carga", n)) for n in banco.cargas())
        ultima = max(banco.indice(("carga", n)) for n in banco.cargas())
        self.assertLess(banco.indice(desmontar), primeira)
        restauros = [i for i, e in enumerate(banco.eventos) if isinstance(e, tuple) and e[0] == "restaurar"]
        self.assertEqual(len(restauros), 5)
        self.assertGreater(min(restauros), ultima)
        self.assertEqual(banco.eventos[-2:], ["analisar", "concluir"])
        self.assertLess(max(restauros), banco.indice("analisar"))
        self.assertEqual(banco.objetos, [])
        self.assertEqual(banco.atual.status, "concluida")

    def test_lookup_tables_never_lose_their_keys(self):
        banco = FakeBanco()
        self.run_carga(banco)
        desmontados = [e[1] for e in banco.eventos if isinstance(e, tuple) and e[0] == "desmontar"]
        self.assertEqual(len(desmontados), 1)
        self.assertTrue(set(desmontados[0]) <= set(cb.BIG_TABLES))

    def test_only_big_tables_with_pending_files_are_dismantled(self):
        # empresas já está inteira no banco (carga manual); só o resto precisa perder as chaves
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "carregando"))
        for tabela in ("cnaes", "motivos", "municipios", "naturezas", "paises", "qualificacoes", "empresas"):
            for stem, n in ARQUIVOS[tabela].items():
                banco.carregados.add(f"{stem}.csv"); banco.tabelas[tabela] += n
        self.run_carga(banco)
        self.assertIn(("desmontar", ("estabelecimentos", "socios", "simples")), banco.eventos)
        self.assertNotIn("empresas", [e[1] for e in banco.eventos if isinstance(e, tuple) and e[0] == "desmontar"][0])

    def test_files_are_loaded_concurrently_up_to_the_job_limit(self):
        banco = FakeBanco(pausa=0.05)
        self.run_carga(banco, jobs=3)
        self.assertEqual(len(banco.cargas()), sum(len(f) for f in ARQUIVOS.values()))
        self.assertGreaterEqual(banco.max_ativos, 2)
        self.assertLessEqual(banco.max_ativos, 3)
        self.assertEqual(banco.tabelas, ESPERADO)

    def test_biggest_files_are_started_first(self):
        for nome in ("Estabelecimentos0", "Socios0"):
            (self.out / nome.rstrip("0").lower() / f"{nome}.csv").write_text("x" * 1000, encoding="utf-8")
        banco = FakeBanco()
        self.run_carga(banco)
        self.assertEqual(set(banco.cargas()[:2]), {"Estabelecimentos0.csv", "Socios0.csv"})

    def test_restore_runs_even_when_every_file_was_already_loaded(self):
        # queda durante a recriação das chaves: tudo carregado, objetos ainda pendentes
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "carregando"), contagens=ESPERADO,
                          objetos_pendentes=[("empresas", "empresas_pkey")])
        banco.carregados = set(LINHAS_POR_CSV)
        self.assertEqual(self.run_carga(banco), "carregada")
        self.assertEqual(banco.cargas(), [])
        self.assertIn(("restaurar", "empresas_pkey"), banco.eventos)
        self.assertFalse(any(isinstance(e, tuple) and e[0] == "desmontar" for e in banco.eventos))
        self.assertEqual(banco.atual.status, "concluida")

    def test_partial_manual_load_is_resumed_without_truncate(self):
        # o que o carregar_banco.ps1 deixa: arquivos registrados, sem carga_status
        banco = FakeBanco(atual=None)
        for tabela in ("cnaes", "motivos", "municipios", "naturezas", "paises", "qualificacoes", "empresas"):
            for stem, n in ARQUIVOS[tabela].items():
                banco.carregados.add(f"{stem}.csv"); banco.tabelas[tabela] += n
        banco.carregados.add("Estabelecimentos0.csv"); banco.tabelas["estabelecimentos"] += 7
        self.assertEqual(self.run_carga(banco), "carregada")
        self.assertNotIn("truncate", banco.eventos)
        self.assertIn("registrar_inicio", banco.eventos)
        self.assertEqual(banco.cargas(), ["Socios0.csv", "Simples.csv"])

    def test_already_loaded_does_nothing(self):
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"), contagens=ESPERADO)
        self.assertEqual(self.run_carga(banco), "ja_carregada")
        self.assertNotIn("truncate", banco.eventos)
        self.assertEqual(banco.cargas(), [])

    def apagar_csvs(self):
        for csv in self.out.rglob("*.csv"):
            csv.unlink()

    def test_already_loaded_does_not_need_the_csvs_anymore(self):
        self.apagar_csvs()  # espaço liberado depois da carga; só o relatório e o estado ficam
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"), contagens=ESPERADO)
        self.assertEqual(self.run_carga(banco), "ja_carregada")
        self.assertNotIn("truncate", banco.eventos)

    def test_adoption_does_not_need_the_csvs_either(self):
        self.apagar_csvs()
        banco = FakeBanco(atual=None, contagens=ESPERADO)
        self.assertEqual(self.run_carga(banco), "adotada")

    def test_csvs_are_still_required_when_there_is_something_to_load(self):
        self.apagar_csvs()
        casos = {
            "carga interrompida": FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "carregando")),
            "competência nova": FakeBanco(atual=EstadoCarga("2026-10", "outra", "concluida")),
            "forçado": FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"), contagens=ESPERADO),
        }
        for nome, banco in casos.items():
            with self.subTest(nome), self.assertRaisesRegex(LoadError, "CSVs ausentes"):
                self.run_carga(banco, force=nome == "forçado")
            self.assertNotIn("truncate", banco.eventos)

    def test_interrupted_load_resumes_without_truncate(self):
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "carregando"))
        # o que já tinha sido carregado antes da interrupção
        for tabela in ("cnaes", "motivos", "municipios", "naturezas", "paises", "qualificacoes"):
            for stem, n in ARQUIVOS[tabela].items():
                banco.carregados.add(f"{stem}.csv"); banco.tabelas[tabela] += n
        banco.carregados.add("Empresas0.csv"); banco.tabelas["empresas"] += 5
        self.assertEqual(self.run_carga(banco), "carregada")
        self.assertNotIn("truncate", banco.eventos)
        self.assertEqual(banco.cargas(), ["Empresas1.csv", "Estabelecimentos0.csv", "Socios0.csv", "Simples.csv"])

    def test_new_competencia_or_republished_file_reloads_everything(self):
        concluida = EstadoCarga("2026-10", "outra", "concluida")
        banco = FakeBanco(atual=concluida, contagens={t: 99 for t in LOAD_ORDER})
        self.assertEqual(self.run_carga(banco), "carregada")
        self.assertEqual(banco.eventos[2], "truncate")
        self.assertEqual(banco.tabelas, ESPERADO)

        # mesma competência, mas a Receita republicou um arquivo (outro ETag)
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"), contagens=ESPERADO)
        self.run_carga(banco, etags={**ETAGS, "Empresas1.zip": "republicado"})
        self.assertIn("truncate", banco.eventos)

    def test_force_reloads_even_if_up_to_date(self):
        banco = FakeBanco(atual=EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"), contagens=ESPERADO)
        self.assertEqual(self.run_carga(banco, force=True), "carregada")
        self.assertIn("truncate", banco.eventos)

    def test_manual_load_with_matching_counts_is_adopted_not_reloaded(self):
        banco = FakeBanco(atual=None, contagens=ESPERADO)
        self.assertEqual(self.run_carga(banco), "adotada")
        self.assertNotIn("truncate", banco.eventos)
        self.assertEqual(banco.cargas(), [])
        self.assertEqual(banco.atual, EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"))

    def test_no_control_and_different_counts_truncates(self):
        banco = FakeBanco(atual=None, contagens={**ESPERADO, "empresas": 1})
        self.assertEqual(self.run_carga(banco), "carregada")
        self.assertIn("truncate", banco.eventos)

    def test_nothing_is_erased_if_preflight_fails(self):
        casos = {
            "tabela ausente no banco": FakeBanco(ausentes=["socios"]),
        }
        for nome, banco in casos.items():
            with self.subTest(nome), self.assertRaises(LoadError):
                self.run_carga(banco)
            self.assertNotIn("truncate", banco.eventos)

        with tempfile.TemporaryDirectory() as tmp:  # CSV do relatório ausente em disco
            out = make_output(Path(tmp), skip_csv="Empresas1.csv")
            banco = FakeBanco()
            with self.assertRaisesRegex(LoadError, "Empresas1.csv"):
                carregar(banco, out, COMPETENCIA, ETAGS)
            self.assertNotIn("truncate", banco.eventos)

        with tempfile.TemporaryDirectory() as tmp:  # tratamento com erros
            out = make_output(Path(tmp), erros={"Empresas3.zip": "boom"})
            banco = FakeBanco()
            with self.assertRaisesRegex(LoadError, "erros"):
                carregar(banco, out, COMPETENCIA, ETAGS)
            self.assertEqual(banco.eventos, [])

    def test_failure_in_a_file_stops_and_stays_resumable(self):
        banco = FakeBanco(falha_em="Empresas1.csv")
        with self.assertRaises(LoadError):
            self.run_carga(banco)
        self.assertEqual(banco.atual.status, "carregando")  # não foi marcado como concluído
        self.assertIn("Empresas0.csv", banco.carregados)
        self.assertNotIn("Estabelecimentos0.csv", banco.carregados)

        banco.falha_em = None  # próxima execução: retoma sem esvaziar
        eventos_antes = len(banco.eventos)
        self.run_carga(banco)
        self.assertNotIn("truncate", banco.eventos[eventos_antes:])
        self.assertEqual(banco.atual.status, "concluida")

    def test_count_mismatch_after_load_is_an_error(self):
        banco = FakeBanco()
        original = banco.carregar_arquivo

        def carrega_a_menos(tabela, colunas, csv, competencia):
            original(tabela, colunas, csv, competencia)
            if csv.name == "Socios0.csv":
                banco.tabelas["socios"] -= 1

        banco.carregar_arquivo = carrega_a_menos
        with self.assertRaisesRegex(LoadError, "socios"):
            self.run_carga(banco)
        self.assertNotEqual(banco.atual.status, "concluida")


class PlanTest(unittest.TestCase):
    def test_load_order_covers_all_layouts(self):
        self.assertEqual(set(LOAD_ORDER), set(LAYOUTS))

    def test_signature_changes_when_any_etag_changes(self):
        self.assertEqual(cb.assinatura_de(ETAGS), cb.assinatura_de(dict(reversed(ETAGS.items()))))
        self.assertNotEqual(cb.assinatura_de(ETAGS), cb.assinatura_de({**ETAGS, "Empresas0.zip": "z"}))


class BancoSqlTest(unittest.TestCase):
    """Confere o SQL e a chamada ao psql, sem executá-lo."""

    def setUp(self):
        patcher = mock.patch.object(cb, "find_psql", return_value="psql")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.banco = Banco(DbConfig(host="h", port=5433, user="u", database="d"))

    def capture(self, metodo, *args, **kwargs):
        with mock.patch.object(self.banco, "_run", return_value="") as run:
            getattr(self.banco, metodo)(*args, **kwargs)
        return run.call_args

    def test_start_truncates_every_table_in_one_transaction(self):
        sql = self.capture("iniciar_carga", COMPETENCIA, ASSINATURA).args[0]
        self.assertTrue(sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;"))
        self.assertIn(f"TRUNCATE {', '.join(LOAD_ORDER)} RESTART IDENTITY;", sql)  # todas juntas (chaves estrangeiras)
        self.assertIn(f"'{COMPETENCIA}', '{ASSINATURA}', 'carregando'", sql)

    def test_file_load_is_copy_plus_registration_in_one_transaction(self):
        csv = Path("saida") / "empresas" / "Empresas0.csv"
        call = self.capture("carregar_arquivo", "empresas", LAYOUTS["empresas"].columns, csv, COMPETENCIA)
        sql = call.args[0]
        self.assertTrue(sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;"))
        self.assertIn("\\copy empresas (cnpj_basico, razao_social, natureza_juridica,", sql)
        self.assertIn("FROM 'Empresas0.csv' WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL', ENCODING 'UTF8')", sql)
        self.assertIn("INSERT INTO carga_arquivos", sql)
        self.assertEqual(call.kwargs["cwd"], csv.parent)  # nome relativo: evita acentos no caminho
        self.assertEqual(call.kwargs["settings"], {"synchronous_commit": "off"})

    def test_dismantle_saves_definitions_before_dropping_in_one_transaction(self):
        sql = self.capture("desmontar", ("estabelecimentos", "socios")).args[0]
        self.assertTrue(sql.startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;"))
        self.assertIn("'public.estabelecimentos'::regclass, 'public.socios'::regclass", sql)
        # chaves estrangeiras de outras tabelas que apontam para estas também saem (dependem da primária)
        self.assertIn("c.confrelid = ANY", sql)
        self.assertIn("pg_get_constraintdef(c.oid)", sql)
        self.assertIn("pg_get_indexdef", sql.replace("i.indexdef", "pg_get_indexdef"))  # índices fora de constraints
        self.assertLess(sql.index("INSERT INTO carga_objetos"), sql.index("DROP CONSTRAINT"))
        # estrangeiras antes das primárias, e primárias antes dos índices
        self.assertIn("CASE tipo WHEN 'fk' THEN 0 WHEN 'pk' THEN 1 ELSE 2 END", sql)

    def test_restore_order_is_primary_keys_then_indexes_then_foreign_keys(self):
        with mock.patch.object(self.banco, "_run", return_value="empresas|empresas_pkey\nsocios|fk_x") as run:
            self.assertEqual(self.banco.objetos_pendentes(), [("empresas", "empresas_pkey"), ("socios", "fk_x")])
        self.assertIn("CASE tipo WHEN 'pk' THEN 0 WHEN 'index' THEN 1 ELSE 2 END", run.call_args.args[0])

    def test_restore_runs_with_big_maintenance_memory_and_escapes_names(self):
        call = self.capture("restaurar", "empresas", "x'; DROP TABLE empresas; --")
        self.assertIn("x''; DROP TABLE empresas; --", call.args[0])  # aspas escapadas: vira texto, não comando
        self.assertEqual(call.kwargs["settings"]["maintenance_work_mem"], "1GB")

    def test_resume_without_truncating_only_registers_the_start(self):
        sql = self.capture("registrar_inicio", COMPETENCIA, ASSINATURA).args[0]
        self.assertNotIn("TRUNCATE", sql)
        self.assertIn("'carregando'", sql)

    def test_hostile_file_name_is_refused(self):
        with self.assertRaises(LoadError):
            self.banco.carregar_arquivo("empresas", ("a",), Path("x") / "e'; DROP TABLE empresas; --.csv", COMPETENCIA)

    def test_parsing_of_psql_output(self):
        with mock.patch.object(self.banco, "_run", return_value="empresas|5\nsocios|2"):
            self.assertEqual(self.banco.contagens(("empresas", "socios")), {"empresas": 5, "socios": 2})
        with mock.patch.object(self.banco, "_run", return_value=f"{COMPETENCIA}|{ASSINATURA}|concluida"):
            self.assertEqual(self.banco.status_atual(), EstadoCarga(COMPETENCIA, ASSINATURA, "concluida"))
        with mock.patch.object(self.banco, "_run", return_value=""):
            self.assertIsNone(self.banco.status_atual())
            self.assertEqual(self.banco.tabelas_ausentes(LOAD_ORDER), [])

    def test_psql_never_prompts_for_password_and_reports_errors(self):
        proc = mock.Mock(returncode=0, stdout=b"1\n", stderr=b"")
        with mock.patch.object(cb.subprocess, "run", return_value=proc) as run:
            self.assertEqual(self.banco._run("SELECT 1"), "1")
        cmd, kwargs = run.call_args.args[0], run.call_args.kwargs
        self.assertIn("-w", cmd)  # nunca pede senha (tarefa agendada não tem console)
        self.assertIn("ON_ERROR_STOP=1", cmd)
        self.assertEqual(cmd[cmd.index("-h") + 1], "h")
        self.assertEqual(cmd[cmd.index("-p") + 1], "5433")
        self.assertEqual(kwargs["env"]["PGCLIENTENCODING"], "UTF8")
        self.assertNotIn("PGPASSWORD", " ".join(cmd))
        self.assertEqual(kwargs["input"], b"SELECT 1")  # bytes: o modo texto do Windows trocaria \n por \r\n

        proc = mock.Mock(returncode=2, stdout=b"", stderr="FATAL: autenticação falhou".encode("utf-8"))
        with mock.patch.object(cb.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(LoadError, "autenticação falhou"):
                self.banco._run("SELECT 1")

    def test_session_settings_go_through_pgoptions_and_keep_existing_ones(self):
        proc = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(cb.subprocess, "run", return_value=proc) as run, \
                mock.patch.dict(cb.os.environ, {"PGOPTIONS": "-c lock_timeout=5s"}):
            self.banco._run("SELECT 1", settings={"synchronous_commit": "off", "maintenance_work_mem": "1GB"})
        self.assertEqual(run.call_args.kwargs["env"]["PGOPTIONS"],
                         "-c lock_timeout=5s -c synchronous_commit=off -c maintenance_work_mem=1GB")

        with mock.patch.object(cb.subprocess, "run", return_value=proc) as run, \
                mock.patch.dict(cb.os.environ, {}, clear=False):
            cb.os.environ.pop("PGOPTIONS", None)
            self.banco._run("SELECT 1")
        self.assertNotIn("PGOPTIONS", run.call_args.kwargs["env"])  # sem settings, nada é alterado


if __name__ == "__main__":
    unittest.main()
