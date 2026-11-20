# Data Processing — CNPJ (Dados Abertos da Receita Federal)

Scripts que limpam e padronizam os arquivos do CNPJ publicados pela Receita Federal, gerando CSVs prontos para carga no PostgreSQL.

## Requisitos

- Python 3.12+ (testado com 3.14)
- Sem dependências externas (somente biblioteca padrão)

## Estrutura

```
data_processing/
├── data/
│   └── receita-federal-AAAA-MM/      # arquivos originais, uma pasta por tabela
│       ├── empresas/
│       ├── estabelecimentos/
│       ├── socios/
│       ├── simples/
│       └── cnaes/ motivos/ municipios/ naturezas/ paises/ qualificacoes/
├── output/
│   └── receita-federal-AAAA-MM/      # gerado pelo script
│       ├── <tabela>/<arquivo>.csv
│       ├── _rejeitados/              # registros que não puderam ser reconstituídos
│       ├── vocabulario_acentos.json  # cache usado na correção de acentos
│       └── relatorio_processamento.json
└── scripts/
    ├── process_receita.py            # ponto de entrada (CLI)
    ├── rf_layout.py                  # cabeçalhos e tipos de coluna de cada tabela
    ├── rf_cleaning.py                # leitura, datas, decimais, NULL
    ├── rf_encoding.py                # correção de codificação
    └── test_rf_cleaning.py           # testes
```

## O que o processamento faz

| # | Regra | Exemplo |
|---|---|---|
| 1 | Adiciona cabeçalho pré-definido por tabela | `"cnpj_basico";"razao_social";...` |
| 2 | `;` dentro de aspas faz parte do valor, não separa colunas | `"QUADRA 271;LOTE 18"` continua um campo só |
| 3 | Registros quebrados em várias linhas físicas viram uma linha | `"HARMON LIDICE⏎"` → `"HARMON LIDICE"` |
| 4 | Datas convertidas para `AAAAMMDD`; vazias, zeradas ou inválidas → `NULL` | `18/04/2023` → `20230418`; `00000000` → `NULL` |
| 5 | Capital social com ponto decimal | `1.234,56` → `1234.56` |
| 6 | Todo valor sai entre aspas (texto), preservando zeros à esquerda | `"0001"`, `"08371299"` |
| 7 | Campos vazios gravados como `NULL` (sem aspas) | `""` → `NULL` |
| 8 | Lê latin-1, grava UTF-8 e corrige defeitos da origem | ver abaixo |

### Correções de codificação

| Defeito na origem | Exemplo | Correção |
|---|---|---|
| Acento perdido, gravado como `?` | `S?O`, `JO?O`, `T?RREO` | `SÃO`, `JOÃO`, `TÉRREO` (via vocabulário extraído dos próprios dados) |
| Apóstrofo gravado como `?` | `D?AGUA`, `KID?S` | `D'AGUA`, `KID'S` |
| Ordinal gravado como `?` | `N? 01`, `2?ANDAR` | `Nº 01`, `2ºANDAR` |
| Trecho UTF-8 dentro de arquivo latin-1 (mojibake) | `RaÃ­zes` | `Raízes` |
| Caracteres de controle | TAB, `\x00`, `\x7F`, `\x8F` | TAB → espaço; demais removidos |

Um `?` só é substituído quando há correspondência segura (a palavra acentuada aparece ao menos 3 vezes e representa 90% ou mais das grafias possíveis). Casos ambíguos (`AM?LIA`: AMÉLIA ou AMÁLIA?) e pontos de interrogação reais (`QUE TAL?`) são mantidos.

## Como rodar

Todos os comandos devem ser executados a partir da **raiz do projeto** e funcionam igual no PowerShell e no Git Bash.

### Comandos básicos

| Objetivo | Comando |
|---|---|
| Processar tudo (configuração padrão) | `python data_processing/scripts/process_receita.py` |
| Teste rápido, 1.000 registros por arquivo | `python data_processing/scripts/process_receita.py --limit 1000` |
| Só algumas tabelas | `python data_processing/scripts/process_receita.py --tables empresas socios` |
| Continuar uma execução interrompida | `python data_processing/scripts/process_receita.py --skip-existing` |
| Ver a ajuda com todas as opções | `python data_processing/scripts/process_receita.py --help` |
| Rodar os testes | `python -m unittest discover data_processing/scripts` |

### Opções

| Opção | O que faz | Padrão |
|---|---|---|
| `--input PASTA` | Pasta com os arquivos da Receita | `data/receita-federal-*` mais recente |
| `--output PASTA` | Pasta de saída | `output/<nome da pasta de entrada>` |
| `--tables T1 T2 ...` | Processa só as tabelas indicadas: `empresas`, `estabelecimentos`, `socios`, `simples`, `cnaes`, `motivos`, `municipios`, `naturezas`, `paises`, `qualificacoes` | todas |
| `--workers N` | Quantos arquivos processar em paralelo | nº de núcleos − 1 |
| `--limit N` | Processa só os N primeiros registros de cada arquivo | sem limite |
| `--skip-existing` | Pula os arquivos que já foram gerados | desligado |
| `--delimiter X` | Separador de colunas na saída | `;` |
| `--null-marker X` | Como o NULL é escrito na saída; `""` deixa o campo vazio | `NULL` |
| `--bom` | Grava UTF-8 com BOM, para o Excel mostrar os acentos certos | desligado |
| `--rebuild-vocab` | Monta de novo a lista de palavras acentuadas usada para corrigir os `?` | desligado |
| `--no-encoding-fix` | Desliga as correções de codificação | desligado |

### Combinações úteis

| Cenário | Comando |
|---|---|
| Abrir os CSVs no Excel | `python data_processing/scripts/process_receita.py --bom` |
| Testar só `estabelecimentos` usando 4 processos | `python data_processing/scripts/process_receita.py --tables estabelecimentos --limit 5000 --workers 4` |
| Processar uma pasta específica | `python data_processing/scripts/process_receita.py --input data_processing/data/receita-federal-2026-11 --output D:/saida_rf` |
| NULL como campo vazio, padrão do `COPY` do PostgreSQL | `python data_processing/scripts/process_receita.py --null-marker ""` |

## Observações

- **Primeira execução:** o script monta o vocabulário de acentos lendo todos os arquivos (cerca de 1,5 minuto) e salva em `output/<dataset>/vocabulario_acentos.json`. As execuções seguintes reaproveitam esse arquivo; use `--rebuild-vocab` ao trocar de dataset ou para refazê-lo.
- **Espaço em disco:** a saída completa ocupa aproximadamente o mesmo que a entrada (~30 GB).
- **Arquivos parciais:** cada CSV é gravado como `.tmp` e só renomeado ao terminar, então uma execução interrompida não deixa arquivos incompletos. Use `--skip-existing` para retomar.
- **Rejeitados:** registros que não fecham com o número de colunas esperado vão para `output/<dataset>/_rejeitados/`, com o número da linha original.
- **Relatório:** `relatorio_processamento.json` traz as contagens por tabela e por arquivo (registros, NULLs, datas convertidas/inválidas, correções `enc_*` etc.).

## Carga no PostgreSQL

Com a saída padrão (`NULL` sem aspas):

```sql
COPY empresas FROM 'C:/.../output/receita-federal-2026-11/empresas/K3241.K03200Y0.D61114.EMPRECSV.csv'
    WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL', ENCODING 'UTF8');
```

Se a saída foi gerada com `--null-marker ""`, omita a cláusula `NULL 'NULL'`.
