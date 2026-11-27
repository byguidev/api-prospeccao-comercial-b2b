package com.byguidev.commercial_prospecting_api.estabelecimento.service;

import com.byguidev.commercial_prospecting_api.estabelecimento.repository.EstabelecimentoRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class EstabelecimentoService {
    private final EstabelecimentoRepository repository;
}
