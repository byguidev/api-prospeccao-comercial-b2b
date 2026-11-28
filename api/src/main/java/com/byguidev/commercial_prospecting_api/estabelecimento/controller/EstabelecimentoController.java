package com.byguidev.commercial_prospecting_api.estabelecimento.controller;

import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoFiltroRequest;
import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoResponseDTO;
import com.byguidev.commercial_prospecting_api.estabelecimento.service.EstabelecimentoService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
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

    @GetMapping
    public ResponseEntity<Page<EstabelecimentoResponseDTO>> buscarEstabelecimentos(
            @ModelAttribute EstabelecimentoFiltroRequest filtros,
            @PageableDefault(size=20,sort={"id.cnpjBasico", "id.cnpjOrdem", "id.cnpjDv"}) Pageable pageable) {
        Page<EstabelecimentoResponseDTO> estabelecimentos = service.buscarEstabelecimentos(filtros, pageable);
        return ResponseEntity.ok().body(estabelecimentos);
    }
}