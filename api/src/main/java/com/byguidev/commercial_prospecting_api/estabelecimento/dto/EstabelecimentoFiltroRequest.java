package com.byguidev.commercial_prospecting_api.estabelecimento.dto;

import com.byguidev.commercial_prospecting_api.empresa.model.constant.PorteEmpresa;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.constant.MatrizFilial;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.constant.SituacaoCadastral;
import com.byguidev.commercial_prospecting_api.simples.model.constant.OpcaoSN;

import java.util.List;

public record EstabelecimentoFiltroRequest(
    PorteEmpresa porteEmpresa,
    String cnaeFiscalPrincipal,
    List<String> cnaeFiscalSecundaria,
    String uf,
    String municipio,
    SituacaoCadastral situacaoCadastral,
    MatrizFilial matrizFilial,
    // double capitalSocial,
    // LocalDate dataInicioAtividade,
    OpcaoSN opcaoMei,
    OpcaoSN opcaoSimples,
    String naturezaJuridica
) {
    public EstabelecimentoFiltroRequest {
        if (situacaoCadastral == null) situacaoCadastral = SituacaoCadastral.ATIVA;
    }
}