package com.byguidev.commercial_prospecting_api.socio.model.constant;

import com.byguidev.commercial_prospecting_api.compartilhado.constant.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class TipoSocioConverter extends CodigoEnumConverter<TipoSocio> {
    public TipoSocioConverter() {
        super(TipoSocio.class);
    }
}
