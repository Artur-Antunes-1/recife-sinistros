"""
Testes do painel consolidado (E6): página de previsão, metodologia, selo de
cobertura e coerência de filtros entre páginas.

  - Unitários de app/dados_previsao.py, sobre os artefatos versionados.
  - App inteiro via streamlit.testing (AppTest), trocando de página com
    switch_page. Precisam do silver em data/silver/ (pulados se faltar).

Rodar:  pytest -v
"""

import re

import pandas as pd
import pytest

import dados_painel as dp
import dados_previsao as dprev

ART = dprev.carrega_artefatos()
requer_art = pytest.mark.skipif(ART is None, reason="data/classificacao/ ausente")
requer_silver = pytest.mark.skipif(not dp.CAMINHO_SILVER.exists(), reason="silver não gerado")


def _pred():
    p = ART["predicoes"]
    return p[p["modelo"] == ART["meta"]["modelo_selecionado"]].copy()


# --- Unitários: dados_previsao ----------------------------------------------------

@requer_art
def test_carrega_artefatos_completos():
    for chave in ["metricas", "predicoes", "curvas", "mensal", "particoes", "ic", "qualidade",
                  "meta", "cobertura"]:
        assert chave in ART
    assert len(ART["metricas"]) == 8  # 4 modelos x {validação, teste}
    assert set(ART["curvas"]["curva"]) == {"roc", "pr"}
    assert ART["mensal"]["periodo"].nunique() == 12


@requer_art
def test_limiar_oficial_reproduz_a_matriz_oficial():
    of = dprev.oficial(ART, "logistica")
    m = dprev.matriz_no_limiar(_pred(), 0.16)
    assert (m["VN"], m["FP"], m["FN"], m["VP"]) == (of["tn"], of["fp"], of["fn"], of["tp"])
    assert m["VN"] + m["FP"] + m["FN"] + m["VP"] == m["n"] == of["n"]


@requer_art
def test_categorias_do_mapa_somam_a_matriz_oficial():
    p = _pred()
    c = dprev.categoria(p).value_counts()
    of = dprev.oficial(ART, "logistica")
    assert (c["VP"], c["FP"], c["FN"], c["VN"]) == (of["tp"], of["fp"], of["fn"], of["tn"])
    # Por mês, cada bairro aparece uma vez: 94 bairro-meses por mês.
    assert (p.groupby("periodo").size() == ART["meta"]["n_bairros"]).all()


@requer_art
def test_curva_de_limiares_tem_o_tradeoff_esperado():
    cl = dprev.curva_limiares(_pred())
    # Subir o limiar nunca aumenta alertas falsos nem diminui omissões.
    assert cl["FP"].is_monotonic_decreasing and cl["FN"].is_monotonic_increasing
    assert (cl["VP"] + cl["FP"] + cl["FN"] + cl["VN"] == cl["n"]).all()


@requer_art
def test_explorar_limiar_nao_altera_tabela_oficial():
    antes = ART["metricas"].copy()
    for lim in [0.05, 0.5, 0.95]:
        dprev.matriz_no_limiar(_pred(), lim)
        dprev.curva_limiares(_pred())
    pd.testing.assert_frame_equal(ART["metricas"], antes)
    pd.testing.assert_frame_equal(dprev.carrega_artefatos()["metricas"], antes)


def test_filtro_de_bairro_traduz_para_chave_do_cadastro():
    df = pd.DataFrame({"bairro_painel": ["Boa Viagem", "NÃO INFORMADO", "Setubal"],
                       "bairro_chave": ["BOA VIAGEM", None, None]})
    assert dprev.chaves_do_filtro(df, []) is None                     # sem filtro = todos
    assert dprev.chaves_do_filtro(df, ["Boa Viagem"]) == {"BOA VIAGEM"}
    assert dprev.chaves_do_filtro(df, ["NÃO INFORMADO", "Setubal"]) == set()  # sem previsão


@requer_art
def test_chaves_da_previsao_casam_com_a_malha():
    """O mapa da previsão reaproveita a malha do ADR-016: as 94 chaves do
    cadastro precisam existir na malha, senão algum bairro some do mapa."""
    malha = dp.carrega_malha()
    if malha is None:
        pytest.skip("malha ausente")
    chaves_malha = {f["properties"]["chave"] for f in malha["features"]}
    assert set(_pred()["bairro"]) == chaves_malha


# --- App inteiro --------------------------------------------------------------------

def _app(pagina=None, ajuste=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../app/dashboard.py", default_timeout=240)
    at.run()
    if pagina:
        at.switch_page(pagina)
        at.run()
    if ajuste:
        ajuste(at)
        at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _html(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def _tabela_oficial(at) -> str:
    return next(m.value for m in at.markdown if 'data-testid="tabela-oficial"' in m.value)


@requer_silver
@requer_art
@pytest.mark.parametrize("pagina", [None, "paginas/previsao.py", "paginas/metodologia.py"])
def test_toda_pagina_tem_selo_de_cobertura_com_as_lacunas(pagina):
    h = _html(_app(pagina))
    assert 'data-testid="selo-cobertura"' in h
    selo = re.search(r'data-testid="selo-cobertura">(.*?)</div>', h, re.S).group(1)
    for termo in ["2015", "junho", "2022", "2021", "2024", "28/12/2024"]:
        assert termo in selo, termo
    assert "Filtros da barra lateral nesta página" in h


@requer_silver
@requer_art
def test_previsao_mostra_numeros_oficiais_e_diz_quais_filtros_valem():
    at = _app("paginas/previsao.py")
    tab = _tabela_oficial(at)
    for v in ["0,845", "84,4%", "77,9%", "92,3%", "0,945", "0,940", "0,835", "0,851"]:
        assert v in tab, v
    h = _html(at)
    assert "não se aplica" in h and "todos os status" in h


@requer_silver
@requer_art
def test_slider_de_limiar_nao_altera_tabela_oficial():
    at = _app("paginas/previsao.py")
    antes = _tabela_oficial(at)
    at.slider(key="lim_explora").set_value(0.5)
    at.run()
    assert not at.exception
    assert _tabela_oficial(at) == antes
    # ...mas a exploração mudou: o título do gráfico de limiares cita 0,50.
    assert any("Com limiar 0,50" in m.value for m in at.markdown)


@requer_silver
@requer_art
def test_previsao_recorte_vazio_por_bairro_sem_cadastro():
    at = _app("paginas/previsao.py",
              lambda a: a.multiselect(key="f_bairros").set_value(["NÃO INFORMADO"]))
    assert "Nenhum bairro do filtro tem previsão" in _html(at)
    # A tabela oficial continua lá, intacta.
    assert "0,845" in _tabela_oficial(at)


@requer_silver
@requer_art
def test_filtro_de_bairro_vale_na_previsao_e_persiste_entre_paginas():
    def ajuste(a):
        a.multiselect(key="f_bairros").set_value(["Boa Viagem"])
    at = _app(None, ajuste)
    at.switch_page("paginas/previsao.py")
    at.run()
    assert not at.exception
    assert at.multiselect(key="f_bairros").value == ["Boa Viagem"]
    assert "1 bairro(s) do filtro" in _html(at)


@requer_silver
@requer_art
def test_metodologia_declara_que_nao_ha_indice_de_severidade_composto():
    at = _app("paginas/metodologia.py")
    texto = "\n".join(m.value for m in at.markdown)
    assert "não usa índice composto de severidade" in texto
    assert "4,5:1" in texto
