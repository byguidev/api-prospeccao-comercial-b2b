# Data Processing — CNPJ (Dados Abertos da Receita Federal)

Scripts que baixam, todo mês, os arquivos do CNPJ publicados pela Receita Federal e os limpam e padronizam, gerando CSVs prontos para carga no PostgreSQL.

## Requisitos

- Python 3.12+ (declarado em `pyproject.toml`; testado com 3.12, 3.13 e 3.14)
- Sem dependências externas (somente biblioteca padrão)
- Espaço em disco: cerca de 8 GB para os ZIPs de uma competência + cerca de 35 GB para os CSVs gerados

## Estrutura

```
data_processing/
├── data/
│   └── AAAA-MM/                      # ZIPs exatamente como publicados pela Receita (não extrair)
│       ├── Cnaes.zip  Motivos.zip  Municipios.zip  Naturezas.zip  Paises.zip  Qualificacoes.zip
│       ├── Empresas0.zip ... Empresas9.zip
│       ├── Estabelecimentos0.zip ... Estabelecimentos9.zip
│       ├── Socios0.zip ... Socios9.zip
│       ├── Simples.zip
│       └── _manifesto.json           # tamanho/ETag de cada ZIP já baixado e validado
├── output/
│   └── AAAA-MM/                      # gerado pelo tratamento
│       ├── <tabela>/<ZIP de origem>.csv   # ex.: empresas/Empresas0.csv, simples/Simples.csv
│       ├── _rejeitados/              # registros que não puderam ser reconstituídos
│       ├── _atualizacao.json         # estado da atualização automática (ETags tratados, status)
│       ├── vocabulario_acentos.json  # cache usado na correção de acentos
│       └── relatorio_processamento.json
├── logs/
│   └── atualizar_receita.log         # histórico das execuções automáticas
├── agendar_atualizacao.ps1           # registra a tarefa diária no Agendador de Tarefas do Windows
└── scripts/
    ├── atualizar_receita.py          # atualização automática: verifica, baixa e trata (CLI)
    ├── process_receita.py            # tratamento de uma competência já baixada (CLI)
    ├── rf_download.py                # listagem e download do compartilhamento da Receita
    ├── rf_source.py                  # leitura dos ZIPs (sem extrair) e identificação das tabelas
    ├── rf_layout.py                  # cabeçalhos e tipos de coluna de cada tabela
    ├── rf_cleaning.py                # leitura, datas, decimais, NULL
    ├── rf_encoding.py                # correção de codificação
    ├── test_rf_cleaning.py           # testes das regras de limpeza
    └── test_atualizacao.py           # testes de leitura dos ZIPs, download e atualização
```

Cada ZIP contém um único arquivo com o nome original da Receita (ex.: `Empresas0.zip` → `K3241.K03200Y0.D61114.EMPRECSV`). Os ZIPs são lidos diretamente, sem extração, e a tabela é identificada pelo nome do ZIP. Pastas com arquivos já extraídos continuam aceitas pelo `process_receita.py` (tabela identificada pela pasta ou pelo nome do arquivo).

## Atualização automática mensal

A Receita publica uma pasta por competência (`2026-11/`, `2026-12/`...) no compartilhamento público
<https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9>, sem data fixa no mês. Por isso a atualização roda **todo dia** e só trabalha quando há algo novo:

1. Lista as competências publicadas (via WebDAV público do Nextcloud) e escolhe a mais recente.
2. **Espera** se a competência estiver incompleta (falta alguma das 10 tabelas) ou se algum arquivo foi alterado há menos de 3 horas (upload da Receita em andamento).
3. **Encerra** se a competência já foi tratada e nenhum arquivo mudou desde então (compara os ETags).
4. Confere o espaço em disco e baixa os ZIPs para `data/AAAA-MM/`, 4 por vez: cada arquivo vai para `.part`, é validado (tamanho + CRC do ZIP) e só então renomeado. Downloads interrompidos são retomados de onde pararam; falhas de rede são repetidas.
5. Trata os arquivos, gerando `output/AAAA-MM/`. Uma execução interrompida é retomada sem refazer os CSVs já concluídos.
6. Aplica a retenção: mantém em `data/` só a competência atual e em `output/` a atual e a anterior. Somente pastas no formato `AAAA-MM` são removidas.

Se a Receita **republicar** algum arquivo de uma competência já tratada (ETag diferente), a execução seguinte baixa só esse arquivo e gera a saída de novo.

Tudo é registrado em `logs/atualizar_receita.log` (rotacionado em 5 MB, 5 arquivos). O código de saída é `0` para sucesso ou "nada a fazer" e `1` para falha.

