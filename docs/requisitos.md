# Requisitos

Este documento lista os requisitos funcionais (RF) e não funcionais (RNF) da API de Prospecção Comercial B2B. As condições e os limites que cada requisito respeita estão em [regras_de_negocio.md](regras_de_negocio.md), referenciados aqui pelos códigos `RNxx.y`.

Os dados vêm do CNPJ publicado como dados abertos pela Receita Federal (empresas, estabelecimentos, sócios, Simples/MEI e tabelas de códigos). Os scripts de `data/` baixam e tratam esses arquivos, e a API em `api/` consulta o resultado no PostgreSQL.

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

## Convenções

- **Código:** `RFxx` para requisito funcional e `RNFxx` para não funcional. O número do RF coincide com o do grupo de regras de negócio correspondente (RF01 ↔ RN01.1, RN01.2...).
- **Situação:** *Implementado* quando já há código no repositório e *Pendente* quando ainda não há.
- **Ator:** quem dispara ou consome o requisito.

## Sumário

### Requisitos funcionais

| Código | Requisito | Ator principal | Situação |
|---|---|---|---|
| RF01 | Buscar empresas por critérios | Usuário comercial, sistema integrador | Pendente |
| RF02 | Consultar empresa por CNPJ | Usuário comercial, sistema integrador | Pendente |
| RF03 | Listar sócios de uma empresa | Usuário comercial, sistema integrador | Pendente |
| RF04 | Consultar tabelas de códigos | Usuário comercial, sistema integrador | Pendente |
| RF05 | Exportar resultado de busca em CSV | Usuário comercial | Pendente |
| RF06 | Atualizar a base com a competência mais recente | Agendador de tarefas | Implementado |
| RF07 | Tratar os arquivos de uma competência | Administrador | Implementado |
| RF08 | Carregar os dados tratados no PostgreSQL | Administrador | Pendente |
| RF09 | Verificar a situação da base | Administrador | Pendente |

### Requisitos não funcionais

| Código | Requisito | Categoria |
|---|---|---|
| RNF01 | Tempo de resposta das buscas mais comuns | Desempenho |
| RNF02 | Paginação obrigatória de listagens | Desempenho |
| RNF03 | Nenhuma consulta varre a tabela inteira | Desempenho |
| RNF04 | API somente leitura | Segurança |
| RNF05 | Atualização mensal idempotente | Confiabilidade |
| RNF06 | Erros padronizados e sem detalhes internos | Segurança, usabilidade |
| RNF07 | Sem autenticação e escuta apenas em `localhost` | Segurança, implantação |
| RNF08 | Instância reproduzível a partir do clone | Portabilidade |

---

## Requisitos funcionais

### Consulta

#### RF01. Buscar empresas por critérios

- **Ator:** usuário comercial, sistema integrador.
- **Necessidade:** quem prospecta precisa montar um perfil de cliente (setor, localização, porte, situação etc.) e obter a lista de empresas que o atendem, sem precisar conhecer o CNPJ de antemão. É a funcionalidade central da API.
- **Entradas:** filtros opcionais (atividade econômica, UF, município, situação cadastral, matriz ou filial, porte, faixa de capital social, período de início da atividade, optante do Simples ou do MEI, natureza jurídica, presença de e-mail ou telefone), página e tamanho da página.
- **Processamento:**
  1. Valida os parâmetros.
  2. Busca os estabelecimentos que atendem a todos os filtros informados.
  3. Ordena por CNPJ e pagina.
- **Saída:** página de resultados com o total de resultados. Cada item traz o CNPJ completo, a razão social, o nome fantasia, o CNAE principal, o município e a UF, o porte, a situação cadastral e os contatos.
- **Tratamento de erros e exceções:**
  - Parâmetro inválido (UF inexistente, CNAE malformado, intervalo de datas invertido, página negativa): a API responde `400` com o campo problemático.
  - Tamanho de página acima do máximo configurado: a API limita ao máximo e informa na resposta o tamanho aplicado.
  - Nenhum estabelecimento atende aos filtros: a resposta é uma lista vazia, sem erro.
- **Regras de negócio:** RN01.1 a RN01.8.
- **Requisitos relacionados:** RF05 (mesmos filtros), RF04 (origem dos valores dos filtros), RNF01, RNF02, RNF03.

#### RF02. Consultar empresa por CNPJ

