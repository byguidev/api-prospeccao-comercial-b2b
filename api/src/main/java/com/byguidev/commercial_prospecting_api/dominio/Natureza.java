package com.byguidev.commercial_prospecting_api.dominio;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;

@Entity
@Table(name="naturezas")
@Getter
@Setter

public class Natureza {
    @Id
    @Column(name="codigo",length=4)
    private String codigo;
    private String descricao;
}
