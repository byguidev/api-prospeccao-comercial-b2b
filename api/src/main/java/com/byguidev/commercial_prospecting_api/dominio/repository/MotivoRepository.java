package com.byguidev.commercial_prospecting_api.dominio.repository;

import com.byguidev.commercial_prospecting_api.dominio.model.Motivo;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MotivoRepository extends JpaRepository<Motivo, String> {
}
