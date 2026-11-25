"""Carrega no PostgreSQL os CSVs tratados de uma competência: esvazia as tabelas e recarrega.

A Receita publica um dump completo por mês, então a carga é uma SUBSTITUIÇÃO: quando chega uma
competência nova (ou a Receita republica algum arquivo), as tabelas são esvaziadas e carregadas de
novo. O estado fica no próprio banco (tabelas ``carga_status`` e ``carga_arquivos``):

  - mesma competência e mesmos arquivos, carga concluída  -> nada a fazer;
  - mesma competência e mesmos arquivos, carga incompleta -> retoma, pulando os arquivos já carregados;
  - banco sem controle e com contagens iguais às do relatório (carga manual anterior) -> adota, sem recarregar;
  - qualquer outro caso (competência nova, arquivo republicado, --force) -> TRUNCATE e carga completa.

Antes de esvaziar, tudo é conferido (psql, conexão, tabelas, CSVs); nada é apagado se algo faltar.
Depois da carga, a contagem de cada tabela é comparada com o relatório do tratamento.

Velocidade (o que mais custava tempo, medido numa carga real de 74 milhões de estabelecimentos):
  - chaves estrangeiras: o Postgres confere cada linha contra ``empresas`` e grava um bloqueio no WAL;
  - chave primária: cada linha é inserida num ponto aleatório do índice (os arquivos não vêm ordenados).
Por isso, nas tabelas grandes com arquivos pendentes, a carga retira chaves estrangeiras, primárias e índices
(guardando a definição no banco, em ``carga_objetos``, para sobreviver a quedas), carrega vários arquivos em
paralelo e, no fim, recria tudo: o índice é construído ordenado e a chave estrangeira é validada numa
única junção, em minutos. Uma falha entre a retirada e a recriação é retomada na execução seguinte.

Usa o cliente ``psql`` (sem dependências Python). A senha NUNCA vem de argumento: use a variável
PGPASSWORD ou o arquivo pgpass.conf (Windows: %APPDATA%\\postgresql\\pgpass.conf), formato
``host:porta:banco:usuario:senha``. O psql roda com ``-w`` (nunca pergunta senha), para não travar
a tarefa agendada.

As tabelas precisam existir (a API cria no primeiro start, com ddl-auto=update).

Uso (a partir da raiz do projeto):
    python data/scripts/carregar_banco.py                       # competência mais recente tratada
    python data/scripts/carregar_banco.py --release 2026-11 --force
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from process_receita import COMPETENCIA, DATA_DIR, REPORT_NAME
from rf_layout import LAYOUTS

# Ordem de carga: as tabelas de apoio e empresas antes de quem tem chave estrangeira para empresas.
LOAD_ORDER = (
    "cnaes", "motivos", "municipios", "naturezas", "paises", "qualificacoes",
    "empresas", "estabelecimentos", "socios", "simples",
)
STATE_NAME = "_atualizacao.json"  # mesmo arquivo gravado por atualizar_receita.py
COPY_OPTIONS = "FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL', ENCODING 'UTF8'"

# Tabelas grandes: perdem chaves e índices durante a carga e os recebem de volta no fim.
# As de apoio (milhares de linhas) são carregadas como estão.
BIG_TABLES = ("empresas", "estabelecimentos", "socios", "simples")
DEFAULT_JOBS = 4  # arquivos carregados ao mesmo tempo
# Só nas sessões de carga: a transação (COPY + registro do arquivo) continua atômica; numa queda de energia
# some inteira ou fica inteira, e o arquivo é refeito na retomada.
LOAD_SETTINGS = {"synchronous_commit": "off"}
# Só nas sessões que recriam chaves/índices: o padrão (64 MB) é pequeno demais para ordenar dezenas de milhões de linhas.
RESTORE_SETTINGS = {"maintenance_work_mem": "1GB", "max_parallel_maintenance_workers": "4"}

CONTROL_DDL = """
CREATE TABLE IF NOT EXISTS carga_arquivos (
    competencia text, tabela text, arquivo text,
    carregado_em timestamptz DEFAULT now(), PRIMARY KEY (competencia, arquivo));
