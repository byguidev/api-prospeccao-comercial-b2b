package com.byguidev.commercial_prospecting_api.socio.model;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnum;
import lombok.Getter;

@Getter

public enum FaixaEtaria implements CodigoEnum {
    NAO_SE_APLICA("0"),
    DE_0_A_12_ANOS("1"),
    DE_13_A_20_ANOS("2"),
    DE_21_A_30_ANOS("3"),
    DE_31_A_40_ANOS("4"),
    DE_41_A_50_ANOS("5"),
    DE_51_A_60_ANOS("6"),
    DE_61_A_70_ANOS("7"),
    DE_71_A_80_ANOS("8"),
    MAIS_DE_80_ANOS("9");

    private final String codigo;

    FaixaEtaria(String codigo) {
        this.codigo = codigo;
    }
}
