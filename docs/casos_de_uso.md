# Casos de uso

Este documento descreve o que a API de Prospecção Comercial B2B faz e quem a usa. Os dados vêm do CNPJ publicado como dados abertos pela Receita Federal (empresas, estabelecimentos, sócios, Simples/MEI e tabelas de códigos). Os scripts de `data/` baixam e tratam esses arquivos, e a API em `api/` consulta o resultado no PostgreSQL.

A ideia é ajudar quem vende para empresas a encontrar as que se encaixam no perfil de cliente que procura e a consultar os dados cadastrais de cada uma.

## Premissas

A API é de uso interno. O repositório é aberto, e quem quiser pode clonar e rodar a própria instância, mas ela não é um serviço público. Por isso não há autenticação, cota por cliente nem SLA, e ela não deve ser exposta à internet. A configuração (banco de dados e demais parâmetros) vem de variáveis de ambiente.

A API só lê os dados. Ela entrega as informações como a Receita as publica e não controla a finalidade de uso dos contatos (e-mail e telefone). Quem opera a instância responde pelo uso, inclusive perante a LGPD.

## Atores

- **Usuário comercial:** vendedor, SDR ou analista que prospecta clientes, normalmente por meio de um front-end sobre a API.
- **Sistema integrador:** aplicação (CRM, automação) que consome a API por HTTP. Faz as mesmas consultas do usuário comercial.
- **Administrador:** quem opera a carga dos dados e acompanha o estado da base.
- **Agendador de tarefas:** tarefa diária do Windows que executa a atualização automática.
- **Receita Federal:** fonte dos arquivos mensais, publicados em um compartilhamento público.
- **PostgreSQL:** banco que recebe os dados tratados e responde às consultas.

## Lista de casos de uso

| ID | Caso de uso | Ator principal |
|---|---|---|
| UC01 | Buscar empresas por critérios | Usuário comercial, sistema integrador |
| UC02 | Consultar empresa por CNPJ | Usuário comercial, sistema integrador |
| UC03 | Listar sócios de uma empresa | Usuário comercial, sistema integrador |
| UC04 | Consultar tabelas de códigos | Usuário comercial, sistema integrador |
| UC05 | Exportar resultado de busca | Usuário comercial |
| UC06 | Atualizar a base com a competência mais recente | Agendador de tarefas |
| UC07 | Tratar os arquivos de uma competência | Administrador |
| UC08 | Carregar os dados tratados no PostgreSQL | Administrador |
| UC09 | Verificar a situação da base | Administrador |

UC06 e UC07 já estão implementados nos scripts de `data/`. Os demais ainda não têm código.

Cada caso de uso é descrito em duas partes: o **Fluxo** (passos principais e variações, inclusive os erros) e as **Regras de negócio** (as condições e os limites que o fluxo respeita). As regras são numeradas como `RNxx.y`, em que `xx` é o número do caso de uso.

---

## Consulta

### UC01. Buscar empresas por critérios

O ator monta um perfil de cliente com filtros e recebe a lista paginada de estabelecimentos que o atendem.

#### Fluxo

**Fluxo principal**

1. O ator envia os filtros, a página e o tamanho da página.
2. A API valida os parâmetros.
3. A API busca os estabelecimentos que atendem a todos os filtros informados.
4. A API devolve a página, ordenada por CNPJ, com o total de resultados. Cada item traz o CNPJ completo, a razão social, o nome fantasia, o CNAE principal, o município e a UF, o porte, a situação cadastral e os contatos.

**Fluxos alternativos e exceções**

- **A1. Parâmetro inválido** (UF inexistente, CNAE malformado, intervalo de datas invertido, página negativa): a API responde `400` com o campo problemático.
- **A2. Tamanho de página acima do máximo configurado:** a API limita ao máximo e informa na resposta o tamanho aplicado.
- **A3. Nenhum estabelecimento atende aos filtros:** a resposta é uma lista vazia, sem erro.