CREATE TABLE IF NOT EXISTS carga_status (
    competencia text PRIMARY KEY, assinatura text NOT NULL, status text NOT NULL,
    iniciado_em timestamptz DEFAULT now(), concluido_em timestamptz);
CREATE TABLE IF NOT EXISTS carga_objetos (
    tabela text, nome text, tipo text NOT NULL, ddl text NOT NULL,
    removido boolean NOT NULL DEFAULT false, PRIMARY KEY (tabela, nome));
"""

log = logging.getLogger("receita.carga")


class LoadError(Exception):
    pass


@dataclass(frozen=True)
class DbConfig:
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    database: str = "prospeccao"
    psql: str | None = None  # caminho do psql; None = procurar no PATH e na instalação padrão


@dataclass(frozen=True)
class EstadoCarga:
    competencia: str
    assinatura: str
    status: str  # "carregando" | "concluida"


# --------------------------------------------------------------------------- acesso ao banco (psql)


def find_psql(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if found := shutil.which("psql"):
        return found
    if os.name == "nt":  # a tarefa agendada nem sempre herda o PATH do usuário
        def version(p: Path) -> int:
            name = p.parent.parent.name
            return int(name) if name.isdigit() else 0

        installed = sorted(Path(r"C:\Program Files\PostgreSQL").glob("*/bin/psql.exe"), key=version, reverse=True)
        if installed:
            return str(installed[0])
    raise LoadError("psql não encontrado: instale o cliente do PostgreSQL, ponha a pasta bin no PATH ou use --psql")


class Banco:
    """Operações no PostgreSQL via psql. Todo SQL daqui usa só nomes fixos e valores validados."""

    def __init__(self, config: DbConfig):
        self.config = config
        self.psql = find_psql(config.psql)

    def _run(self, sql: str, cwd: Path | None = None, settings: dict[str, str] | None = None) -> str:
        """Executa o SQL no psql. ``settings`` vale só para esta sessão (parâmetros do servidor, via PGOPTIONS)."""
        c = self.config
        cmd = [self.psql, "-X", "-w", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
               "-h", c.host, "-p", str(c.port), "-U", c.user, "-d", c.database]
        env = {**os.environ, "PGCLIENTENCODING": "UTF8"}
        if settings:
            extra = " ".join(f"-c {k}={v}" for k, v in settings.items())
            env["PGOPTIONS"] = f"{env.get('PGOPTIONS', '')} {extra}".strip()
        # Bytes (e não texto): no Windows o modo texto trocaria "\n" por "\r\n" no que vai para o psql.
        proc = subprocess.run(
            cmd, input=sql.encode("utf-8"), capture_output=True, cwd=cwd, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # sem janela sob pythonw
        )
        if proc.returncode != 0:
            erro = proc.stderr.decode("utf-8", errors="replace").strip()[-2000:]
            raise LoadError(f"psql falhou (código {proc.returncode}): {erro}")
        return proc.stdout.decode("utf-8", errors="replace").strip()

    def verificar(self) -> None:
        self._run("SELECT 1")

    def tabelas_ausentes(self, tabelas: tuple[str, ...]) -> list[str]:
        lista = ", ".join(f"'{t}'" for t in tabelas)
        out = self._run(f"SELECT t FROM unnest(ARRAY[{lista}]) AS t WHERE to_regclass('public.' || t) IS NULL")
        return out.splitlines() if out else []

    def garantir_controle(self) -> None:
        self._run(CONTROL_DDL)

    def status_atual(self) -> EstadoCarga | None:
        out = self._run("SELECT competencia || '|' || assinatura || '|' || status FROM carga_status LIMIT 1")
        if not out:
            return None
        competencia, assinatura, status = out.split("|")
        return EstadoCarga(competencia, assinatura, status)

    def contagens(self, tabelas: tuple[str, ...]) -> dict[str, int]:
        out = self._run(" UNION ALL ".join(f"SELECT '{t}', count(*) FROM {t}" for t in tabelas))
        return {linha.split("|")[0]: int(linha.split("|")[1]) for linha in out.splitlines()}

    def iniciar_carga(self, competencia: str, assinatura: str) -> None:
        """Esvazia tudo e registra o início, numa transação só: se falhar, nada é apagado."""
        self._run(
            "BEGIN;\n"
            f"TRUNCATE {', '.join(LOAD_ORDER)} RESTART IDENTITY;\n"
            "DELETE FROM carga_arquivos;\n"
            "DELETE FROM carga_status;\n"
            f"INSERT INTO carga_status (competencia, assinatura, status) VALUES ('{competencia}', '{assinatura}', 'carregando');\n"
            "COMMIT;"
        )

    def arquivos_carregados(self, competencia: str) -> set[str]:
        out = self._run(f"SELECT arquivo FROM carga_arquivos WHERE competencia = '{competencia}'")
        return set(out.splitlines()) if out else set()

    def carregar_arquivo(self, tabela: str, colunas: tuple[str, ...], csv: Path, competencia: str) -> None:
        """COPY + registro do arquivo na mesma transação: ou entra tudo, ou nada (e será tentado de novo)."""
        if "'" in csv.name:
            raise LoadError(f"nome de arquivo inválido: {csv.name}")
        # \copy lê o arquivo pelo cliente; o nome é relativo ao cwd para evitar problemas com acentos no caminho.
        self._run(
            "BEGIN;\n"
            f"\\copy {tabela} ({', '.join(colunas)}) FROM '{csv.name}' WITH ({COPY_OPTIONS})\n"
            f"INSERT INTO carga_arquivos (competencia, tabela, arquivo) VALUES ('{competencia}', '{tabela}', '{csv.name}');\n"
            "COMMIT;",
            cwd=csv.parent,
            settings=LOAD_SETTINGS,
        )

    def registrar_inicio(self, competencia: str, assinatura: str) -> None:
        """Marca a competência como em carga SEM esvaziar nada (retomada de uma carga manual parcial)."""
        self._run(
            "BEGIN;\nDELETE FROM carga_status;\n"
            f"INSERT INTO carga_status (competencia, assinatura, status) VALUES ('{competencia}', '{assinatura}', 'carregando');\n"
            "COMMIT;"
        )

    def desmontar(self, tabelas: tuple[str, ...]) -> None:
        """Retira chaves estrangeiras, chaves primárias e índices das tabelas, guardando a definição em carga_objetos.

        Tudo numa transação: guardar e retirar andam juntos, então uma falha não perde a definição de nada.
        Retira também as chaves estrangeiras de OUTRAS tabelas que apontam para estas (dependem da chave primária).
        Chamar de novo é seguro: o que já foi retirado e ainda não foi recriado é preservado.
        """
        regs = ", ".join(f"'public.{t}'::regclass" for t in tabelas)
        nomes = ", ".join(f"'{t}'" for t in tabelas)
        self._run(f"""BEGIN;
