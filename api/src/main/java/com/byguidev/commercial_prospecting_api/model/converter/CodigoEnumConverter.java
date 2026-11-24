package com.byguidev.commercial_prospecting_api.model.converter;

import com.byguidev.commercial_prospecting_api.model.enumeration.CodigoEnum;
import jakarta.persistence.AttributeConverter;

import java.util.Arrays;

public abstract class CodigoEnumConverter <E extends Enum<E> & CodigoEnum> implements AttributeConverter<E, String> {
    private final Class<E> tipo;

    protected CodigoEnumConverter(Class<E> tipo) {
        this.tipo = tipo;
    }

    @Override
    public String convertToDatabaseColumn(E constante) {
        if (constante == null) {
            return null;
        }
        return constante.getCodigo();
    }

    @Override
    public E convertToEntityAttribute(String codigo) {
        if (codigo == null || codigo.isBlank()) {
            return null;
        }

        String codigoLimpo = codigo.trim();

        return Arrays.stream(tipo.getEnumConstants())
                .filter(constante -> constante.getCodigo().equals(codigoLimpo))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Código '" + codigo + "' não existe em " + tipo.getSimpleName()));
    }
}
