package com.byguidev.commercial_prospecting_api.estabelecimento.model;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnum;
import lombok.Getter;

@Getter

public enum MatrizFilial implements CodigoEnum {
    MATRIZ("1"),
    FILIAL("2");

    private final String codigo;

    MatrizFilial(String codigo) {
        this.codigo = codigo;
    }
}