INSERT INTO carga_objetos (tabela, nome, tipo, ddl)
SELECT c.conrelid::regclass::text, c.conname, CASE WHEN c.contype = 'f' THEN 'fk' ELSE 'pk' END,
       format('ALTER TABLE %s ADD CONSTRAINT %I %s', c.conrelid::regclass, c.conname, pg_get_constraintdef(c.oid))
  FROM pg_constraint c
 WHERE c.connamespace = 'public'::regnamespace AND c.contype IN ('p', 'u', 'f')
   AND (c.conrelid = ANY (ARRAY[{regs}]) OR c.confrelid = ANY (ARRAY[{regs}]))
ON CONFLICT DO NOTHING;
INSERT INTO carga_objetos (tabela, nome, tipo, ddl)
SELECT i.tablename, i.indexname, 'index', i.indexdef
  FROM pg_indexes i
 WHERE i.schemaname = 'public' AND i.tablename = ANY (ARRAY[{nomes}])
   AND NOT EXISTS (SELECT 1 FROM pg_constraint c
                    WHERE c.conname = i.indexname AND c.connamespace = 'public'::regnamespace)
ON CONFLICT DO NOTHING;
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT * FROM carga_objetos WHERE NOT removido
            ORDER BY CASE tipo WHEN 'fk' THEN 0 WHEN 'pk' THEN 1 ELSE 2 END
  LOOP
    IF r.tipo = 'index' THEN
      EXECUTE format('DROP INDEX IF EXISTS %I', r.nome);
    ELSE
      EXECUTE format('ALTER TABLE %s DROP CONSTRAINT IF EXISTS %I', r.tabela, r.nome);
    END IF;
    UPDATE carga_objetos SET removido = true WHERE tabela = r.tabela AND nome = r.nome;
  END LOOP;
