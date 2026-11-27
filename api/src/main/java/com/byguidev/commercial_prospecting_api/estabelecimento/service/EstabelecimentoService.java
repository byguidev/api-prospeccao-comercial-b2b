package com.byguidev.commercial_prospecting_api.estabelecimento.service;

import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoFiltroRequest;
import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoResponseDTO;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.Estabelecimento;
import com.byguidev.commercial_prospecting_api.estabelecimento.repository.EstabelecimentoRepository;
import com.byguidev.commercial_prospecting_api.estabelecimento.specification.EstabelecimentoSpecification;
import lombok.RequiredArgsConstructor;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
public class EstabelecimentoService {
    private final EstabelecimentoRepository repository;

    public List<EstabelecimentoResponseDTO> buscarEstabelecimentos(EstabelecimentoFiltroRequest filtros) {
        Specification<Estabelecimento> spec = EstabelecimentoSpecification.comFiltros(filtros);
        return repository.findAll(spec).stream().map(EstabelecimentoResponseDTO::new).toList();
    }
}
