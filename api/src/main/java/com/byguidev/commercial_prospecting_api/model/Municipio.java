package com.byguidev.commercial_prospecting_api.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name="municipios")
@Getter
@Setter

public class Municipio {
    @Id
    @Column(name="codigo",length=4)
    private String codigo;
    private String descricao;
}