### Agendar no Windows

Na raiz do projeto, no PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File data_processing\agendar_atualizacao.ps1                 # todo dia às 03:00
powershell -ExecutionPolicy Bypass -File data_processing\agendar_atualizacao.ps1 -Horario 02:30  # outro horário
powershell -ExecutionPolicy Bypass -File data_processing\agendar_atualizacao.ps1 -Remover        # remove a tarefa
```

A tarefa roda com `pythonw.exe` (sem janela), só quando o usuário está conectado, com até 12 horas de duração e sem instâncias simultâneas. Se o computador estiver desligado no horário, ela roda assim que ele for ligado. Para executar na hora: `Start-ScheduledTask -TaskName 'CNPJ Receita Federal - atualizacao'`.

### Comandos

| Objetivo | Comando |
|---|---|
| Execução normal (a mesma da tarefa agendada) | `python data_processing/scripts/atualizar_receita.py` |
| Só verificar se há competência nova | `python data_processing/scripts/atualizar_receita.py --check-only` |
| Baixar e tratar uma competência específica de novo | `python data_processing/scripts/atualizar_receita.py --release 2026-10 --force` |
| Teste rápido com tabelas pequenas | `python data_processing/scripts/atualizar_receita.py --tables cnaes motivos --limit 100` |

| Opção | O que faz | Padrão |
|---|---|---|
| `--share-url URL` | Link do compartilhamento da Receita (também via variável `RECEITA_SHARE_URL`) | link acima |
| `--release AAAA-MM` | Competência específica | a mais recente |
| `--data-dir` / `--output-dir` / `--log-dir` | Pastas de download, saída e log | `data/`, `output/`, `logs/` |
| `--tables T1 T2 ...` | Só estas tabelas (execução parcial, para teste: não marca a competência como concluída e não aplica retenção) | todas |
| `--limit N` | Só os N primeiros registros de cada arquivo (teste) | sem limite |
| `--workers N` | Processos no tratamento | nº de núcleos − 1 |
| `--download-workers N` | Downloads simultâneos | 4 |
| `--quiet-hours H` | Horas sem alterações na pasta da Receita antes de baixar | 3 |
| `--keep-downloads N` / `--keep-outputs N` | Competências mantidas em `data/` / `output/` | 1 / 2 |
| `--check-only` | Só informa se há competência pendente | desligado |
| `--force` | Trata de novo mesmo que já esteja concluída | desligado |

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

## Tratamento manual de uma competência já baixada

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
| Rodar os testes em outra versão do Python (requer `uv`) | `uv run --no-project --python 3.12 python -m unittest discover data_processing/scripts` |

### Opções

| Opção | O que faz | Padrão |
|---|---|---|
| `--input PASTA` | Pasta da competência, com os ZIPs da Receita (ou arquivos já extraídos) | `data/AAAA-MM` mais recente |
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
| Processar uma pasta específica | `python data_processing/scripts/process_receita.py --input data_processing/data/2026-11 --output D:/saida_rf` |
| NULL como campo vazio, padrão do `COPY` do PostgreSQL | `python data_processing/scripts/process_receita.py --null-marker ""` |

## Observações

- **Vocabulário de acentos:** é montado na primeira execução de cada competência lendo todos os arquivos (alguns minutos) e salvo em `output/<competência>/vocabulario_acentos.json`. As execuções seguintes da mesma competência reaproveitam esse arquivo; use `--rebuild-vocab` para refazê-lo.
- **Arquivos parciais:** cada CSV é gravado como `.tmp` e só renomeado ao terminar, então uma execução interrompida não deixa arquivos incompletos. Use `--skip-existing` para retomar.
- **Rejeitados:** registros que não fecham com o número de colunas esperado vão para `output/<competência>/_rejeitados/`, com o número da linha original.
- **Relatório:** `relatorio_processamento.json` traz as contagens por tabela e por arquivo (ZIP/arquivo de origem, registros, NULLs, datas convertidas/inválidas, correções `enc_*` etc.) e a lista de erros.
- **Integridade:** o CRC de cada arquivo é conferido no download e de novo na leitura do ZIP; um arquivo corrompido gera erro em vez de dados truncados.

## Carga no PostgreSQL

Com a saída padrão (`NULL` sem aspas):

```sql
COPY empresas FROM 'C:/.../output/2026-11/empresas/Empresas0.csv'
    WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL', ENCODING 'UTF8');
```

Se a saída foi gerada com `--null-marker ""`, omita a cláusula `NULL 'NULL'`.
