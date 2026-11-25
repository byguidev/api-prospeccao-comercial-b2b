package com.byguidev.commercial_prospecting_api.dominio.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name="paises")
@Getter
@Setter

public class Pais {
    @Id
    @Column(name="codigo",length=3)
    private String codigo;
    private String descricao;
}
