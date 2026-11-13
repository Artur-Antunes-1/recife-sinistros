"""
Testes do dashboard (app/dashboard.py e app/dados_painel.py).

Duas partes:
  - Unitários de dados_painel, com DataFrame sintético (não dependem dos CSVs).
  - Testes do app inteiro via streamlit.testing (AppTest), que rodam o script
    sem navegador. Estes PRECISAM do silver real em data/silver/ e são pulados
    se ele não existir. Conferem o total 59.006 e os cenários de filtro.

Rodar:  pytest -v
"""

import re

import pandas as pd
import pytest

import dados_painel as dp
import tema


# --- Unitários: normalização e casamento ----------------------------------

def test_normaliza_nome_remove_acento_caixa_e_pontuacao():
    assert dp.normaliza_nome("  São  José ") == "SAO JOSE"
    assert dp.normaliza_nome("Cohab - Ibura de Cima") == "COHAB IBURA DE CIMA"
    assert dp.normaliza_nome("hipódromo") == "HIPODROMO"


def test_nome_exibicao_preposicao_minuscula():
    assert dp.nome_exibicao("ALTO JOSÉ DO PINHO") == "Alto José do Pinho"


def _df_sintetico():
    linhas = [
        # bairro, bairro_original, ano, severidade
        ("BOA VIAGEM", "BOA VIAGEM", 2019, "SEM VÍTIMA"),
        ("BOA VIAGEM", "BOA VIAGEM", 2019, "COM VÍTIMA"),
        ("BAIRRO DO RECIFE", "BAIRRO DO RECIFE", 2020, "COM VÍTIMA"),
        ("SETUBAL", "SETÚBAL", 2021, "SEM VÍTIMA"),
        ("NÃO INFORMADO", "", 2021, "VÍTIMA FATAL"),
    ]
    df = pd.DataFrame(linhas, columns=["bairro", "bairro_original", "ano", "severidade"])
    df["data"] = pd.to_datetime(df["ano"].astype(str) + "-03-01")
    df["data_fora_do_ano"] = False
    df["hora_int"] = pd.array([8, 8, None, 17, 17], dtype="Int64")
    df["dia_semana"] = df["data"].dt.dayofweek
    return df


def test_casamento_alias_e_nao_informado_fora_do_geo():
    df, rel = dp.casa_bairros(_df_sintetico(), {"BOA VIAGEM", "RECIFE"})
    # Alias explícito leva 'BAIRRO DO RECIFE' à chave 'RECIFE' da malha.
    assert df.loc[2, "bairro_chave"] == "RECIFE"
    # Nome que não é bairro oficial e NÃO INFORMADO ficam sem chave.
    assert df["bairro_chave"].isna().tolist() == [False, False, False, True, True]
    assert rel["nao_casaram_sem_alias"] == ["BAIRRO DO RECIFE", "SETUBAL"]
    assert rel["nao_casaram_com_alias"] == ["SETUBAL"]
    assert rel["linhas_nao_casaram_com_alias"] == 1
    # NÃO INFORMADO continua no df (entra nos totais) e não vira nome bonito.
    assert df.loc[4, "bairro_painel"] == dp.BAIRRO_NAO_INFORMADO


def test_cobertura_e_ranking_excluem_sem_chave():
    df, _ = dp.casa_bairros(_df_sintetico(), {"BOA VIAGEM", "RECIFE"})
    cob = dp.cobertura_geo(df)
    assert cob == {"total": 5, "no_mapa": 3, "fora": 2, "nao_informado": 1, "sem_poligono": 1}
    r = dp.ranking_bairros(df)
    assert r["bairro_painel"].tolist() == ["Boa Viagem", "Bairro do Recife"]
    assert r["pct"].round(1).tolist() == [66.7, 33.3]


def test_filtros_combinados_e_severidade_vazia():
    df, _ = dp.casa_bairros(_df_sintetico(), {"BOA VIAGEM", "RECIFE"})
    rec = dp.aplica_filtros(df, (2019, 2019), ["Boa Viagem"], ["COM VÍTIMA"])
    assert len(rec) == 1
    # Nenhuma severidade selecionada = recorte vazio, sem erro.
    assert dp.aplica_filtros(df, (2015, 2024), [], []).empty


def test_hora_dia_conta_quem_nao_tem_hora():
    df, _ = dp.casa_bairros(_df_sintetico(), set())
    m, sem_hora = dp.hora_dia(df)
    assert m.shape == (7, 24)
    assert sem_hora == 1
    assert int(m.values.sum()) == 4


