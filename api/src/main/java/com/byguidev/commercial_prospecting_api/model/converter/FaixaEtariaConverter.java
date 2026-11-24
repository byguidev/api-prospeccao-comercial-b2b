package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.FaixaEtaria;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class FaixaEtariaConverter extends CodigoEnumConverter<FaixaEtaria> {
    public FaixaEtariaConverter() {
        super(FaixaEtaria.class);
    }
}
