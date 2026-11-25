package com.byguidev.commercial_prospecting_api.estabelecimento;

import com.byguidev.commercial_prospecting_api.empresa.Empresa;
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

    private String tipoLogradouro;
    private String logradouro;
    private String numero;
    private String complemento;
    private String bairro;
    private String cep;
    private String uf;
    private String municipio;
    private String pais;
    private String nomeCidadeExterior;

    @Column(name = "ddd_1")
    private String ddd1;
    @Column(name = "telefone_1")
    private String telefone1;
    @Column(name = "ddd_2")
    private String ddd2;
    @Column(name = "telefone_2")
    private String telefone2;
    private String dddFax;
    private String fax;
    private String correioEletronico;
}