#### Regras de negócio

- **RN01.1.** Todos os filtros são opcionais e se combinam (a busca traz só os estabelecimentos que atendem a todos os informados). Os filtros disponíveis são: atividade econômica (CNAE principal ou secundário), UF, município, situação cadastral, matriz ou filial, porte, faixa de capital social, período de início da atividade, optante do Simples ou do MEI, natureza jurídica e presença de e-mail ou telefone.
- **RN01.2.** Sem filtro de situação cadastral, a busca traz só estabelecimentos ativos. Quem quiser outras situações precisa pedi-las.
- **RN01.3.** Sem filtro de matriz ou filial, a busca traz os dois tipos.
- **RN01.4.** Cada estabelecimento é um resultado. Uma empresa com 50 filiais aparece 50 vezes, e o filtro de matriz ou filial serve para restringir quando for o caso.
- **RN01.5.** O CNPJ completo é a junção de CNPJ básico, ordem e dígito verificador.
- **RN01.6.** O CNAE secundário é um campo com vários códigos separados por vírgula, e o filtro considera todos.
- **RN01.7.** A ordenação é por CNPJ, para a paginação não repetir nem perder itens.
- **RN01.8.** Toda listagem é paginada, e o tamanho máximo de página é configurável (RNF02).

### UC02. Consultar empresa por CNPJ

O ator informa um CNPJ, com ou sem máscara, e recebe todos os dados disponíveis do estabelecimento e da empresa a que ele pertence.

#### Fluxo

**Fluxo principal**

1. O ator informa o CNPJ de 14 dígitos.
2. A API normaliza o número e confere os dígitos verificadores.
3. A API localiza o estabelecimento e a empresa.
4. A API devolve os dados da empresa (razão social, natureza jurídica, capital social, porte), do estabelecimento (nome fantasia, situação cadastral com data e motivo, data de início, CNAEs, endereço, contatos) e do Simples/MEI.

**Fluxos alternativos e exceções**

- **A1. CNPJ com tamanho ou dígito verificador inválido:** a API responde `400`.
- **A2. CNPJ válido que não está na base:** a API responde `404`.
- **A3. Empresa sem registro no Simples/MEI:** o bloco do Simples/MEI vem vazio, sem erro.

#### Regras de negócio

- **RN02.1.** O CNPJ pode ser informado com ou sem máscara e deve ter 14 dígitos depois de normalizado.
- **RN02.2.** Os dígitos verificadores são conferidos antes de qualquer consulta ao banco.
- **RN02.3.** Os códigos de CNAE, município, natureza, motivo e país vêm acompanhados da descrição.
- **RN02.4.** A ausência de registro no Simples/MEI é comum e não é erro.

### UC03. Listar sócios de uma empresa

Serve para descobrir quem são os sócios e chegar ao decisor.

#### Fluxo

**Fluxo principal**

1. O ator informa o CNPJ.
2. A API normaliza o número e confere os dígitos verificadores, como no UC02.
3. A API localiza a empresa.
4. A API devolve o quadro societário: tipo do sócio, nome ou razão social, qualificação, data de entrada, faixa etária e representante legal, quando houver.

**Fluxos alternativos e exceções**

- **A1. CNPJ inválido:** a API responde `400`.
- **A2. CNPJ inexistente na base:** a API responde `404`.
- **A3. Empresa sem sócios na base:** a API devolve lista vazia.

#### Regras de negócio

- **RN03.1.** Os sócios pertencem à empresa, não a um estabelecimento. Por isso matriz e filiais mostram a mesma lista.
- **RN03.2.** O tipo do sócio é pessoa jurídica, pessoa física ou estrangeiro.
- **RN03.3.** O CPF dos sócios pessoa física já vem mascarado da Receita, e a API o mantém assim, sem tentar reconstituí-lo nem aceitá-lo como filtro.
- **RN03.4.** A validação do CNPJ e os códigos de erro seguem as regras do UC02 (RN02.1 e RN02.2).

