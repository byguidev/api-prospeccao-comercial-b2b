package com.byguidev.commercial_prospecting_api.socio.model.constant;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class FaixaEtariaConverter extends CodigoEnumConverter<FaixaEtaria> {
    public FaixaEtariaConverter() {
        super(FaixaEtaria.class);
    }
}
