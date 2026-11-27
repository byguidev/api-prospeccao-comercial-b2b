package com.byguidev.commercial_prospecting_api.estabelecimento.specification;

import com.byguidev.commercial_prospecting_api.empresa.model.constant.PorteEmpresa;
import com.byguidev.commercial_prospecting_api.estabelecimento.dto.EstabelecimentoFiltroRequest;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.Estabelecimento;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.constant.MatrizFilial;
import com.byguidev.commercial_prospecting_api.estabelecimento.model.constant.SituacaoCadastral;
import com.byguidev.commercial_prospecting_api.simples.model.constant.OpcaoSN;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.jpa.domain.Specification;

import java.util.List;

public class EstabelecimentoSpecification {
    public static Specification<Estabelecimento> comFiltros(EstabelecimentoFiltroRequest filtro) {
        return Specification.allOf(
                porteEmpresaIgual(filtro.porteEmpresa()),
                cnaeFiscalPrincipalIgual(filtro.cnaeFiscalPrincipal()),
                cnaeFiscalSecundariaContem(filtro.cnaeFiscalSecundaria()),
                ufIgual(filtro.uf()),
                municipioIgual(filtro.municipio()),
                situacaoCadastralIgual(filtro.situacaoCadastral()),
                matrizFilialIgual(filtro.matrizFilial()),
                opcaoMeiIgual(filtro.opcaoMei()),
                opcaoSimplesIgual(filtro.opcaoSimples()),
                naturezaJuridicaIgual(filtro.naturezaJuridica())
        );
    }

    private static Specification<Estabelecimento> porteEmpresaIgual(PorteEmpresa porte) {
        return (root, query, cb) -> {
            if (porte == null) return null;
            return cb.equal(root.get("empresa").get("porteEmpresa"), porte);
        };
    }

    private static Specification<Estabelecimento> cnaeFiscalPrincipalIgual(String cnae) {
        return (root, query, cb) -> {
            if (cnae == null || cnae.isBlank()) return null;
            return cb.equal(root.get("cnaeFiscalPrincipal"), cnae);
        };
    }

    private static Specification<Estabelecimento> cnaeFiscalSecundariaContem(List<String> cnaes) {
        return (root, query, cb) -> {
            if (cnaes == null || cnaes.isEmpty()) return null;
            Predicate[] predicados = cnaes.stream()
                    .map(cnae -> cb.like(root.get("cnaeFiscalSecundaria"), "%" + cnae + "%"))
                    .toArray(Predicate[]::new);
            return cb.or(predicados);
        };
    }

    private static Specification<Estabelecimento> ufIgual(String uf) {
        return (root, query, cb) -> {
            if (uf == null || uf.isBlank()) return null;
            return cb.equal(root.get("uf"), uf.trim().toUpperCase());
        };
    }

    private static Specification<Estabelecimento> municipioIgual(String municipio) {
        return (root, query, cb) -> {
            if (municipio == null || municipio.isBlank()) return null;
            return cb.equal(root.get("municipio"), municipio);
        };
    }

    private static Specification<Estabelecimento> situacaoCadastralIgual(SituacaoCadastral situacao) {
        return (root, query, cb) -> {
            if (situacao == null) return null;
            return cb.equal(root.get("situacaoCadastral"), situacao);
        };
    }

    private static Specification<Estabelecimento> matrizFilialIgual(MatrizFilial matrizFilial) {
        return (root, query, cb) -> {
            if (matrizFilial == null) return null;
            return cb.equal(root.get("identificadorMatrizFilial"), matrizFilial);
        };
    }

    private static Specification<Estabelecimento> opcaoMeiIgual(OpcaoSN opcao) {
        return (root, query, cb) -> {
            if (opcao == null) return null;
            return cb.equal(root.get("empresa").get("simples").get("opcaoMei"), opcao);
        };
    }

    private static Specification<Estabelecimento> opcaoSimplesIgual(OpcaoSN opcao) {
        return (root, query, cb) -> {
            if (opcao == null) return null;
            return cb.equal(root.get("empresa").get("simples").get("opcaoSimples"), opcao);
        };
    }

    private static Specification<Estabelecimento> naturezaJuridicaIgual(String natureza) {
        return (root, query, cb) -> {
            if (natureza == null || natureza.isBlank()) return null;
            return cb.equal(root.get("empresa").get("naturezaJuridica"), natureza);
        };
    }
}