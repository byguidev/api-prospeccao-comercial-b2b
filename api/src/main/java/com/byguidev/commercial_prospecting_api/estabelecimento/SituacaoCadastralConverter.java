package com.byguidev.commercial_prospecting_api.estabelecimento;

import com.byguidev.commercial_prospecting_api.compartilhado.CodigoEnumConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class SituacaoCadastralConverter extends CodigoEnumConverter<SituacaoCadastral> {
    public SituacaoCadastralConverter() {
        super(SituacaoCadastral.class);
    }
}
