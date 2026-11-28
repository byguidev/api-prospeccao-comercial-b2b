package com.byguidev.commercial_prospecting_api.estabelecimento.model.constant;

import com.byguidev.commercial_prospecting_api.compartilhado.constant.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class MatrizFilialConverter extends CodigoEnumConverter<MatrizFilial> {
    public MatrizFilialConverter() {
        super(MatrizFilial.class);
    }
}