- **Ator:** usuário comercial, sistema integrador.
- **Necessidade:** depois de encontrar uma empresa, ou ao receber um CNPJ de outra fonte, o ator precisa ver todos os dados cadastrais disponíveis dela e do estabelecimento em questão.
- **Entradas:** CNPJ de 14 dígitos, com ou sem máscara.
- **Processamento:**
  1. Normaliza o número e confere os dígitos verificadores.
  2. Localiza o estabelecimento e a empresa.
- **Saída:**
  - Empresa: razão social, natureza jurídica, capital social, porte.
  - Estabelecimento: nome fantasia, situação cadastral com data e motivo, data de início, CNAEs, endereço, contatos.
  - Simples/MEI.
- **Tratamento de erros e exceções:**
  - CNPJ com tamanho ou dígito verificador inválido: `400`.
  - CNPJ válido que não está na base: `404`.
  - Empresa sem registro no Simples/MEI: o bloco do Simples/MEI vem vazio, sem erro.
- **Regras de negócio:** RN02.1 a RN02.4.
- **Requisitos relacionados:** RF03, RNF06.

#### RF03. Listar sócios de uma empresa

- **Ator:** usuário comercial, sistema integrador.
- **Necessidade:** descobrir quem são os sócios de uma empresa para chegar ao decisor.
- **Entradas:** CNPJ, com ou sem máscara.
- **Processamento:**
  1. Normaliza o número e confere os dígitos verificadores, como no RF02.
  2. Localiza a empresa.
- **Saída:** quadro societário com tipo do sócio, nome ou razão social, qualificação, data de entrada, faixa etária e representante legal, quando houver.
- **Tratamento de erros e exceções:**
  - CNPJ inválido: `400`.
  - CNPJ inexistente na base: `404`.
  - Empresa sem sócios na base: lista vazia.
- **Regras de negócio:** RN03.1 a RN03.4.
- **Requisitos relacionados:** RF02, RNF06.

#### RF04. Consultar tabelas de códigos

- **Ator:** usuário comercial, sistema integrador.
- **Necessidade:** os filtros do RF01 usam códigos (CNAE, município, natureza jurídica etc.). Um front-end precisa dos pares código e descrição para montar os campos de seleção, e o usuário precisa poder pesquisar pela descrição.
- **Entradas:** tabela escolhida (CNAE, município, natureza jurídica, qualificação de sócio, país ou motivo da situação cadastral), página, tamanho da página e, opcionalmente, um texto de busca.
- **Processamento:** consulta a tabela escolhida, aplicando a busca textual quando informada.
- **Saída:** página com os pares código e descrição.
- **Regras de negócio:** RN04.1 a RN04.3.
- **Requisitos relacionados:** RF01, RNF02.

#### RF05. Exportar resultado de busca em CSV

- **Ator:** usuário comercial.
- **Necessidade:** levar a lista de prospecção para outra ferramenta (planilha, CRM, automação) sem refazer a busca por páginas.
- **Entradas:** os mesmos filtros do RF01.
- **Processamento:**
  1. Confere se o total de resultados cabe no limite de exportação.
  2. Gera o CSV em UTF-8 e o envia aos poucos, sem carregar tudo em memória.
- **Saída:** arquivo CSV com a mesma lista que o RF01 devolveria.
- **Tratamento de erros e exceções:** resultado acima do limite de exportação: `422`, com o total encontrado e o pedido para refinar os filtros.
- **Regras de negócio:** RN05.1 a RN05.4.
- **Requisitos relacionados:** RF01.

### Carga de dados

#### RF06. Atualizar a base com a competência mais recente

- **Ator:** agendador de tarefas.
- **Situação:** implementado em `atualizar_receita.py`.
- **Necessidade:** a Receita publica uma pasta por mês (`2026-11`, `2026-12`...), sem dia fixo. A base precisa acompanhar essa publicação sem intervenção manual, então o agendador executa o script todo dia e ele só trabalha quando há novidade.
- **Entradas:** nenhuma obrigatória. Opções de teste: `--tables` e `--limit`.
- **Processamento:**
  1. Lista as competências publicadas e escolhe a mais recente.
  2. Confere se a competência está completa (as 10 tabelas) e se nenhum arquivo foi alterado nas últimas 3 horas, sinal de que a Receita ainda está enviando.
  3. Confere o espaço em disco: cerca de 8 GB para os ZIPs e 35 GB para os CSVs.
  4. Baixa os ZIPs, 4 por vez, validando tamanho e CRC antes de aceitar cada arquivo.
  5. Trata os arquivos (RF07).
  6. Aplica a retenção: mantém uma competência em `data/raw/` e duas em `data/output/`, removendo apenas pastas no formato `AAAA-MM`.
  7. Registra tudo em `data/logs/atualizar_receita.log` e encerra com código `0`.
