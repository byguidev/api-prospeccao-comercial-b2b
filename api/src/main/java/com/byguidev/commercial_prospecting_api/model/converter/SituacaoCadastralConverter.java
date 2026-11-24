package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.SituacaoCadastral;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class SituacaoCadastralConverter extends CodigoEnumConverter<SituacaoCadastral> {
    public SituacaoCadastralConverter() {
        super(SituacaoCadastral.class);
    }
}
