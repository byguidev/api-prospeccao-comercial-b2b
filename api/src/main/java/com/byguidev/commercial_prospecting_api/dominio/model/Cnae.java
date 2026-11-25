package com.byguidev.commercial_prospecting_api.dominio.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name="cnaes")
@Getter
@Setter

public class Cnae {
    @Id
    @Column(name="codigo",length=7)
    private String codigo;
    private String descricao;
}
