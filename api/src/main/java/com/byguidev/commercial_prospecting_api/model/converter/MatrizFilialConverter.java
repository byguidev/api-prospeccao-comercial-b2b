package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.MatrizFilial;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class MatrizFilialConverter extends CodigoEnumConverter<MatrizFilial> {
    public MatrizFilialConverter() {
        super(MatrizFilial.class);
    }
}
