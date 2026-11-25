"""Limpa e padroniza os arquivos do CNPJ (Dados Abertos da Receita Federal).

A entrada é a pasta de uma competência como baixada do site da Receita (data/raw/AAAA-MM/*.zip);
os ZIPs são lidos diretamente, sem extração. Para cada arquivo gera um CSV UTF-8 com:
  1. cabeçalho pré-definido por tipo de tabela (ver rf_layout.py);
  2. ";" dentro de campos preservado (leitura respeita aspas);
  3. registros partidos em várias linhas físicas reconstituídos em uma única linha;
  4. datas em AAAAMMDD (DD/MM/AAAA convertido; vazia/zerada/inválida -> NULL);
  5. capital social com ponto decimal ("1000,50" -> "1000.50");
  6. todos os valores como texto entre aspas (zeros à esquerda preservados);
  7. campos vazios ("") gravados como NULL (sem aspas);
  8. codificação: lê latin-1, grava UTF-8 e corrige defeitos da origem (ver rf_encoding.py).

Uso (a partir da raiz do projeto):
    python data/scripts/process_receita.py
    python data/scripts/process_receita.py --tables empresas socios --workers 4
    python data/scripts/process_receita.py --limit 1000   # amostra para teste

Carga no PostgreSQL (exemplo):
    COPY empresas FROM '.../empresas/Empresas0.csv'
        WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL');
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

from rf_cleaning import (
    clean_record,
    column_kinds,
    drop_placeholder_duplicates,
    format_line,
    iter_numbered_records,
)
from rf_encoding import TextFixer, load_or_build_vocabulary
from rf_layout import LAYOUTS, TableLayout
from rf_source import Source, discover_sources

DATA_DIR = Path(__file__).resolve().parent.parent
SOURCE_ENCODING = "latin-1"
OUTPUT_ENCODING = "utf-8"
REPORT_NAME = "relatorio_processamento.json"
VOCABULARY_NAME = "vocabulario_acentos.json"
COMPETENCIA = re.compile(r"\d{4}-\d{2}")

log = logging.getLogger("receita.processamento")


@dataclass(frozen=True)
class Options:
    input: Path
    output: Path
    tables: frozenset[str] = field(default_factory=frozenset)  # vazio = todas
    workers: int = max(1, (os.cpu_count() or 2) - 1)
    delimiter: str = ";"
    null_marker: str = "NULL"
    limit: int | None = None
    skip_existing: bool = False
    encoding_fix: bool = True
    rebuild_vocab: bool = False
    bom: bool = False


@dataclass(frozen=True)
class Job:
    source: Source
    target: Path
    rejects: Path
    delimiter: str
    null_marker: str
    limit: int | None
    vocabulary: Path | None  # None = sem correção de codificação
    bom: bool


_fixers: dict[Path | None, TextFixer | None] = {}


def _fixer_for(vocabulary: Path | None) -> TextFixer | None:
    """Carrega o vocabulário uma vez por processo."""
    if vocabulary not in _fixers:
        _fixers[vocabulary] = (
            TextFixer(json.loads(vocabulary.read_text(encoding="utf-8"))) if vocabulary else None
        )
    return _fixers[vocabulary]


def process_file(job: Job) -> tuple[str, str, Counter]:
    """Processa um arquivo. Executa em processo separado."""
    layout: TableLayout = LAYOUTS[job.source.table]
    n_fields = len(layout.columns)
    kinds = column_kinds(
        n_fields, layout.indexes_of(layout.date_columns), layout.indexes_of(layout.decimal_columns)
    )
    fixer = _fixer_for(job.vocabulary)
    stats: Counter = Counter()
    rejects: list[tuple[int, list[str]]] = []

    job.target.parent.mkdir(parents=True, exist_ok=True)
    tmp_target = job.target.with_suffix(job.target.suffix + ".tmp")

    with (
        job.source.open_text(SOURCE_ENCODING) as src,
        open(tmp_target, "w", encoding="utf-8-sig" if job.bom else OUTPUT_ENCODING, newline="") as dst,
    ):
        dst.write(format_line(layout.columns, job.delimiter, job.null_marker))
        records = iter_numbered_records(src, n_fields, stats, rejects)
        if layout.key_columns:
            records = drop_placeholder_duplicates(records, layout.key_indexes(), stats, rejects)
        if job.limit:
            records = islice(records, job.limit)

        write = dst.write
        for _, row in records:
            write(format_line(clean_record(row, kinds, stats, fixer), job.delimiter, job.null_marker))
            stats["records"] += 1

    os.replace(tmp_target, job.target)  # só publica o arquivo quando completo

    if rejects:
        job.rejects.parent.mkdir(parents=True, exist_ok=True)
        with open(job.rejects, "w", encoding=OUTPUT_ENCODING, newline="") as out:
            out.write(format_line(("linha_origem", "qtd_campos", "campos"), ";", ""))
            for line_no, fields in rejects:
                out.write(format_line((str(line_no), str(len(fields)), " | ".join(fields)), ";", ""))

    return job.source.table, job.source.output_stem, stats


def build_jobs(opts: Options, sources: list[Source], vocabulary: Path | None) -> list[Job]:
    jobs: list[Job] = []
    for source in sources:
        if opts.tables and source.table not in opts.tables:
            continue
        target = opts.output / source.table / f"{source.output_stem}.csv"
        if opts.skip_existing and target.exists():
            continue
        jobs.append(
            Job(
                source=source,
                target=target,
                rejects=opts.output / "_rejeitados" / source.table / f"{source.output_stem}.rejeitados.csv",
                delimiter=opts.delimiter,
                null_marker=opts.null_marker,
                limit=opts.limit,
                vocabulary=vocabulary,
                bom=opts.bom,
            )
        )
    # Arquivos maiores primeiro: melhor distribuição entre os processos.
    return sorted(jobs, key=lambda j: j.source.size, reverse=True)


def _previous_files(report_path: Path) -> dict[str, dict]:
    try:
        return json.loads(report_path.read_text(encoding="utf-8")).get("arquivos", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _totals_by_table(per_file: dict[str, dict]) -> dict[str, Counter]:
    totals: dict[str, Counter] = {}
    for key, stats in per_file.items():
        counts = {k: v for k, v in stats.items() if isinstance(v, int)}
        totals.setdefault(key.split("/", 1)[0], Counter()).update(counts)
    return totals


def processar(opts: Options) -> dict:
    """Processa uma competência e grava o relatório. Retorna o relatório (``"erros"`` lista falhas)."""
    sources = discover_sources(opts.input)
    if not sources:
        raise FileNotFoundError(f"nenhum arquivo da Receita encontrado em {opts.input}")

    vocabulary_path = None
    if opts.encoding_fix:
        vocabulary_path = opts.output / VOCABULARY_NAME
        if opts.rebuild_vocab or not vocabulary_path.exists():
            log.info("Construindo vocabulário de acentos a partir de todos os arquivos (uma vez só)...")
        vocabulary = load_or_build_vocabulary(vocabulary_path, sources, opts.workers, opts.rebuild_vocab)
        log.info("Vocabulário de acentos: %s palavras (%s)", f"{len(vocabulary):,}", vocabulary_path)

    jobs = build_jobs(opts, sources, vocabulary_path)
    log.info("Processando %d arquivo(s) de %s -> %s (%d processos)", len(jobs), opts.input, opts.output, opts.workers)
    started = time.perf_counter()
    per_table: dict[str, Counter] = {}
    per_file: dict[str, dict] = {}
    errors: dict[str, str] = {}

    if jobs:
        with ProcessPoolExecutor(max_workers=opts.workers) as pool:
            futures = {pool.submit(process_file, job): job for job in jobs}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    table, stem, stats = future.result()
                except Exception as exc:  # um arquivo com erro não derruba os demais
                    log.error("falha ao processar %s: %r", job.source.label, exc)
                    errors[job.source.label] = repr(exc)
                    continue
                per_table.setdefault(table, Counter()).update(stats)
                per_file[f"{table}/{stem}"] = {"origem": job.source.label, **stats}
                flag = f"  (rejeitados: {stats['rejected']})" if stats["rejected"] else ""
                log.info("  ok  %s/%s: %s registros%s", table, stem, f"{stats['records']:,}", flag)

    elapsed = time.perf_counter() - started
    report_path = opts.output / REPORT_NAME
    if opts.skip_existing:  # retomada: preserva as contagens dos arquivos gerados na execução anterior
        per_file = _previous_files(report_path) | per_file
        per_table = _totals_by_table(per_file)
    report = {
        "entrada": str(opts.input),
        "saida": str(opts.output),
        "segundos": round(elapsed, 1),
        "tabelas": {t: dict(c) for t, c in sorted(per_table.items())},
        "arquivos": dict(sorted(per_file.items())),
        "erros": errors,
    }
    opts.output.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info("Concluído em %ss. Resumo por tabela:", f"{elapsed:,.1f}")
    for table, stats in sorted(per_table.items()):
        details = ", ".join(f"{k}={v:,}" for k, v in sorted(stats.items()) if k != "records")
        log.info("  %s: %s registros | %s", table, f"{stats['records']:,}", details)
    if errors:
        log.error("%d arquivo(s) com erro: %s", len(errors), ", ".join(sorted(errors)))
    log.info("Relatório: %s", report_path)
    return report


def latest_input_dir() -> Path | None:
    """Pasta data/raw/AAAA-MM mais recente."""
    candidates = sorted(
        p for p in (DATA_DIR / "raw").glob("*") if p.is_dir() and COMPETENCIA.fullmatch(p.name)
    )
    return candidates[-1] if candidates else None


def parse_args() -> Options:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=latest_input_dir(),
                        help="pasta da competência, com os ZIPs da Receita (padrão: data/raw/AAAA-MM mais recente)")
    parser.add_argument("--output", type=Path, default=None,
                        help="pasta de saída (padrão: output/<nome da pasta de entrada>)")
    parser.add_argument("--tables", nargs="*", choices=sorted(LAYOUTS), help="processa só estas tabelas")
    parser.add_argument("--workers", type=int, default=Options.workers)
    parser.add_argument("--delimiter", default=";", help='separador da saída (padrão: ";")')
    parser.add_argument("--null-marker", default="NULL",
                        help='representação de NULL na saída, sem aspas (padrão: NULL; use "" para vazio)')
    parser.add_argument("--limit", type=int, default=None, help="processa só os N primeiros registros de cada arquivo")
    parser.add_argument("--skip-existing", action="store_true", help="pula arquivos já gerados")
    parser.add_argument("--no-encoding-fix", action="store_true",
                        help="não corrige acentos perdidos/mojibake/caracteres de controle")
    parser.add_argument("--rebuild-vocab", action="store_true",
                        help="refaz o vocabulário de acentos mesmo que já exista")
    parser.add_argument("--bom", action="store_true",
                        help="grava UTF-8 com BOM (necessário para o Excel exibir acentos corretamente)")
    args = parser.parse_args()

    if args.input is None or not args.input.is_dir():
        parser.error(f"pasta de entrada inválida: {args.input}")
    return Options(
        input=args.input,
        output=args.output or DATA_DIR / "output" / args.input.name,
        tables=frozenset(args.tables or ()),
        workers=args.workers,
        delimiter=args.delimiter,
        null_marker=args.null_marker,
        limit=args.limit,
        skip_existing=args.skip_existing,
        encoding_fix=not args.no_encoding_fix,
        rebuild_vocab=args.rebuild_vocab,
        bom=args.bom,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    report = processar(parse_args())
    sys.exit(1 if report["erros"] else 0)


if __name__ == "__main__":
    main()
