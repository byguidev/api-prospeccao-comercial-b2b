package com.byguidev.commercial_prospecting_api.socio.model;

import com.byguidev.commercial_prospecting_api.empresa.model.Empresa;
import com.byguidev.commercial_prospecting_api.socio.model.constant.FaixaEtaria;
import com.byguidev.commercial_prospecting_api.socio.model.constant.TipoSocio;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDate;

@Entity
@Table(name="socios")
@Getter
@Setter

public class Socio {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch=FetchType.LAZY)
    @JoinColumn(name="cnpj_basico")
    private Empresa empresa;

    @Column(length = 1)
    private TipoSocio identificadorSocio;
    private String nomeSocioRazaoSocial;
    private String cpfCnpjSocio;
    private String qualificacaoSocio;
    private LocalDate dataEntradaSociedade;
    private String pais;
    private String representanteLegal;
    private String nomeRepresentante;
    private String qualificacaoRepresentanteLegal;
    @Column(length = 1)
    private FaixaEtaria faixaEtaria;
}