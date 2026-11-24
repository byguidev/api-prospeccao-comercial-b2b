package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.OpcaoSN;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class OpcaoSNConverter extends CodigoEnumConverter<OpcaoSN> {
    public OpcaoSNConverter() {
        super(OpcaoSN.class);
    }
}
