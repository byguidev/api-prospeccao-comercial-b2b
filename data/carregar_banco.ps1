<#
Carrega no PostgreSQL os CSVs gerados por process_receita.py / atualizar_receita.py.

Pula arquivos ja carregados (tabela de controle carga_arquivos) e pede a senha uma unica vez.
O arquivo e ASCII de proposito: o PowerShell 5.1 le .ps1 sem BOM como ANSI e estragaria acentos.

Exemplos (na raiz do projeto):
  powershell -ExecutionPolicy Bypass -File data\carregar_banco.ps1
  powershell -ExecutionPolicy Bypass -File data\carregar_banco.ps1 -Tabelas cnaes   # teste
  powershell -ExecutionPolicy Bypass -File data\carregar_banco.ps1 -Competencia 2026-11
#>
param(
    [string]$Competencia,
    [string[]]$Tabelas = @("cnaes", "motivos", "municipios", "naturezas", "paises", "qualificacoes",
                           "empresas", "estabelecimentos", "socios", "simples"),
    [string]$Servidor = "localhost",
    [int]$Porta = 5432,
    [string]$Usuario = "postgres",
    [string]$Banco = "prospeccao"
)

function Falhar([string]$mensagem) {
    Write-Host "ERRO: $mensagem" -ForegroundColor Red
    exit 1
}

# --- psql ---
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    $bin = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $bin) { Falhar "psql nao encontrado. Instale o cliente do PostgreSQL ou adicione a pasta bin ao PATH." }
    $env:Path = "$($bin.DirectoryName);$env:Path"
}

# --- competencia e pasta de saida ---
$saidaRaiz = Join-Path $PSScriptRoot "output"
if (-not $Competencia) {
    $ultima = Get-ChildItem $saidaRaiz -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}$' } | Sort-Object Name | Select-Object -Last 1
    if (-not $ultima) { Falhar "nenhuma competencia encontrada em $saidaRaiz" }
    $Competencia = $ultima.Name
}
$saida = Join-Path $saidaRaiz $Competencia
if (-not (Test-Path $saida)) { Falhar "pasta nao encontrada: $saida" }

# Contagem de registros por tabela, gerada no tratamento (usada para reconhecer tabelas ja carregadas).
$relatorio = $null
$arquivoRelatorio = Join-Path $saida "relatorio_processamento.json"
if (Test-Path $arquivoRelatorio) { $relatorio = Get-Content $arquivoRelatorio -Raw -Encoding UTF8 | ConvertFrom-Json }

# --- senha (uma vez, so nesta sessao) ---
if (-not $env:PGPASSWORD) {
    $senha = Read-Host "Senha do usuario $Usuario" -AsSecureString
    $env:PGPASSWORD = [System.Net.NetworkCredential]::new("", $senha).Password
}
$pg = @("-h", $Servidor, "-p", "$Porta", "-U", $Usuario, "-d", $Banco, "-X", "-v", "ON_ERROR_STOP=1")

Write-Host "Competencia $Competencia | $Usuario@${Servidor}:$Porta/$Banco"
psql @pg -c "SELECT 1" | Out-Null
if ($LASTEXITCODE -ne 0) { Falhar "nao foi possivel conectar ao banco (veja a mensagem acima)." }

psql @pg -c "CREATE TABLE IF NOT EXISTS carga_arquivos (competencia text, tabela text, arquivo text, carregado_em timestamptz DEFAULT now(), PRIMARY KEY (competencia, arquivo))" | Out-Null
if ($LASTEXITCODE -ne 0) { Falhar "nao foi possivel criar a tabela carga_arquivos." }

