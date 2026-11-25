package com.byguidev.commercial_prospecting_api.empresa;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnum;
import lombok.Getter;

@Getter

public enum PorteEmpresa implements CodigoEnum {
    NAO_INFORMADO("00"),
    MICROEMPRESA("01"),
    EMPRESA_PEQUENO_PORTE("03"),
    DEMAIS("05");

    private final String codigo;

    PorteEmpresa(String codigo) { this.codigo = codigo; }
}