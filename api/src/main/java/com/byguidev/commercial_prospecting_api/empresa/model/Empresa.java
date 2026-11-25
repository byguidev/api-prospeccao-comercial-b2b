package com.byguidev.commercial_prospecting_api.empresa.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name="empresas")
@Getter
@Setter

public class Empresa {
    @Id
    @Column(name="cnpj_basico",length=8)
    private String cnpjBasico;
    private String razaoSocial;
    private String naturezaJuridica;
    private String qualificacaoResponsavel;
    private Double capitalSocial;
    @Column(length = 2)
    private PorteEmpresa porteEmpresa;
    private String enteFederativoResponsavel;
}
