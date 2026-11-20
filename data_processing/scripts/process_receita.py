"""Limpa e padroniza os arquivos do CNPJ (Dados Abertos da Receita Federal).

Para cada arquivo de entrada gera um CSV UTF-8 com:
  1. cabeçalho pré-definido por tipo de tabela (ver rf_layout.py);
  2. ";" dentro de campos preservado (leitura respeita aspas);
  3. registros partidos em várias linhas físicas reconstituídos em uma única linha;
  4. datas em AAAAMMDD (DD/MM/AAAA convertido; vazia/zerada/inválida -> NULL);
  5. capital social com ponto decimal ("1000,50" -> "1000.50");
  6. todos os valores como texto entre aspas (zeros à esquerda preservados);
  7. campos vazios ("") gravados como NULL (sem aspas);
  8. codificação: lê latin-1, grava UTF-8 e corrige defeitos da origem (ver rf_encoding.py).

Uso (a partir da raiz do projeto):
    python data_processing/scripts/process_receita.py
    python data_processing/scripts/process_receita.py --tables empresas socios --workers 4
    python data_processing/scripts/process_receita.py --limit 1000   # amostra para teste

Carga no PostgreSQL (exemplo):
    COPY empresas FROM '.../empresas/arquivo.csv'
        WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL');
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from rf_cleaning import clean_record, column_kinds, format_line, iter_records
from rf_encoding import TextFixer, load_or_build_vocabulary
from rf_layout import LAYOUTS, TableLayout, detect_layout

DATA_PROCESSING_DIR = Path(__file__).resolve().parent.parent
SOURCE_ENCODING = "latin-1"
OUTPUT_ENCODING = "utf-8"


@dataclass(frozen=True)
class Job:
    source: Path
    target: Path
    rejects: Path
    table: str
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
    layout: TableLayout = LAYOUTS[job.table]
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
        open(job.source, encoding=SOURCE_ENCODING, newline="") as src,
        open(tmp_target, "w", encoding="utf-8-sig" if job.bom else OUTPUT_ENCODING, newline="") as dst,
    ):
        dst.write(format_line(layout.columns, job.delimiter, job.null_marker))
        records = iter_records(src, n_fields, stats, rejects)
        if job.limit:
            records = islice(records, job.limit)

        write = dst.write
        for row in records:
            write(format_line(clean_record(row, kinds, stats, fixer), job.delimiter, job.null_marker))
            stats["records"] += 1

    os.replace(tmp_target, job.target)  # só publica o arquivo quando completo

    if rejects:
        job.rejects.parent.mkdir(parents=True, exist_ok=True)
        with open(job.rejects, "w", encoding=OUTPUT_ENCODING, newline="") as out:
            out.write(format_line(("linha_origem", "qtd_campos", "campos"), ";", ""))
            for line_no, fields in rejects:
                out.write(format_line((str(line_no), str(len(fields)), " | ".join(fields)), ";", ""))

    return job.table, job.source.name, stats


def source_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.rglob("*") if p.is_file())


def build_jobs(args: argparse.Namespace, vocabulary: Path | None) -> list[Job]:
    jobs: list[Job] = []
    for source in source_files(args.input):
        layout = detect_layout(source.parent.name, source.name)
        if layout is None:
            print(f"[aviso] tabela não identificada, ignorando: {source}", file=sys.stderr)
            continue
        if args.tables and layout.name not in args.tables:
            continue
        target = args.output / layout.name / f"{source.name}.csv"
        if args.skip_existing and target.exists():
            continue
        jobs.append(
            Job(
                source=source,
                target=target,
                rejects=args.output / "_rejeitados" / layout.name / f"{source.name}.rejeitados.csv",
                table=layout.name,
                delimiter=args.delimiter,
                null_marker=args.null_marker,
                limit=args.limit,
                vocabulary=vocabulary,
                bom=args.bom,
            )
        )
    # Arquivos maiores primeiro: melhor distribuição entre os processos.
    return sorted(jobs, key=lambda j: j.source.stat().st_size, reverse=True)


def latest_input_dir() -> Path | None:
    candidates = sorted((DATA_PROCESSING_DIR / "data").glob("receita-federal-*"))
    return candidates[-1] if candidates else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=latest_input_dir(),
                        help="pasta com os arquivos da Receita (padrão: data/receita-federal-* mais recente)")
    parser.add_argument("--output", type=Path, default=None,
                        help="pasta de saída (padrão: output/<nome da pasta de entrada>)")
    parser.add_argument("--tables", nargs="*", choices=sorted(LAYOUTS), help="processa só estas tabelas")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
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
    if args.output is None:
        args.output = DATA_PROCESSING_DIR / "output" / args.input.name
    return args


def main() -> None:
    args = parse_args()

    vocabulary_path = None
    if not args.no_encoding_fix:
        vocabulary_path = args.output / "vocabulario_acentos.json"
        if args.rebuild_vocab or not vocabulary_path.exists():
            print("Construindo vocabulário de acentos a partir de todos os arquivos (uma vez só)...")
        vocabulary = load_or_build_vocabulary(
            vocabulary_path, source_files(args.input), args.workers, args.rebuild_vocab
        )
        print(f"Vocabulário de acentos: {len(vocabulary):,} palavras ({vocabulary_path})")

    jobs = build_jobs(args, vocabulary_path)
    if not jobs:
        print("Nenhum arquivo para processar.")
        return

    print(f"Processando {len(jobs)} arquivo(s) de {args.input} -> {args.output} ({args.workers} processos)")
    started = time.perf_counter()
    per_table: dict[str, Counter] = {}
    per_file: dict[str, dict] = {}

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_file, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                table, name, stats = future.result()
            except Exception as exc:  # um arquivo com erro não derruba os demais
                print(f"[erro] {job.source}: {exc!r}", file=sys.stderr)
                per_file[str(job.source)] = {"erro": repr(exc)}
                continue
            per_table.setdefault(table, Counter()).update(stats)
            per_file[f"{table}/{name}"] = dict(stats)
            flag = f"  (rejeitados: {stats['rejected']})" if stats["rejected"] else ""
            print(f"  ok  {table}/{name}: {stats['records']:,} registros{flag}")

    elapsed = time.perf_counter() - started
    report = {
        "entrada": str(args.input),
        "saida": str(args.output),
        "segundos": round(elapsed, 1),
        "tabelas": {t: dict(c) for t, c in sorted(per_table.items())},
        "arquivos": dict(sorted(per_file.items())),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "relatorio_processamento.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nConcluído em {elapsed:,.1f}s. Resumo por tabela:")
    for table, stats in sorted(per_table.items()):
        details = ", ".join(f"{k}={v:,}" for k, v in sorted(stats.items()) if k != "records")
        print(f"  {table}: {stats['records']:,} registros | {details}")
    print(f"Relatório: {report_path}")


if __name__ == "__main__":
    main()
