package com.byguidev.commercial_prospecting_api.estabelecimento;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.AllArgsConstructor;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.io.Serializable;

@Embeddable
@EqualsAndHashCode
@Getter @Setter
@NoArgsConstructor
@AllArgsConstructor

public class EstabelecimentoId implements Serializable {
    @Column(name="cnpj_basico",length=8)
    private String cnpjBasico;

    @Column(name="cnpj_ordem",length=4)
    private String cnpjOrdem;

    @Column(name="cnpj_dv",length=2)
    private String cnpjDv;
}