def test_contraste_wcag_conhecido():
    assert tema.contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert tema.contraste("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


# --- App inteiro (precisa do silver real) -------------------------------------

requer_silver = pytest.mark.skipif(not dp.CAMINHO_SILVER.exists(),
                                   reason="silver não gerado (rode src/transform_sinistros.py)")

# Linhas silver por ano, de docs/relatorio_qualidade_silver.md.
SILVER_POR_ANO = {2015: 5175, 2016: 8519, 2017: 9223, 2018: 9494, 2019: 10109,
                  2020: 3496, 2021: 2095, 2022: 2391, 2023: 3575, 2024: 4929}


def _app(ajuste=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("../app/dashboard.py", default_timeout=180)
    at.run()
    if ajuste:
        ajuste(at)
        at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _contador(at) -> int:
    html = next(m.value for m in at.markdown if 'class="contador"' in m.value)
    return int(re.search(r'class="contador">([\d.]+)<', html).group(1).replace(".", ""))


def _titulo(at) -> str:
    html = next(m.value for m in at.markdown if 'class="titulo"' in m.value)
    return re.sub(r"<[^>]+>", "", re.search(r'<h1 class="titulo">(.*?)</h1>', html).group(1))


@requer_silver
def test_silver_bate_com_relatorio_de_qualidade():
    df = dp.carrega_silver()
    assert len(df) == 59006
    assert df.groupby("ano").size().to_dict() == SILVER_POR_ANO


@requer_silver
def test_app_sem_filtro_mostra_59006():
    at = _app()
    assert _contador(at) == 59006
    assert _titulo(at).startswith("10 bairros concentram")


@requer_silver
def test_app_um_bairro():
    at = _app(lambda a: a.multiselect(key="f_bairros").set_value(["Boa Viagem"]))
    assert _contador(at) == 7220
    assert _titulo(at).startswith("Boa Viagem:")


@requer_silver
def test_app_um_ano():
    at = _app(lambda a: a.slider(key="f_anos").set_value((2022, 2022)))
    assert _contador(at) == SILVER_POR_ANO[2022]
    # 2022 não tem hora: o mapa de calor some e o painel diz por quê.
    assert any("Nenhum registro do recorte tem hora" in m.value for m in at.markdown)


@requer_silver
def test_app_tres_filtros_juntos():
    def ajuste(a):
        a.slider(key="f_anos").set_value((2019, 2021))
        a.multiselect(key="f_bairros").set_value(["Boa Viagem", "Derby"])
        a.multiselect(key="f_sev").set_value(["COM VÍTIMA"])
    at = _app(ajuste)
    df, _ = dp.casa_bairros(dp.carrega_silver(), None)
    esperado = len(df[df["ano"].between(2019, 2021)
                      & df["bairro_painel"].isin(["Boa Viagem", "Derby"])
                      & (df["severidade"] == "COM VÍTIMA")])
    assert _contador(at) == esperado > 0


@requer_silver
def test_app_recorte_vazio_nao_quebra():
    at = _app(lambda a: a.multiselect(key="f_sev").set_value([]))
    assert _contador(at) == 0
    assert _titulo(at) == "Nenhum registro no recorte atual"
    # O rodapé com a fonte continua lá.
    assert any('class="rodape"' in m.value for m in at.markdown)


def test_todo_texto_do_painel_tem_contraste_minimo_4_5():
    """Todo par texto/fundo usado no painel, incluindo o texto dentro de cada
    classe da rampa (mapa de calor e rótulos do mapa)."""
    pares = [
        (tema.TEXTO, tema.FUNDO), (tema.TEXTO_2, tema.FUNDO),       # página
        (tema.TEXTO, tema.LATERAL), (tema.TEXTO_2, tema.LATERAL),   # barra lateral
        (tema.TEXTO, tema.GRADE), (tema.TEXTO_2, tema.GRADE),       # anotações nas faixas
        (tema.BRANCO, tema.DESTAQUE), (tema.BRANCO, tema.ESCURO),   # % dentro das barras
        (tema.TEXTO, tema.CINZA_MARCA),
    ] + [(tema.texto_sobre(c), c) for c in tema.RAMPA]
    piores = sorted((tema.contraste(a, b), a, b) for a, b in pares)
    assert piores[0][0] >= 4.5, piores[0]


def test_cor_do_texto_bate_com_a_classe_pintada_na_fronteira():
    n = len(tema.RAMPA)
    for i in range(1, n):
        assert tema.cor_na_rampa(i / n) == tema.RAMPA[i]


@requer_silver
def test_app_nao_afirma_queda_quando_o_recorte_sobe():
    """Regressão: com Boa Viagem + só COM VÍTIMA/VÍTIMA FATAL, 2019 -> 2021 SOBE
    (180 -> 186). O título anual dizia 'Os registros caem -3%'. Não pode."""
    def ajuste(a):
        a.slider(key="f_anos").set_value((2019, 2024))
        a.multiselect(key="f_bairros").set_value(["Boa Viagem"])
        a.multiselect(key="f_sev").set_value(["COM VÍTIMA", "VÍTIMA FATAL"])
    at = _app(ajuste)
    titulos = [m.value for m in at.markdown if 'class="ch-t"' in m.value and "2019 a 2021" in m.value]
    assert titulos and all("Os registros caem" not in x for x in titulos), titulos

def test_fmt_pct_nunca_arredonda_para_100_nem_para_0():
    """99,95% nao pode virar "100,0%" ao lado de "29 sem severidade".

    Regressao: o KPI de severidade mostrava 100,0% com 29 registros sem
    severidade, duas afirmacoes que se contradizem na mesma linha.
    """
    # o caso real: 58.977 de 59.006
    assert dp.fmt_pct((59006 - 29) / 59006 * 100) == "99,9%"
    # so 100% exato pode exibir 100%
    assert dp.fmt_pct(100.0) == "100,0%"
    assert dp.fmt_pct(99.999) == "99,9%"
    assert dp.fmt_pct(99.96, 0) == "99%"
    assert dp.fmt_pct(100.0, 0) == "100%"
    # o espelho: valor pequeno mas nao nulo nao pode virar 0%
    assert dp.fmt_pct(0.0) == "0,0%"
    assert dp.fmt_pct(0.004) == "0,1%"
    assert dp.fmt_pct(0.4, 0) == "1%"
