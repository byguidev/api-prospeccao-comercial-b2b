package com.byguidev.commercial_prospecting_api.model.enumeration;

import lombok.Getter;

@Getter

public enum TipoSocio implements CodigoEnum {
    PESSOA_JURIDICA("1"),
    PESSOA_FISICA("2"),
    ESTRANGEIRO("3");

    private final String codigo;

    TipoSocio(String codigo) {
        this.codigo = codigo;
    }
}
