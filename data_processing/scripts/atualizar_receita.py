"""Atualização mensal automática dos Dados Abertos do CNPJ: verifica, baixa e trata a competência mais recente.

Feito para rodar todo dia (Agendador de Tarefas do Windows ou cron). Em cada execução:
  1. lista as competências publicadas no compartilhamento da Receita e escolhe a mais recente;
  2. se ela ainda estiver incompleta ou tiver sido alterada há pouco (upload em andamento), encerra;
  3. se ela já foi tratada e nenhum arquivo mudou desde então, encerra;
  4. baixa os ZIPs para data/AAAA-MM/ (nomes e estrutura originais; retoma downloads interrompidos);
  5. trata os arquivos (process_receita.py) gerando output/AAAA-MM/;
  6. com --carregar-banco: esvazia e recarrega o PostgreSQL com a competência (carregar_banco.py);
     uma carga interrompida é retomada na execução seguinte;
  7. apaga competências antigas de data/ e output/ conforme a política de retenção.
Tudo é registrado em data_processing/logs/atualizar_receita.log.

Uso (a partir da raiz do projeto):
    python data_processing/scripts/atualizar_receita.py                  # execução normal (agendada)
    python data_processing/scripts/atualizar_receita.py --check-only     # só informa se há competência nova
    python data_processing/scripts/atualizar_receita.py --release 2026-10 --force
    python data_processing/scripts/atualizar_receita.py --tables cnaes motivos --limit 100   # teste rápido

Códigos de saída: 0 = sucesso ou nada a fazer; 1 = falha (detalhes no log).
"""

import argparse
import json
import logging
import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from carregar_banco import Banco, add_db_arguments, carregar, db_config_from_args
from process_receita import COMPETENCIA, DATA_PROCESSING_DIR, Options, processar
from rf_download import (
    DEFAULT_SHARE_URL,
    ReceitaShare,
    download_release,
    is_current,
    missing_tables,
    read_manifest,
)
from rf_layout import LAYOUTS
from rf_source import table_for_zip

STATE_NAME = "_atualizacao.json"
# Tamanho aproximado de (arquivos descompactados + CSVs gerados) em relação ao tamanho dos ZIPs.
OUTPUT_TO_ZIP_RATIO = 4.5

log = logging.getLogger("receita.atualizacao")


class AlreadyRunning(Exception):
    pass


class UpdateError(Exception):
    pass


# --------------------------------------------------------------------------- infraestrutura


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_dir / "atualizar_receita.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    ]
    if sys.stderr is not None:  # pythonw (execução agendada sem janela) não tem console
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", handlers=handlers, force=True
    )


