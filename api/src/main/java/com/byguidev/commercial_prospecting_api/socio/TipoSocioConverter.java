package com.byguidev.commercial_prospecting_api.socio;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class TipoSocioConverter extends CodigoEnumConverter<TipoSocio> {
    public TipoSocioConverter() {
        super(TipoSocio.class);
    }
}
