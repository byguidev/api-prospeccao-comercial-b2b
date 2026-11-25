package com.byguidev.commercial_prospecting_api.estabelecimento.repository;

import com.byguidev.commercial_prospecting_api.estabelecimento.model.Estabelecimento;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.EstabelecimentoId;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EstabelecimentoRepository extends JpaRepository<Estabelecimento, EstabelecimentoId> {
}
