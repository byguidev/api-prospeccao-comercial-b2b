package com.byguidev.commercial_prospecting_api.simples.model;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class OpcaoSNConverter extends CodigoEnumConverter<OpcaoSN> {
    public OpcaoSNConverter() {
        super(OpcaoSN.class);
    }
}