### UC04. Consultar tabelas de códigos

O ator escolhe uma tabela de códigos e recebe os pares código e descrição. É o que um front-end usa para montar os campos de seleção dos filtros do UC01.

#### Fluxo

**Fluxo principal**

1. O ator escolhe uma das tabelas: CNAE, município, natureza jurídica, qualificação de sócio, país ou motivo da situação cadastral.
2. O ator informa a página, o tamanho da página e, opcionalmente, um texto de busca.
3. A API consulta a tabela escolhida.
4. A API devolve a página com os pares código e descrição.

#### Regras de negócio

- **RN04.1.** As tabelas disponíveis são CNAE, município, natureza jurídica, qualificação de sócio, país e motivo da situação cadastral.
- **RN04.2.** A listagem é paginada (RNF02), e a busca textual é opcional.
- **RN04.3.** Como essas tabelas mudam pouco, a API pode mantê-las em cache até a próxima carga (UC08).

### UC05. Exportar resultado de busca

O ator pede em CSV a mesma lista que o UC01 devolveria, para levar a outra ferramenta.

#### Fluxo

**Fluxo principal**

1. O ator envia os filtros do UC01.
2. A API confere se o total de resultados cabe no limite de exportação.
3. A API gera o CSV em UTF-8 e o envia aos poucos, sem carregar tudo em memória.

**Fluxos alternativos e exceções**

- **A1. Resultado acima do limite de exportação:** a API responde `422` com o total encontrado e pede para refinar os filtros.

#### Regras de negócio

- **RN05.1.** Os filtros e o resultado são os mesmos do UC01, inclusive as regras de situação cadastral e de matriz ou filial (RN01.2 e RN01.3).
- **RN05.2.** O limite de exportação é configurável.
- **RN05.3.** O limite é conferido antes de gerar o arquivo.
- **RN05.4.** O CSV é gerado em UTF-8 e enviado em partes (streaming), sem carregar o resultado inteiro em memória.

---

## Carga de dados

### UC06. Atualizar a base com a competência mais recente

A Receita publica uma pasta por mês (`2026-11`, `2026-12`...), sem dia fixo. Por isso o agendador executa `atualizar_receita.py` todo dia, e o script só trabalha quando há novidade.

#### Fluxo

**Fluxo principal**

1. O script lista as competências publicadas e escolhe a mais recente.
2. Confere se a competência está completa (as 10 tabelas) e se nenhum arquivo foi alterado nas últimas 3 horas, sinal de que a Receita ainda está enviando.
3. Confere o espaço em disco: cerca de 8 GB para os ZIPs e 35 GB para os CSVs.
4. Baixa os ZIPs, 4 por vez, validando tamanho e CRC antes de aceitar cada arquivo.
5. Trata os arquivos (UC07).
6. Aplica a retenção: mantém uma competência em `data/raw/` e duas em `data/output/`, removendo apenas pastas no formato `AAAA-MM`.
7. Registra tudo em `data/logs/atualizar_receita.log` e encerra com código `0`.

**Fluxos alternativos e exceções**

- **A1. Competência incompleta ou em envio:** o script termina sem baixar e tenta de novo no dia seguinte.
- **A2. Competência já tratada e nenhum arquivo alterado (mesmos ETags):** o script termina sem fazer nada.
- **A3. Receita republicou um arquivo:** só ele é baixado de novo e a saída é refeita.
- **A4. Execução interrompida:** o script retoma os downloads parciais e pula os CSVs já prontos.
- **A5. Falha de rede:** a operação é repetida. Se a falha persistir, o script encerra com código `1`.
- **A6. Falta de espaço em disco:** nada é baixado e o script encerra com código `1`.
- **A7. Execução de teste (`--tables` ou `--limit`):** a competência não é marcada como concluída e a retenção não é aplicada.

