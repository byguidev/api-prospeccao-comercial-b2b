package com.byguidev.commercial_prospecting_api.estabelecimento.repository;

import com.byguidev.commercial_prospecting_api.estabelecimento.model.Estabelecimento;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.embedded.EstabelecimentoId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface EstabelecimentoRepository extends JpaRepository<Estabelecimento, EstabelecimentoId>, JpaSpecificationExecutor<Estabelecimento> {
}