END $$;
COMMIT;""")

    def objetos_pendentes(self) -> list[tuple[str, str]]:
        """(tabela, nome) do que foi retirado e ainda não recriado: primárias, depois índices, depois estrangeiras."""
        out = self._run(
            "SELECT tabela || '|' || nome FROM carga_objetos WHERE removido "
            "ORDER BY CASE tipo WHEN 'pk' THEN 0 WHEN 'index' THEN 1 ELSE 2 END, tabela, nome"
        )
        return [tuple(linha.split("|", 1)) for linha in out.splitlines()] if out else []

    def restaurar(self, tabela: str, nome: str) -> None:
        """Recria um objeto retirado e o tira da lista, na mesma transação (a falha deixa tudo como estava)."""
        t, n = tabela.replace("'", "''"), nome.replace("'", "''")
        self._run(
            "DO $$ DECLARE r carga_objetos; BEGIN "
            f"SELECT * INTO r FROM carga_objetos WHERE tabela = '{t}' AND nome = '{n}'; "
            "EXECUTE r.ddl; "
            "DELETE FROM carga_objetos WHERE tabela = r.tabela AND nome = r.nome; "
            "END $$;",
            settings=RESTORE_SETTINGS,
        )

    def concluir(self, competencia: str) -> None:
        self._run(f"UPDATE carga_status SET status = 'concluida', concluido_em = now() WHERE competencia = '{competencia}'")

    def adotar(self, competencia: str, assinatura: str) -> None:
        """Registra como concluída uma carga feita por fora (contagens já conferidas)."""
        self._run(
            "BEGIN;\nDELETE FROM carga_status;\n"
            "INSERT INTO carga_status (competencia, assinatura, status, concluido_em) "
            f"VALUES ('{competencia}', '{assinatura}', 'concluida', now());\nCOMMIT;"
        )

    def analisar(self, tabelas: tuple[str, ...]) -> None:
        self._run(f"ANALYZE {', '.join(tabelas)}")


# --------------------------------------------------------------------------- fluxo


def assinatura_de(etags: dict[str, str]) -> str:
    """Identifica o conjunto exato de arquivos publicados; muda se a Receita republicar qualquer um."""
    return hashlib.sha256(json.dumps(sorted(etags.items())).encode()).hexdigest()[:16]


def _ler_relatorio(output_dir: Path) -> dict:
    path = output_dir / REPORT_NAME
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise LoadError(f"relatório do tratamento ausente ou inválido: {path}") from exc
    if report.get("erros"):
        raise LoadError(f"o tratamento terminou com erros: {', '.join(report['erros'])}")
    return report


def _esperado(report: dict) -> dict[str, int]:
    """Contagem de registros esperada por tabela, segundo o relatório do tratamento."""
    esperado = {t: int(report.get("tabelas", {}).get(t, {}).get("records", 0)) for t in LOAD_ORDER}
    vazias = [t for t, n in esperado.items() if n == 0]
    if vazias:
        raise LoadError(f"tabelas sem registros no relatório: {', '.join(vazias)}")
    return esperado


def _planejar(output_dir: Path, report: dict) -> dict[str, list[Path]]:
    """CSVs a carregar, por tabela. Falha se algum faltar (antes de apagar qualquer coisa)."""
    arquivos: dict[str, list[Path]] = {t: [] for t in LOAD_ORDER}
    for chave in report.get("arquivos", {}):
        tabela, stem = chave.split("/", 1)
        if tabela in arquivos:
            arquivos[tabela].append(output_dir / tabela / f"{stem}.csv")
    ausentes = [str(p) for lista in arquivos.values() for p in lista if not p.is_file()]
    if ausentes or any(not lista for lista in arquivos.values()):
        raise LoadError(f"CSVs ausentes em {output_dir}: {', '.join(ausentes) or 'tabela sem arquivos'}")
    return {t: sorted(lista) for t, lista in arquivos.items()}


def carregar(
    banco, output_dir: Path, competencia: str, etags: dict[str, str], force: bool = False, jobs: int = DEFAULT_JOBS
) -> str:
    """Esvazia e recarrega o banco com a competência, se necessário.

    Retorna "ja_carregada", "adotada" ou "carregada". Levanta LoadError em qualquer falha;
    uma carga interrompida (inclusive por queda de energia) é retomada na execução seguinte.
    """
    report = _ler_relatorio(output_dir)  # o relatório (pequeno) é sempre exigido; os CSVs só se for preciso carregar
    esperado = _esperado(report)

    banco.verificar()
    if faltam := banco.tabelas_ausentes(LOAD_ORDER):
        raise LoadError(f"tabelas ausentes no banco: {', '.join(faltam)} (suba a API uma vez para criá-las)")
    banco.garantir_controle()

    assinatura = assinatura_de(etags)
    atual = banco.status_atual()
    mesma_carga = atual is not None and atual.competencia == competencia and atual.assinatura == assinatura

    # Os dois casos em que não há nada a carregar valem mesmo que os CSVs já tenham sido apagados para liberar espaço.
    if mesma_carga and not force and atual.status == "concluida":
        log.info("Banco já carregado com a competência %s; nada a fazer.", competencia)
        return "ja_carregada"
    if atual is None and not force and banco.contagens(LOAD_ORDER) == esperado:
        banco.adotar(competencia, assinatura)
        log.info("Banco já tem exatamente os registros da competência %s (carga anterior); registrado como concluído.",
                 competencia)
        return "adotada"

    arquivos = _planejar(output_dir, report)  # daqui em diante é preciso carregar: os CSVs têm de existir

    if mesma_carga and not force:
        log.info("Retomando a carga da competência %s (arquivos já carregados serão pulados).", competencia)
    elif atual is None and not force and banco.arquivos_carregados(competencia):
        # Carga manual interrompida (carregar_banco.ps1 ou COPY): cada arquivo registrado foi gravado por inteiro,
        # na mesma transação do registro. Continua dali, sem esvaziar.
        log.info("Carga manual parcial da competência %s encontrada; retomando sem esvaziar.", competencia)
        banco.registrar_inicio(competencia, assinatura)
    else:
        motivo = "forçado" if force else "competência nova ou arquivos republicados"
        log.warning("Esvaziando as tabelas para carregar a competência %s (%s).", competencia, motivo)
        banco.iniciar_carga(competencia, assinatura)

    carregados = banco.arquivos_carregados(competencia)
    pendentes = {t: [c for c in arquivos[t] if c.name not in carregados] for t in LOAD_ORDER}
    if ja := sorted(c.name for lista in arquivos.values() for c in lista if c.name in carregados):
        log.info("  %d arquivo(s) já carregado(s), pulados: %s", len(ja), ", ".join(ja))

    inicio = time.perf_counter()
    if grandes := tuple(t for t in BIG_TABLES if pendentes[t]):
        log.info("Retirando chaves e índices de %s para acelerar a carga (serão recriados no fim).", ", ".join(grandes))
        banco.desmontar(grandes)

    tarefas = [(t, c) for t in LOAD_ORDER for c in pendentes[t]]
    tarefas.sort(key=lambda tc: tc[1].stat().st_size, reverse=True)  # os maiores primeiro: melhor distribuição
    _carregar_em_paralelo(banco, tarefas, competencia, jobs)

    obtido = banco.contagens(LOAD_ORDER)
    if divergentes := {t: (obtido[t], esperado[t]) for t in LOAD_ORDER if obtido[t] != esperado[t]}:
        detalhe = ", ".join(f"{t}: banco={a:,} relatório={b:,}" for t, (a, b) in divergentes.items())
        raise LoadError(f"contagens divergentes após a carga ({detalhe})")

    _restaurar_objetos(banco)
    banco.analisar(LOAD_ORDER)
    banco.concluir(competencia)
    log.info("Carga da competência %s concluída em %.0f s.", competencia, time.perf_counter() - inicio)
    return "carregada"


def _carregar_em_paralelo(banco, tarefas: list[tuple[str, Path]], competencia: str, jobs: int) -> None:
    """Carrega os arquivos com até ``jobs`` sessões simultâneas. A primeira falha cancela o que não começou."""
    if not tarefas:
        return

    parar = threading.Event()  # acionado pela própria tarefa que falha: nenhuma outra começa depois disso

    def um(tabela: str, csv: Path) -> None:
        if parar.is_set():
            return
        t0 = time.perf_counter()
        try:
            banco.carregar_arquivo(tabela, LAYOUTS[tabela].columns, csv, competencia)
        except Exception:
            parar.set()
            raise
        log.info("  ok  %s (%.0f s)", csv.name, time.perf_counter() - t0)

    erro: Exception | None = None
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futuros = [pool.submit(um, t, c) for t, c in tarefas]
        for futuro in as_completed(futuros):  # as em curso terminam (cada uma é uma transação inteira)
            try:
                futuro.result()
            except Exception as exc:  # noqa: BLE001
                erro = erro or exc
    if erro is not None:
        raise erro


def _restaurar_objetos(banco) -> None:
    """Recria o que a carga retirou: primárias, índices e, por último, estrangeiras (precisam das primárias)."""
    pendentes = banco.objetos_pendentes()
    if pendentes:
        log.info("Recriando %d chave(s)/índice(s) retirados na carga...", len(pendentes))
    for tabela, nome in pendentes:
        t0 = time.perf_counter()
        try:
            banco.restaurar(tabela, nome)
        except LoadError as exc:
            raise LoadError(f"falha ao recriar {nome} em {tabela} (os dados foram carregados; corrija e rode de novo): {exc}") from exc
        log.info("  ok  %s em %s (%.0f s)", nome, tabela, time.perf_counter() - t0)


# --------------------------------------------------------------------------- linha de comando


def add_db_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("banco de dados (a senha vem de PGPASSWORD ou pgpass.conf, nunca de argumento)")
    group.add_argument("--db-host", default=os.environ.get("PGHOST", "localhost"))
    group.add_argument("--db-port", type=int, default=int(os.environ.get("PGPORT", "5432")))
    group.add_argument("--db-user", default=os.environ.get("PGUSER", "postgres"))
    group.add_argument("--db-name", default=os.environ.get("PGDATABASE", "prospeccao"))
    group.add_argument("--psql", default=os.environ.get("PSQL_PATH"),
                       help="caminho do psql (padrão: PATH ou pasta de instalação do PostgreSQL)")
    group.add_argument("--db-jobs", type=int, default=DEFAULT_JOBS,
                       help="arquivos carregados ao mesmo tempo (padrão: %(default)s)")


def db_config_from_args(args: argparse.Namespace) -> DbConfig:
    return DbConfig(args.db_host, args.db_port, args.db_user, args.db_name, args.psql)


def _latest_treated(output_root: Path) -> str | None:
    candidates = []
    for d in sorted(output_root.glob("*")):
        if d.is_dir() and COMPETENCIA.fullmatch(d.name):
            try:
                state = json.loads((d / STATE_NAME).read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                continue
            if state.get("status") == "concluido" and not state.get("parcial"):
                candidates.append(d.name)
    return candidates[-1] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release", metavar="AAAA-MM", help="competência (padrão: a mais recente já tratada)")
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR / "output")
    parser.add_argument("--force", action="store_true", help="esvazia e recarrega mesmo que o banco já esteja atualizado")
    add_db_arguments(parser)
    args = parser.parse_args(argv)
    if args.release and not COMPETENCIA.fullmatch(args.release):
        parser.error("--release deve estar no formato AAAA-MM")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", stream=sys.stdout)
    competencia = args.release or _latest_treated(args.output_dir)
    if competencia is None:
        log.error("nenhuma competência tratada em %s", args.output_dir)
        return 1
    try:
        state = json.loads((args.output_dir / competencia / STATE_NAME).read_text(encoding="utf-8"))
        if state.get("status") != "concluido" or state.get("parcial"):
            raise LoadError(f"a competência {competencia} não tem um tratamento completo (status: {state.get('status')})")
        carregar(Banco(db_config_from_args(args)), args.output_dir / competencia, competencia,
                 state["etags"], force=args.force, jobs=args.db_jobs)
    except (LoadError, FileNotFoundError, KeyError) as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