#### Regras de negócio

- **RN06.1.** O script roda todo dia e só trabalha quando há novidade, porque a Receita não tem dia fixo de publicação.
- **RN06.2.** A competência a processar é sempre a mais recente publicada, identificada pela pasta `AAAA-MM`.
- **RN06.3.** Uma competência só é aceita quando está completa (as 10 tabelas) e estável, ou seja, sem arquivo alterado nas últimas 3 horas.
- **RN06.4.** Antes de baixar, é preciso haver espaço em disco para cerca de 8 GB de ZIPs e 35 GB de CSVs.
- **RN06.5.** Os downloads são feitos 4 por vez, e cada arquivo só é aceito depois de validados o tamanho e o CRC.
- **RN06.6.** A detecção de mudança usa os ETags dos arquivos. Sem mudança, nada é refeito, e se um arquivo mudou, só ele é baixado de novo (a atualização é idempotente, RNF05).
- **RN06.7.** A retenção mantém uma competência em `data/raw/` e duas em `data/output/`, e só remove pastas no formato `AAAA-MM`.
- **RN06.8.** Tudo é registrado em `data/logs/atualizar_receita.log`. O código de saída é `0` em sucesso, incluindo os casos em que não há nada a fazer, e `1` em falha de rede persistente ou falta de espaço.
- **RN06.9.** Execuções de teste (`--tables` ou `--limit`) não alteram o estado de conclusão nem a retenção.

### UC07. Tratar os arquivos de uma competência

O administrador (ou o UC06) transforma os arquivos brutos da Receita em CSVs limpos, com `process_receita.py`.

#### Fluxo

**Fluxo principal**

1. O script lê cada ZIP sem extraí-lo e identifica a tabela pelo nome do arquivo.
2. Aplica as regras de limpeza (RN07.2 a RN07.6).
3. Grava cada CSV com extensão `.tmp` e só o renomeia ao terminar.
4. Gera o `relatorio_processamento.json` com as contagens por tabela e arquivo.

**Fluxos alternativos e exceções**

- **A1. Registro com número de colunas divergente:** o registro vai para `_rejeitados/` com o número da linha original, e o processamento continua.
- **A2. ZIP corrompido:** o script gera erro explícito, sem dados truncados.
- **A3. Execução interrompida:** com `--skip-existing`, a nova execução pula o que já foi gerado.

#### Regras de negócio

- **RN07.1.** O ZIP é lido sem extração, e a tabela é identificada pelo nome do arquivo.
- **RN07.2.** Cada tabela recebe o cabeçalho que lhe corresponde.
- **RN07.3.** Registros quebrados em várias linhas são juntados.
- **RN07.4.** As datas ficam no formato `AAAAMMDD`.
- **RN07.5.** O capital social usa ponto como separador decimal, e os campos vazios viram `NULL`.
- **RN07.6.** A codificação e os acentos são corrigidos. Um `?` só vira letra acentuada quando a palavra acentuada aparece ao menos 3 vezes e responde por 90% ou mais das grafias possíveis. Casos ambíguos, como `AM?LIA`, ficam como estão.
- **RN07.7.** O CSV é gravado como `.tmp` e só é renomeado ao terminar, para uma execução interrompida não deixar arquivo incompleto.
- **RN07.8.** Registros rejeitados nunca interrompem o processamento e são sempre rastreáveis pela linha original.
- **RN07.9.** Um ZIP corrompido nunca gera dados truncados.

### UC08. Carregar os dados tratados no PostgreSQL

O administrador carrega no banco os CSVs de uma competência já tratada. O esquema já deve existir, criado a partir das entidades JPA.

#### Fluxo

**Fluxo principal**