@contextmanager
def single_instance(lock_path: Path):
    """Impede duas atualizações simultâneas. O sistema libera a trava se o processo morrer."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    try:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise AlreadyRunning(str(lock_path)) from exc
        yield
    finally:
        handle.close()


def read_state(output_dir: Path) -> dict:
    try:
        return json.loads((output_dir / STATE_NAME).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(output_dir: Path, state: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = output_dir / (STATE_NAME + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, output_dir / STATE_NAME)


def _existing_anchor(path: Path) -> Path:
    while not path.exists():
        path = path.parent
    return path


def check_disk_space(data_dir: Path, output_dir: Path, download_bytes: int, output_bytes: int) -> None:
    needs: dict[str, tuple[Path, int]] = {}
    for path, size in ((data_dir, download_bytes), (output_dir, output_bytes)):
        anchor = _existing_anchor(path)
        drive = anchor.resolve().anchor
        needs[drive] = (anchor, needs.get(drive, (anchor, 0))[1] + size)
    for drive, (anchor, size) in needs.items():
        free = shutil.disk_usage(anchor).free
        if free < size:
            raise UpdateError(
                f"espaço insuficiente em {drive}: necessários ~{size / 1e9:.1f} GB, livres {free / 1e9:.1f} GB"
            )
        log.info("Espaço em disco (%s): necessários ~%.1f GB, livres %.1f GB", drive, size / 1e9, free / 1e9)


def prune(root: Path, keep: int, current: str) -> None:
    """Mantém as ``keep`` competências mais recentes até ``current`` (inclusive); apaga as mais antigas."""
    if not root.is_dir():
        return
    older = sorted(d.name for d in root.iterdir() if d.is_dir() and COMPETENCIA.fullmatch(d.name) and d.name <= current)
    for name in older[: -max(keep, 1)]:
        log.info("Retenção: removendo %s", root / name)
        shutil.rmtree(root / name)


def carregar_no_banco(
    args: argparse.Namespace, competencia: str, output_dir: Path, etags: dict[str, str], force: bool = False
) -> None:
    """Esvazia e recarrega o PostgreSQL com a competência tratada (ver carregar_banco.py). Falha = exceção."""
    log.info("Carga no banco: %s@%s:%s/%s", args.db_user, args.db_host, args.db_port, args.db_name)
    carregar(Banco(db_config_from_args(args)), output_dir, competencia, etags, force=force, jobs=args.db_jobs)


# --------------------------------------------------------------------------- fluxo


def select_release(share: ReceitaShare, wanted: str | None) -> str:
    releases = [r.name for r in share.releases()]
    if not releases:
        raise UpdateError("nenhuma competência (AAAA-MM) encontrada no compartilhamento da Receita")
    if wanted is None:
        return releases[-1]
    if wanted not in releases:
        raise UpdateError(f"competência {wanted} não encontrada; disponíveis: {releases[0]} a {releases[-1]}")
    return wanted


def run(args: argparse.Namespace) -> int:
    share = ReceitaShare(args.share_url)
    competencia = select_release(share, args.release)
    files = share.release_files(competencia)
    partial = bool(args.tables or args.limit)
    if args.tables:
        files = [f for f in files if table_for_zip(f.name) in args.tables]
        if not files:
            raise UpdateError(f"nenhum arquivo das tabelas {sorted(args.tables)} em {competencia}")
    elif missing := missing_tables(files):
        log.info("Competência %s ainda incompleta (faltam: %s). Nova verificação na próxima execução.",
                 competencia, ", ".join(missing))
        return 0

    last_change = max(f.modified for f in files)
    age = datetime.now(timezone.utc) - last_change
    if age < timedelta(hours=args.quiet_hours):
        log.info("Competência %s alterada há %s (upload possivelmente em andamento); aguardando %sh sem mudanças.",
                 competencia, str(age).split(".")[0], args.quiet_hours)
        return 0

    data_dir = args.data_dir / competencia
    output_dir = args.output_dir / competencia
    etags = {f.name: f.etag for f in files}
    state = read_state(output_dir)
    if state.get("status") == "concluido" and state.get("etags") == etags and not state.get("parcial") \
            and not partial and not args.force:
        if args.carregar_banco:  # confere o banco (rápido se já estiver carregado) e retoma carga interrompida
            log.info("Competência %s já tratada em %s; conferindo o banco.", competencia, state.get("concluido_em"))
            carregar_no_banco(args, competencia, output_dir, etags)
        else:
            log.info("Competência %s já tratada em %s; nada a fazer.", competencia, state.get("concluido_em"))
        return 0

    total_zip = sum(f.size for f in files)
    log.info("Competência %s: %d arquivo(s), %.2f GB compactados.", competencia, len(files), total_zip / 1e9)
    if args.check_only:
        log.info("--check-only: competência %s pendente de download/tratamento.", competencia)
        return 0

    # Retoma só uma execução interrompida com os mesmos arquivos e opções; caso contrário, refaz a saída.
    run_signature = {"tables": sorted(args.tables or LAYOUTS), "limit": args.limit}
    resume = (
        state.get("status") == "em_andamento"
        and state.get("etags") == etags
        and state.get("opcoes") == run_signature
        and not args.force
    )
    manifest = read_manifest(data_dir)
    to_download = sum(f.size for f in files if not is_current(data_dir, f, manifest))
    check_disk_space(data_dir, output_dir, to_download, 0 if resume else int(total_zip * OUTPUT_TO_ZIP_RATIO))

    download_release(share, competencia, files, data_dir, args.download_workers)

    if output_dir.exists() and not resume:
        log.info("Removendo saída anterior de %s para gerar de novo", output_dir)
        shutil.rmtree(output_dir)
    write_state(output_dir, {"competencia": competencia, "status": "em_andamento", "etags": etags,
                             "opcoes": run_signature, "parcial": partial,
                             "iniciado_em": datetime.now().isoformat(timespec="seconds")})

    report = processar(Options(
        input=data_dir,
        output=output_dir,
        tables=frozenset(args.tables or ()),
        workers=args.workers,
        limit=args.limit,
        skip_existing=resume,
    ))
    if report["erros"]:
        raise UpdateError(f"{len(report['erros'])} arquivo(s) com erro no tratamento: {', '.join(report['erros'])}")
    expected = set(args.tables or LAYOUTS)
    empty = sorted(t for t in expected if not report["tabelas"].get(t, {}).get("records"))
    if empty:
        raise UpdateError(f"tabelas sem nenhum registro tratado: {', '.join(empty)}")

    write_state(output_dir, {"competencia": competencia, "status": "concluido", "etags": etags,
                             "opcoes": run_signature, "parcial": partial,
                             "concluido_em": datetime.now().isoformat(timespec="seconds"),
                             "registros": {t: c.get("records", 0) for t, c in report["tabelas"].items()}})
    log.info("Competência %s tratada com sucesso: %s", competencia, output_dir)

    if partial:
        log.info("Execução parcial (--tables/--limit): carga no banco e retenção não aplicadas.")
    else:
        if args.carregar_banco:  # se falhar, a retenção não roda e a carga é retomada na próxima execução
            carregar_no_banco(args, competencia, output_dir, etags, force=args.force)
        prune(args.data_dir, args.keep_downloads, competencia)
        prune(args.output_dir, args.keep_outputs, competencia)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--share-url", default=os.environ.get("RECEITA_SHARE_URL", DEFAULT_SHARE_URL),
                        help="link do compartilhamento da Receita (padrão: variável RECEITA_SHARE_URL ou %(default)s)")
    parser.add_argument("--data-dir", type=Path, default=DATA_PROCESSING_DIR / "data",
                        help="onde os ZIPs são baixados, em <data-dir>/AAAA-MM (padrão: %(default)s)")
    parser.add_argument("--output-dir", type=Path, default=DATA_PROCESSING_DIR / "output",
                        help="onde os CSVs tratados são gerados, em <output-dir>/AAAA-MM (padrão: %(default)s)")
    parser.add_argument("--log-dir", type=Path, default=DATA_PROCESSING_DIR / "logs")
    parser.add_argument("--release", metavar="AAAA-MM", help="competência específica (padrão: a mais recente)")
    parser.add_argument("--tables", nargs="+", choices=sorted(LAYOUTS),
                        help="só estas tabelas (execução parcial, para teste)")
    parser.add_argument("--limit", type=int, help="só os N primeiros registros de cada arquivo (teste)")
    parser.add_argument("--workers", type=int, default=Options.workers, help="processos no tratamento")
    parser.add_argument("--download-workers", type=int, default=4, help="downloads simultâneos (padrão: 4)")
    parser.add_argument("--quiet-hours", type=float, default=3,
                        help="horas sem alterações na pasta da Receita antes de baixar (padrão: 3)")
    parser.add_argument("--keep-downloads", type=int, default=1,
                        help="competências mantidas em data/ (padrão: 1, só a atual)")
    parser.add_argument("--keep-outputs", type=int, default=2,
                        help="competências mantidas em output/ (padrão: 2, a atual e a anterior)")
    parser.add_argument("--check-only", action="store_true", help="só verifica se há competência nova")
    parser.add_argument("--force", action="store_true",
                        help="trata de novo mesmo que já esteja concluída (com --carregar-banco, recarrega o banco)")
    parser.add_argument("--carregar-banco", action="store_true",
                        help="depois do tratamento, esvazia e recarrega o PostgreSQL com a competência")
    add_db_arguments(parser)
    args = parser.parse_args(argv)
    if args.release and not COMPETENCIA.fullmatch(args.release):
        parser.error("--release deve estar no formato AAAA-MM")
    args.tables = frozenset(args.tables or ())
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_dir)
    try:
        with single_instance(args.log_dir / "atualizar_receita.lock"):
            log.info("=== Início da verificação (%s)", args.share_url)
            code = run(args)
            log.info("=== Fim")
            return code
    except AlreadyRunning:
        log.warning("Outra atualização já está em andamento; encerrando.")
        return 0
    except Exception:
        log.exception("Falha na atualização")
        return 1


if __name__ == "__main__":
    sys.exit(main())
