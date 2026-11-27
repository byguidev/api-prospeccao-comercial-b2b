package com.byguidev.commercial_prospecting_api.estabelecimento.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

public record EstabelecimentoRequestDTO(
        String cnae,
        String uf,
        String municipio,
        String situacao,
        String identificadorMatrizFilial,
        String porte,

        BigDecimal capitalMinimo,
        BigDecimal capitalMaximo,

        LocalDate dataInicio,
        LocalDate dataFim,

        Boolean optanteSimples,
        Boolean optanteMei,

        String naturezaJuridica,

        Boolean possuiEmail,
        Boolean possuiTelefone,

        Integer page,
        Integer size
) {
    public EstabelecimentoRequestDTO {
        page = page == null ? 0 : page;
        size = size == null ? 20 : size;
    }
}