package com.byguidev.commercial_prospecting_api.empresa;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class PorteEmpresaConverter extends CodigoEnumConverter<PorteEmpresa> {
    public PorteEmpresaConverter() {
        super(PorteEmpresa.class);
    }
}
