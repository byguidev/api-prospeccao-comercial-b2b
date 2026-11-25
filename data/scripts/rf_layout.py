"""Layout (cabeçalhos e tipos de coluna) das tabelas do CNPJ - Dados Abertos da Receita Federal.

Referência: "Metadados CNPJ" publicado pela Receita Federal junto aos arquivos.
Todas as colunas são tratadas como TEXTO, exceto as listadas em ``date_columns``
(normalizadas para AAAAMMDD) e ``decimal_columns`` (vírgula decimal -> ponto).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TableLayout:
    name: str
    columns: tuple[str, ...]
    # Sufixos/trechos do nome do arquivo original, usados quando a pasta não identifica a tabela.
    file_markers: tuple[str, ...]
    date_columns: frozenset[str] = frozenset()
    decimal_columns: frozenset[str] = frozenset()
    # Chave natural (única no banco). Se informada, registros vazios que repetem a chave são descartados.
    key_columns: tuple[str, ...] = ()

    def indexes_of(self, names: frozenset[str]) -> frozenset[int]:
        return frozenset(self.columns.index(n) for n in names)

    def key_indexes(self) -> tuple[int, ...]:
        return tuple(self.columns.index(n) for n in self.key_columns)


_LOOKUP_COLUMNS = ("codigo", "descricao")

LAYOUTS: dict[str, TableLayout] = {
    layout.name: layout
    for layout in (
        TableLayout(
            name="empresas",
            columns=(
                "cnpj_basico",
                "razao_social",
                "natureza_juridica",
                "qualificacao_responsavel",
                "capital_social",
                "porte_empresa",
                "ente_federativo_responsavel",
            ),
            file_markers=("EMPRECSV",),
            decimal_columns=frozenset({"capital_social"}),
            key_columns=("cnpj_basico",),
        ),
        TableLayout(
            name="estabelecimentos",
            columns=(
                "cnpj_basico",
                "cnpj_ordem",
                "cnpj_dv",
                "identificador_matriz_filial",
                "nome_fantasia",
                "situacao_cadastral",
                "data_situacao_cadastral",
                "motivo_situacao_cadastral",
                "nome_cidade_exterior",
                "pais",
                "data_inicio_atividade",
                "cnae_fiscal_principal",
                "cnae_fiscal_secundaria",
                "tipo_logradouro",
                "logradouro",
                "numero",
                "complemento",
                "bairro",
                "cep",
                "uf",
                "municipio",
                "ddd_1",
                "telefone_1",
                "ddd_2",
                "telefone_2",
                "ddd_fax",
                "fax",
                "correio_eletronico",
                "situacao_especial",
                "data_situacao_especial",
            ),
            file_markers=("ESTABELE",),
            date_columns=frozenset(
                {"data_situacao_cadastral", "data_inicio_atividade", "data_situacao_especial"}
            ),
        ),
        TableLayout(
            name="socios",
            columns=(
                "cnpj_basico",
                "identificador_socio",
                "nome_socio_razao_social",
                "cpf_cnpj_socio",
                "qualificacao_socio",
                "data_entrada_sociedade",
                "pais",
                "representante_legal",
                "nome_representante",
                "qualificacao_representante_legal",
                "faixa_etaria",
            ),
            file_markers=("SOCIOCSV",),
            date_columns=frozenset({"data_entrada_sociedade"}),
        ),
        TableLayout(
            name="simples",
            columns=(
                "cnpj_basico",
                "opcao_simples",
                "data_opcao_simples",
                "data_exclusao_simples",
                "opcao_mei",
                "data_opcao_mei",
                "data_exclusao_mei",
            ),
            file_markers=("SIMPLES",),
            date_columns=frozenset(
                {"data_opcao_simples", "data_exclusao_simples", "data_opcao_mei", "data_exclusao_mei"}
            ),
        ),
        TableLayout(name="cnaes", columns=_LOOKUP_COLUMNS, file_markers=("CNAECSV",)),
        TableLayout(name="motivos", columns=_LOOKUP_COLUMNS, file_markers=("MOTICSV",)),
        TableLayout(name="municipios", columns=_LOOKUP_COLUMNS, file_markers=("MUNICCSV",)),
        TableLayout(name="naturezas", columns=_LOOKUP_COLUMNS, file_markers=("NATJUCSV",)),
        TableLayout(name="paises", columns=_LOOKUP_COLUMNS, file_markers=("PAISCSV",)),
        TableLayout(name="qualificacoes", columns=_LOOKUP_COLUMNS, file_markers=("QUALSCSV",)),
    )
}


def detect_layout(folder_name: str, file_name: str) -> TableLayout | None:
    """Identifica a tabela pelo nome da pasta; se não bater, pelo nome do arquivo."""
    if folder_name.lower() in LAYOUTS:
        return LAYOUTS[folder_name.lower()]
    upper_name = file_name.upper()
    for layout in LAYOUTS.values():
        if any(marker in upper_name for marker in layout.file_markers):
            return layout
    return None
