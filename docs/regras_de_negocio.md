# Regras de negócio

Este documento reúne as regras de negócio da API de Prospecção Comercial B2B: as condições e os limites que cada funcionalidade respeita. O que cada funcionalidade faz, quem a usa e os requisitos não funcionais estão em [requisitos.md](requisitos.md).

As regras são numeradas como `RNxx.y`, em que `xx` é o número do requisito funcional (RFxx) a que a regra pertence. Quando uma regra depende de um requisito não funcional, ele aparece pelo código `RNFxx`.

## Sumário

| Grupo | Requisito funcional | Regras |
|---|---|---|
| Consulta | RF01. Buscar empresas por critérios | RN01.1 a RN01.8 |
| Consulta | RF02. Consultar empresa por CNPJ | RN02.1 a RN02.4 |
| Consulta | RF03. Listar sócios de uma empresa | RN03.1 a RN03.4 |
| Consulta | RF04. Consultar tabelas de códigos | RN04.1 a RN04.3 |
| Consulta | RF05. Exportar resultado de busca em CSV | RN05.1 a RN05.4 |
| Carga de dados | RF06. Atualizar a base com a competência mais recente | RN06.1 a RN06.9 |
| Carga de dados | RF07. Tratar os arquivos de uma competência | RN07.1 a RN07.9 |
| Carga de dados | RF08. Carregar os dados tratados no PostgreSQL | RN08.1 a RN08.9 |
| Carga de dados | RF09. Verificar a situação da base | RN09.1 e RN09.2 |

---

## Consulta

### RF01. Buscar empresas por critérios

- **RN01.1.** Todos os filtros são opcionais e se combinam (a busca traz só os estabelecimentos que atendem a todos os informados). Os filtros disponíveis são: atividade econômica (CNAE principal ou secundário), UF, município, situação cadastral, matriz ou filial, porte, faixa de capital social, período de início da atividade, optante do Simples ou do MEI, natureza jurídica e presença de e-mail ou telefone.
- **RN01.2.** Sem filtro de situação cadastral, a busca traz só estabelecimentos ativos. Quem quiser outras situações precisa pedi-las.
- **RN01.3.** Sem filtro de matriz ou filial, a busca traz os dois tipos.
- **RN01.4.** Cada estabelecimento é um resultado. Uma empresa com 50 filiais aparece 50 vezes, e o filtro de matriz ou filial serve para restringir quando for o caso.
- **RN01.5.** O CNPJ completo é a junção de CNPJ básico, ordem e dígito verificador.
- **RN01.6.** O CNAE secundário é um campo com vários códigos separados por vírgula, e o filtro considera todos.
- **RN01.7.** A ordenação é por CNPJ, para a paginação não repetir nem perder itens.
- **RN01.8.** Toda listagem é paginada, e o tamanho máximo de página é configurável (RNF02).

### RF02. Consultar empresa por CNPJ

- **RN02.1.** O CNPJ pode ser informado com ou sem máscara e deve ter 14 dígitos depois de normalizado.
- **RN02.2.** Os dígitos verificadores são conferidos antes de qualquer consulta ao banco.
- **RN02.3.** Os códigos de CNAE, município, natureza, motivo e país vêm acompanhados da descrição.
- **RN02.4.** A ausência de registro no Simples/MEI é comum e não é erro.

### RF03. Listar sócios de uma empresa

- **RN03.1.** Os sócios pertencem à empresa, não a um estabelecimento. Por isso matriz e filiais mostram a mesma lista.
- **RN03.2.** O tipo do sócio é pessoa jurídica, pessoa física ou estrangeiro.
- **RN03.3.** O CPF dos sócios pessoa física já vem mascarado da Receita, e a API o mantém assim, sem tentar reconstituí-lo nem aceitá-lo como filtro.
- **RN03.4.** A validação do CNPJ e os códigos de erro seguem as regras do RF02 (RN02.1 e RN02.2).

### RF04. Consultar tabelas de códigos

- **RN04.1.** As tabelas disponíveis são CNAE, município, natureza jurídica, qualificação de sócio, país e motivo da situação cadastral.
- **RN04.2.** A listagem é paginada (RNF02), e a busca textual é opcional.
- **RN04.3.** Como essas tabelas mudam pouco, a API pode mantê-las em cache até a próxima carga (RF08).

### RF05. Exportar resultado de busca em CSV

