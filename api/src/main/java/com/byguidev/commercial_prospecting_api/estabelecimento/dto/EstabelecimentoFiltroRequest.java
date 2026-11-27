package com.byguidev.commercial_prospecting_api.estabelecimento.dto;

import com.byguidev.commercial_prospecting_api.empresa.model.PorteEmpresa;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.MatrizFilial;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.SituacaoCadastral;
import com.byguidev.commercial_prospecting_api.simples.model.OpcaoSN;

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
    // String correioEletronico,
    // String telefone1
) {
}
