package com.byguidev.commercial_prospecting_api.model.enumeration;

import lombok.Getter;

@Getter

public enum SituacaoCadastral implements CodigoEnum {
    NULA("01"),
    ATIVA("02"),
    SUSPENSA("03"),
    INAPTA("04"),
    BAIXADA("08");

    private final String codigo;

    SituacaoCadastral(String codigo) {
        this.codigo = codigo;
    }
}
