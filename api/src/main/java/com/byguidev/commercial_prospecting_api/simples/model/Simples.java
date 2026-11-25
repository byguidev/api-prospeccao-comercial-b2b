package com.byguidev.commercial_prospecting_api.simples.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
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
    @Column(length = 1)
    private OpcaoSN opcaoSimples;
    private LocalDate dataOpcaoSimples;
    private LocalDate dataExclusaoSimples;
    @Column(length = 1)
    private OpcaoSN opcaoMei;
    private LocalDate dataOpcaoMei;
    private LocalDate dataExclusaoMei;
}