- **Saída:** CSVs tratados em `data/output/`, log da execução e código de saída.
- **Tratamento de erros e exceções:**
  - Competência incompleta ou em envio: termina sem baixar e tenta de novo no dia seguinte.
  - Competência já tratada e nenhum arquivo alterado (mesmos ETags): termina sem fazer nada.
  - Receita republicou um arquivo: só ele é baixado de novo e a saída é refeita.
  - Execução interrompida: retoma os downloads parciais e pula os CSVs já prontos.
  - Falha de rede: a operação é repetida. Se persistir, encerra com código `1`.
  - Falta de espaço em disco: nada é baixado e encerra com código `1`.
  - Execução de teste (`--tables` ou `--limit`): a competência não é marcada como concluída e a retenção não é aplicada.
- **Regras de negócio:** RN06.1 a RN06.9.
- **Requisitos relacionados:** RF07, RNF05.

#### RF07. Tratar os arquivos de uma competência

- **Ator:** administrador (ou o RF06).
- **Situação:** implementado em `process_receita.py`.
- **Necessidade:** os arquivos brutos da Receita têm problemas de formato (registros quebrados em várias linhas, codificação e acentos corrompidos, datas e números fora do padrão) que impedem a carga direta no banco. É preciso transformá-los em CSVs limpos e padronizados.
- **Entradas:** os ZIPs de uma competência.
- **Processamento:**
  1. Lê cada ZIP sem extraí-lo e identifica a tabela pelo nome do arquivo.
  2. Aplica as regras de limpeza (RN07.2 a RN07.6).
  3. Grava cada CSV com extensão `.tmp` e só o renomeia ao terminar.
  4. Gera o `relatorio_processamento.json` com as contagens por tabela e arquivo.
- **Saída:** CSVs tratados, pasta `_rejeitados/` e `relatorio_processamento.json`.
- **Tratamento de erros e exceções:**
  - Registro com número de colunas divergente: vai para `_rejeitados/` com o número da linha original, e o processamento continua.
  - ZIP corrompido: erro explícito, sem dados truncados.
  - Execução interrompida: com `--skip-existing`, a nova execução pula o que já foi gerado.
- **Regras de negócio:** RN07.1 a RN07.9.
- **Requisitos relacionados:** RF06, RF08 (consome o relatório de contagens).

#### RF08. Carregar os dados tratados no PostgreSQL

- **Ator:** administrador.
- **Necessidade:** a API só consulta o banco, então os CSVs tratados precisam entrar no PostgreSQL de forma consistente. Uma competência nova substitui a anterior, e a API nunca pode enxergar dados misturados de duas competências.
- **Pré-condição:** o esquema já existe, criado a partir das entidades JPA.
- **Entradas:** os CSVs tratados e o `relatorio_processamento.json` de uma competência.
- **Processamento:**
  1. Executa a carga, que usa `COPY` por tabela.
  2. Abre uma única transação e esvazia as tabelas de uma vez, com um só `TRUNCATE`.
  3. Carrega as tabelas de códigos (CNAE, município, natureza, qualificação, país e motivo).
  4. Carrega `empresas`, depois `estabelecimentos`, `socios` e `simples`, descartando os registros órfãos no caminho.
  5. Compara as contagens com o `relatorio_processamento.json`, descontando rejeitados e órfãos.
  6. Confirma a transação e registra o resumo, com as contagens e os órfãos removidos por tabela.
- **Saída:** banco carregado com uma competência e resumo da carga.
- **Tratamento de erros e exceções:**
  - Contagem final divergente: a transação não é confirmada, e o resumo aponta a tabela e a diferença.
  - Falha no meio da carga: a transação é desfeita, e a competência anterior continua intacta.
- **Regras de negócio:** RN08.1 a RN08.9.
- **Requisitos relacionados:** RF07, RF09, RNF05.

#### RF09. Verificar a situação da base

- **Ator:** administrador.
- **Necessidade:** saber qual competência está no banco, quando foi carregada e se a última carga terminou bem, sem precisar abrir o banco ou ler logs.
- **Entradas:** nenhuma.
- **Processamento:** lê o estado registrado da carga e as contagens das tabelas.
- **Saída:** competência carregada, data da última carga, quantidade de registros por tabela e resultado da última execução.
- **Tratamento de erros e exceções:** base ainda sem carga: a API informa que não há dados, em vez de falhar.
- **Regras de negócio:** RN09.1 e RN09.2.
- **Requisitos relacionados:** RF08, RNF06.

