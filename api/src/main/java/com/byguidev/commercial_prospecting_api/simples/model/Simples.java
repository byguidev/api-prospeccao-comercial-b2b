package com.byguidev.commercial_prospecting_api.simples.model;

import com.byguidev.commercial_prospecting_api.empresa.model.Empresa;
import com.byguidev.commercial_prospecting_api.simples.model.constant.OpcaoSN;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.LocalDate;

@Entity
@Table(name="simples")
@Getter
@Setter

public class Simples {
    @Id
    @Column(name="cnpj_basico",length=8)
    private String cnpjBasico;

    @OneToOne(fetch=FetchType.LAZY)
    @MapsId
    @JoinColumn(name="cnpj_basico")
    private Empresa empresa;

    @Column(length = 1)
    private OpcaoSN opcaoSimples;

    @Column(length = 1)
    private OpcaoSN opcaoMei;

    private LocalDate dataOpcaoSimples;
    private LocalDate dataExclusaoSimples;
    private LocalDate dataOpcaoMei;
    private LocalDate dataExclusaoMei;
}