1. O administrador executa a carga, que usa `COPY` por tabela.
2. A carga abre uma única transação e esvazia as tabelas de uma vez, com um só `TRUNCATE`.
3. Carrega as tabelas de códigos (CNAE, município, natureza, qualificação, país e motivo).
4. Carrega `empresas`, depois `estabelecimentos`, `socios` e `simples`, descartando os registros órfãos no caminho.
5. Compara as contagens com o `relatorio_processamento.json`, descontando rejeitados e órfãos.
6. Confirma a transação e registra o resumo, com as contagens e os órfãos removidos por tabela.

**Fluxos alternativos e exceções**

- **A1. Contagem final divergente:** a transação não é confirmada, e o resumo aponta a tabela e a diferença.
- **A2. Falha no meio da carga:** a transação é desfeita, e a competência anterior continua intacta.

#### Regras de negócio

- **RN08.1.** O esquema deve existir antes da carga, criado a partir das entidades JPA.
- **RN08.2.** A carga é uma única transação. O `TRUNCATE` é um só, já que há chaves estrangeiras entre as tabelas.
- **RN08.3.** A ordem de carga é: tabelas de códigos, `empresas`, `estabelecimentos`, `socios` e `simples`.
- **RN08.4.** A competência nova substitui a anterior, e o banco guarda uma competência por vez. A API nunca enxerga dados de duas competências misturados.
- **RN08.5.** As consultas ficam aguardando enquanto a carga roda, por isso ela deve acontecer fora do horário de uso.
- **RN08.6.** Estabelecimento, sócio ou registro do Simples cujo CNPJ básico não existe em `empresas` é descartado.
- **RN08.7.** Um código de município, CNAE, natureza, qualificação, país ou motivo que não existe na tabela de códigos vira `NULL`, e o registro é mantido, para não perder uma empresa real por um código ausente.
- **RN08.8.** Os registros descartados e os códigos anulados entram na contagem do resumo.
- **RN08.9.** A conferência das contagens com o `relatorio_processamento.json` desconta os rejeitados (UC07) e os órfãos. A transação só é confirmada se tudo bater.

### UC09. Verificar a situação da base

O administrador consulta o estado da base e da última carga.

#### Fluxo

**Fluxo principal**

1. O administrador solicita a situação da base.
2. A API lê o estado registrado da carga e as contagens das tabelas.
3. A API devolve qual competência está carregada, quando foi a última carga, quantos registros há em cada tabela e como terminou a última execução.

**Fluxos alternativos e exceções**

- **A1. Base ainda sem carga:** a API informa que não há dados, em vez de falhar.

#### Regras de negócio

- **RN09.1.** A resposta não expõe caminhos internos do servidor nem dados de conexão (RNF06).
- **RN09.2.** Antes da primeira carga, a consulta não é um erro: a resposta informa que não há dados.

---

## Requisitos não funcionais

- **RNF01.** As buscas mais comuns (UF, CNAE e situação) respondem em até 2 segundos na base completa, o que exige índices nessas colunas.
- **RNF02.** Toda listagem é paginada, com tamanho máximo configurável.
- **RNF03.** A base tem dezenas de milhões de estabelecimentos, então nenhuma consulta pode depender de varrer a tabela inteira sem filtro.
- **RNF04.** A API só lê os dados. Nenhuma operação de escrita sobre eles é exposta.
- **RNF05.** A atualização mensal é idempotente: rodar de novo não duplica nem corrompe dados.
- **RNF06.** Os erros seguem um formato padronizado (código, mensagem e campo) e não expõem detalhes internos.
- **RNF07.** A API não tem autenticação nem cota. A configuração padrão escuta apenas em `localhost`.
- **RNF08.** Qualquer pessoa consegue subir uma instância a partir do clone: a conexão com o banco vem de variáveis de ambiente, nada sensível vai para o repositório.

## Fora de escopo

Enriquecimento com fontes além da Receita (site, redes sociais, faturamento), pontuação ou recomendação automática de leads, gestão de funil e histórico de contato, e envio de e-mails ou mensagens.