# --- carga ---
foreach ($tabela in $Tabelas) {
    $arquivos = Get-ChildItem (Join-Path $saida $tabela) -Filter *.csv -ErrorAction SilentlyContinue | Sort-Object Name
    if (-not $arquivos) { Write-Host "Sem CSVs para '$tabela', ignorando." -ForegroundColor Yellow; continue }

    # Tabela sem nenhum arquivo registrado, mas com linhas: foi carregada antes da tabela de controle existir.
    # Se a contagem bate com o relatorio, registra tudo como concluido; se nao bate, para (carga parcial).
    $registrados = [int](psql @pg -t -A -c "SELECT count(*) FROM carga_arquivos WHERE competencia = '$Competencia' AND tabela = '$tabela'")
    if ($LASTEXITCODE -ne 0) { Falhar "falha ao consultar carga_arquivos." }
    if ($registrados -eq 0) {
        $existentes = [long](psql @pg -t -A -c "SELECT count(*) FROM $tabela")
        if ($LASTEXITCODE -ne 0) { Falhar "falha ao contar as linhas de $tabela." }
        if ($existentes -gt 0) {
            # Cada COPY e atomico, entao o que esta no banco e a soma de arquivos inteiros.
            # Procura qual combinacao de arquivos (contagens do relatorio) soma exatamente as linhas existentes.
            $contagens = @()
            foreach ($a in $arquivos) {
                $info = $null
                if ($relatorio) { $info = $relatorio.arquivos."$tabela/$($a.BaseName)" }
                if ($info) { $contagens += [pscustomobject]@{ Nome = $a.Name; Registros = [long]$info.records } }
            }
            $combinacoes = @()
            if ($contagens.Count -eq $arquivos.Count -and $contagens.Count -le 16) {
                for ($mascara = 1; $mascara -lt (1 -shl $contagens.Count); $mascara++) {
                    $soma = 0L; $nomes = @()
                    for ($i = 0; $i -lt $contagens.Count; $i++) {
                        if ($mascara -band (1 -shl $i)) { $soma += $contagens[$i].Registros; $nomes += $contagens[$i].Nome }
                    }
                    if ($soma -eq $existentes) { $combinacoes += , $nomes }
                }
            }
            if ($combinacoes.Count -ne 1) {
                Falhar "'$tabela' tem $existentes linhas no banco e nao foi possivel identificar quais arquivos ja foram carregados ($($combinacoes.Count) combinacoes possiveis; carga parcial de arquivo ou de outra competencia). Esvazie a tabela com TRUNCATE e rode de novo."
            }
            $valores = ($combinacoes[0] | ForEach-Object { "('$Competencia', '$tabela', '$_')" }) -join ", "
            psql @pg -c "INSERT INTO carga_arquivos (competencia, tabela, arquivo) VALUES $valores ON CONFLICT DO NOTHING" | Out-Null
            if ($LASTEXITCODE -ne 0) { Falhar "falha ao registrar $tabela em carga_arquivos." }
            Write-Host "Tabela '$tabela' ja tinha $existentes linhas: registrado como carregado -> $($combinacoes[0] -join ', ')" -ForegroundColor Cyan
        }
    }

    foreach ($csv in $arquivos) {
        $ja = psql @pg -t -A -c "SELECT 1 FROM carga_arquivos WHERE competencia = '$Competencia' AND arquivo = '$($csv.Name)'"
        if ($LASTEXITCODE -ne 0) { Falhar "falha ao consultar carga_arquivos." }
        if ($ja) { Write-Host "Pulando $($csv.Name) (ja carregado)"; continue }

        $colunas = (Get-Content $csv.FullName -TotalCount 1 -Encoding UTF8) -replace '"', '' -replace ';', ', '
        Write-Host "Carregando $($csv.Name)..."

        # Entra na pasta e usa so o nome do arquivo: evita problemas com acentos no caminho.
        Push-Location $csv.DirectoryName
        try {
            @"
BEGIN;
\copy $tabela ($colunas) FROM '$($csv.Name)' WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL 'NULL', ENCODING 'UTF8')
INSERT INTO carga_arquivos (competencia, tabela, arquivo) VALUES ('$Competencia', '$tabela', '$($csv.Name)');
COMMIT;
"@ | psql @pg
            $codigo = $LASTEXITCODE
        }
        finally { Pop-Location }

        if ($codigo -ne 0) { Falhar "falha ao carregar $($csv.Name). A transacao foi desfeita; corrija e rode de novo." }
    }
}
Write-Host "Concluido." -ForegroundColor Green
