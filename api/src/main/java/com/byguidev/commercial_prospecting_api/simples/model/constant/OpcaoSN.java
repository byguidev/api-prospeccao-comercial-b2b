package com.byguidev.commercial_prospecting_api.simples.model.constant;

import com.byguidev.commercial_prospecting_api.compartilhado.constant.CodigoEnum;
import lombok.Getter;

@Getter

public enum OpcaoSN implements CodigoEnum {
    SIM("S"),
    NAO("N");

    private final String codigo;

    OpcaoSN(String codigo) {
        this.codigo = codigo;
    }
}
