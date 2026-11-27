package com.byguidev.commercial_prospecting_api.empresa.model;

import com.byguidev.commercial_prospecting_api.simples.model.Simples;
import jakarta.persistence.*;
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

    @Column(length = 2)
    private PorteEmpresa porteEmpresa;

    @OneToOne(mappedBy="empresa")
    private Simples simples;

    private String razaoSocial;
    private String naturezaJuridica;
    private String qualificacaoResponsavel;
    private Double capitalSocial;

    private String enteFederativoResponsavel;
}
