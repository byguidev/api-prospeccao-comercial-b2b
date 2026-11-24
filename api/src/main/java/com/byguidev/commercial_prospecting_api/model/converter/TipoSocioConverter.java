package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.TipoSocio;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class TipoSocioConverter extends CodigoEnumConverter<TipoSocio> {
    public TipoSocioConverter() {
        super(TipoSocio.class);
    }
}
