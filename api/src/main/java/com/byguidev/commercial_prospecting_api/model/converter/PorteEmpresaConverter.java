package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.PorteEmpresa;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class PorteEmpresaConverter extends CodigoEnumConverter<PorteEmpresa> {
    public PorteEmpresaConverter() {
        super(PorteEmpresa.class);
    }
}