---

## Requisitos não funcionais

#### RNF01. Tempo de resposta das buscas mais comuns

- **Categoria:** desempenho.
- **Necessidade:** a busca é a operação mais usada e o usuário a refaz várias vezes ao ajustar o perfil de cliente, então a espera precisa ser curta mesmo sobre a base completa.
- **Requisito:** as buscas por UF, CNAE e situação respondem em até 2 segundos na base completa.
- **Implicação:** exige índices nessas colunas.
- **Verificação:** medir o tempo das buscas por UF, CNAE e situação na base completa.
- **Afeta:** RF01.

#### RNF02. Paginação obrigatória de listagens

- **Categoria:** desempenho.
- **Necessidade:** uma listagem sem limite, sobre dezenas de milhões de registros, derrubaria a API e o cliente.
- **Requisito:** toda listagem é paginada, com tamanho máximo configurável.
- **Verificação:** pedir uma página acima do máximo e conferir que o tamanho é limitado.
- **Afeta:** RF01, RF04.

#### RNF03. Nenhuma consulta varre a tabela inteira

- **Categoria:** desempenho.
- **Necessidade:** a base tem dezenas de milhões de estabelecimentos, e uma varredura completa torna a consulta inviável.
- **Requisito:** nenhuma consulta pode depender de varrer a tabela inteira sem filtro.
- **Verificação:** conferir os planos de execução (`EXPLAIN`) das consultas.
- **Afeta:** RF01, RF05.

#### RNF04. API somente leitura

- **Categoria:** segurança.
- **Necessidade:** a base é uma cópia dos dados da Receita e só muda pela carga. Escrita via API corromperia a fidelidade com a fonte.
- **Requisito:** nenhuma operação de escrita sobre os dados é exposta.
- **Verificação:** a API não expõe métodos `POST`, `PUT`, `PATCH` ou `DELETE` sobre os dados.
- **Afeta:** RF01 a RF05 e RF09.

#### RNF05. Atualização mensal idempotente

- **Categoria:** confiabilidade.
- **Necessidade:** o agendador roda todo dia e as execuções podem ser interrompidas, então repetir uma execução não pode causar dano.
- **Requisito:** rodar a atualização de novo não duplica nem corrompe dados.
- **Verificação:** rodar a atualização duas vezes seguidas e comparar as contagens; interromper e retomar.
- **Afeta:** RF06, RF08.

#### RNF06. Erros padronizados e sem detalhes internos

- **Categoria:** segurança e usabilidade.
- **Necessidade:** quem integra precisa tratar erros de forma previsível, e a resposta não pode vazar caminhos, consultas ou dados de conexão.
- **Requisito:** os erros seguem um formato padronizado (código, mensagem e campo) e não expõem detalhes internos.
- **Verificação:** provocar erros de validação e de banco e conferir o formato e a ausência de stack trace e de caminhos.
- **Afeta:** todos os RF de consulta (RF01 a RF05) e RF09.

#### RNF07. Sem autenticação e escuta apenas em `localhost`

- **Categoria:** segurança e implantação.
- **Necessidade:** a API é de uso interno (ver Premissas). Sem autenticação, o que protege a instância é não expô-la.
- **Requisito:** a API não tem autenticação nem cota, e a configuração padrão escuta apenas em `localhost`.
- **Verificação:** subir com a configuração padrão e confirmar que ela não aceita conexões de outras máquinas.
- **Afeta:** toda a API.

#### RNF08. Instância reproduzível a partir do clone

- **Categoria:** portabilidade.
- **Necessidade:** o repositório é aberto, e qualquer pessoa deve conseguir rodar a própria instância sem segredos embutidos.
- **Requisito:** a conexão com o banco vem de variáveis de ambiente, e nada sensível vai para o repositório.
- **Verificação:** clonar, definir as variáveis e subir a API; conferir que o repositório não tem credenciais.
- **Afeta:** toda a API e os scripts de carga.

---

## Fora de escopo

Enriquecimento com fontes além da Receita (site, redes sociais, faturamento), pontuação ou recomendação automática de leads, gestão de funil e histórico de contato, e envio de e-mails ou mensagens.
