package com.byguidev.commercial_prospecting_api.empresa.controller;

import com.byguidev.commercial_prospecting_api.empresa.model.Empresa;
import com.byguidev.commercial_prospecting_api.empresa.service.EmpresaService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;

@RestController
@RequestMapping("/empresas")
@RequiredArgsConstructor
public class EmpresaController {
    private final EmpresaService service;

    @GetMapping
    public List<Empresa> getAllEmpresas() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Optional<Empresa> getEmpresa(@PathVariable String id) {
        return service.findById(id);
    }
}
