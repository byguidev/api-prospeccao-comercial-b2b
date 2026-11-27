package com.byguidev.commercial_prospecting_api.estabelecimento.controller;

import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoRequestDTO;
import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoResponseDTO;
import com.byguidev.commercial_prospecting_api.estabelecimento.service.EstabelecimentoService;
import lombok.RequiredArgsConstructor;
import org.hibernate.query.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/estabelecimentos")
@RequiredArgsConstructor
public class EstabelecimentoController {
    private final EstabelecimentoService service;

    // @GetMapping
    // public ResponseEntity<Page> buscar(@ModelAttribute EstabelecimentoRequestDTO filtros) {
    // }
}
