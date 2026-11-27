package com.byguidev.commercial_prospecting_api.estabelecimento.dto;

import com.byguidev.commercial_prospecting_api.estabelecimento.model.Estabelecimento;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;

public record EstabelecimentoResponseDTO(
        String cnpj,
        String identificadorMatrizFilial,
        String nomeFantasia,
        String situacaoCadastral,
        LocalDate dataSituacaoCadastral,
        String motivoSituacaoCadastral,
        String situacaoEspecial,
        LocalDate dataSituacaoEspecial,
        LocalDate dataInicioAtividade,
        String cnaeFiscalPrincipal,
        List<String> cnaeFiscalSecundaria,
        EnderecoDTO endereco,
        ContatoDTO contato
) {
    public record EnderecoDTO(
            String tipoLogradouro,
            String logradouro,
            String numero,
            String complemento,
            String bairro,
            String cep,
            String uf,
            String municipio,
            String pais,
            String nomeCidadeExterior
    ) {
    }

    public record ContatoDTO(
            String ddd1,
            String telefone1,
            String ddd2,
            String telefone2,
            String dddFax,
            String fax,
            String correioEletronico
    ) {
    }

    public EstabelecimentoResponseDTO(Estabelecimento e) {
        this(
                e.getId().toString(),
                e.getIdentificadorMatrizFilial().getCodigo(),
                e.getNomeFantasia(),
                e.getSituacaoCadastral().getCodigo(),
                e.getDataSituacaoCadastral(),
                e.getMotivoSituacaoCadastral(),
                e.getSituacaoEspecial(),
                e.getDataSituacaoEspecial(),
                e.getDataInicioAtividade(),
                e.getCnaeFiscalPrincipal(),
                separarCnaes(e.getCnaeFiscalSecundaria()),
                new EnderecoDTO(
                        e.getTipoLogradouro(),
                        e.getLogradouro(),
                        e.getNumero(),
                        e.getComplemento(),
                        e.getBairro(),
                        e.getCep(),
                        e.getUf(),
                        e.getMunicipio(),
                        e.getPais(),
                        e.getNomeCidadeExterior()
                ),
                new ContatoDTO(
                        e.getDdd1(),
                        e.getTelefone1(),
                        e.getDdd2(),
                        e.getTelefone2(),
                        e.getDddFax(),
                        e.getFax(),
                        e.getCorreioEletronico()
                )
        );
    }

    private static List<String> separarCnaes(String cnaes) {
        if (cnaes == null || cnaes.isBlank()) {
            return List.of();
        }
        return Arrays.stream(cnaes.split(","))
                .map(String::trim)
                .filter(c -> !c.isEmpty())
                .toList();
    }
}
