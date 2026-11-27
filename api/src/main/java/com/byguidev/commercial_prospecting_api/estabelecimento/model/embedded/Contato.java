package com.byguidev.commercial_prospecting_api.estabelecimento.model.embedded;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@Embeddable
public class Contato {
    @Column(name = "ddd_1")
    private String ddd1;
    @Column(name = "telefone_1")
    private String telefone1;
    @Column(name = "ddd_2")
    private String ddd2;
    @Column(name = "telefone_2")
    private String telefone2;
    private String dddFax;
    private String fax;
    private String correioEletronico;
}
