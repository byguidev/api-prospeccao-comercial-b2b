package com.byguidev.commercial_prospecting_api.empresa.service;

import com.byguidev.commercial_prospecting_api.empresa.model.Empresa;
import com.byguidev.commercial_prospecting_api.empresa.repository.EmpresaRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;

@Service
@RequiredArgsConstructor
public class EmpresaService {
    private final EmpresaRepository repository;

    public Optional<Empresa> findById(String id) {
        return repository.findById(id);
    }

    public List<Empresa> findAll() {
        return repository.findAll();
    }

    public long count() {
        return repository.count();
    }

    public boolean existsById(String id) {
        return repository.existsById(id);
    }
}