- **RN05.1.** Os filtros e o resultado são os mesmos do RF01, inclusive as regras de situação cadastral e de matriz ou filial (RN01.2 e RN01.3).
- **RN05.2.** O limite de exportação é configurável.
- **RN05.3.** O limite é conferido antes de gerar o arquivo.
- **RN05.4.** O CSV é gerado em UTF-8 e enviado em partes (streaming), sem carregar o resultado inteiro em memória.

---

## Carga de dados

### RF06. Atualizar a base com a competência mais recente

- **RN06.1.** O script roda todo dia e só trabalha quando há novidade, porque a Receita não tem dia fixo de publicação.
- **RN06.2.** A competência a processar é sempre a mais recente publicada, identificada pela pasta `AAAA-MM`.
- **RN06.3.** Uma competência só é aceita quando está completa (as 10 tabelas) e estável, ou seja, sem arquivo alterado nas últimas 3 horas.
- **RN06.4.** Antes de baixar, é preciso haver espaço em disco para cerca de 8 GB de ZIPs e 35 GB de CSVs.
- **RN06.5.** Os downloads são feitos 4 por vez, e cada arquivo só é aceito depois de validados o tamanho e o CRC.
- **RN06.6.** A detecção de mudança usa os ETags dos arquivos. Sem mudança, nada é refeito, e se um arquivo mudou, só ele é baixado de novo (a atualização é idempotente, RNF05).
- **RN06.7.** A retenção mantém uma competência em `data/raw/` e duas em `data/output/`, e só remove pastas no formato `AAAA-MM`.
- **RN06.8.** Tudo é registrado em `data/logs/atualizar_receita.log`. O código de saída é `0` em sucesso, incluindo os casos em que não há nada a fazer, e `1` em falha de rede persistente ou falta de espaço.
- **RN06.9.** Execuções de teste (`--tables` ou `--limit`) não alteram o estado de conclusão nem a retenção.

### RF07. Tratar os arquivos de uma competência

- **RN07.1.** O ZIP é lido sem extração, e a tabela é identificada pelo nome do arquivo.
- **RN07.2.** Cada tabela recebe o cabeçalho que lhe corresponde.
- **RN07.3.** Registros quebrados em várias linhas são juntados.
- **RN07.4.** As datas ficam no formato `AAAAMMDD`.
- **RN07.5.** O capital social usa ponto como separador decimal, e os campos vazios viram `NULL`.
- **RN07.6.** A codificação e os acentos são corrigidos. Um `?` só vira letra acentuada quando a palavra acentuada aparece ao menos 3 vezes e responde por 90% ou mais das grafias possíveis. Casos ambíguos, como `AM?LIA`, ficam como estão.
- **RN07.7.** O CSV é gravado como `.tmp` e só é renomeado ao terminar, para uma execução interrompida não deixar arquivo incompleto.
- **RN07.8.** Registros rejeitados nunca interrompem o processamento e são sempre rastreáveis pela linha original.
- **RN07.9.** Um ZIP corrompido nunca gera dados truncados.

### RF08. Carregar os dados tratados no PostgreSQL

- **RN08.1.** O esquema deve existir antes da carga, criado a partir das entidades JPA.
- **RN08.2.** A carga é uma única transação. O `TRUNCATE` é um só, já que há chaves estrangeiras entre as tabelas.
- **RN08.3.** A ordem de carga é: tabelas de códigos, `empresas`, `estabelecimentos`, `socios` e `simples`.
- **RN08.4.** A competência nova substitui a anterior, e o banco guarda uma competência por vez. A API nunca enxerga dados de duas competências misturados.
- **RN08.5.** As consultas ficam aguardando enquanto a carga roda, por isso ela deve acontecer fora do horário de uso.
- **RN08.6.** Estabelecimento, sócio ou registro do Simples cujo CNPJ básico não existe em `empresas` é descartado.
- **RN08.7.** Um código de município, CNAE, natureza, qualificação, país ou motivo que não existe na tabela de códigos vira `NULL`, e o registro é mantido, para não perder uma empresa real por um código ausente.
- **RN08.8.** Os registros descartados e os códigos anulados entram na contagem do resumo.
- **RN08.9.** A conferência das contagens com o `relatorio_processamento.json` desconta os rejeitados (RF07) e os órfãos. A transação só é confirmada se tudo bater.

### RF09. Verificar a situação da base

- **RN09.1.** A resposta não expõe caminhos internos do servidor nem dados de conexão (RNF06).
- **RN09.2.** Antes da primeira carga, a consulta não é um erro: a resposta informa que não há dados.
