package com.byguidev.commercial_prospecting_api.empresa.repository;

import com.byguidev.commercial_prospecting_api.empresa.model.Empresa;
import org.springframework.data.jpa.repository.JpaRepository;

public interface EmpresaRepository extends JpaRepository<Empresa, String> {
}