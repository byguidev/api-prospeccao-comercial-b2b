package com.byguidev.commercial_prospecting_api.estabelecimento.model;

import com.byguidev.commercial_prospecting_api.empresa.model.Empresa;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.constant.MatrizFilial;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.constant.SituacaoCadastral;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.embedded.Contato;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.embedded.Endereco;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.embedded.EstabelecimentoId;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDate;

@Entity
@Table(name="estabelecimentos")
@Getter
@Setter

public class Estabelecimento {
    @EmbeddedId
    private EstabelecimentoId id;
    @ManyToOne(fetch=FetchType.LAZY)
    @MapsId("cnpjBasico")
    @JoinColumn(name="cnpj_basico")
    private Empresa empresa;
    @Embedded
    private Endereco endereco;
    @Embedded
    private Contato contato;
    @Column(length = 1)
    private MatrizFilial identificadorMatrizFilial;
    private String nomeFantasia;
    @Column(length = 2)
    private SituacaoCadastral situacaoCadastral;
    private LocalDate dataSituacaoCadastral;
    private String motivoSituacaoCadastral;
    private String situacaoEspecial;
    private LocalDate dataSituacaoEspecial;
    private LocalDate dataInicioAtividade;
    private String cnaeFiscalPrincipal;
    @Column(columnDefinition = "text")
    private String cnaeFiscalSecundaria;
}
