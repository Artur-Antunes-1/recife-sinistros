"""
estado.py
---------
Carregamentos (com cache), rodapé e filtros compartilhados entre as páginas.

Carregamento (ADR-018): a base de pontos críticos vem de data/painel/ (versionada,
abre numa cópia limpa e no Streamlit Community Cloud) ou, na falta dela, do
silver local; a previsão lê data/classificacao/. O cache é invalidado pela data
de modificação do arquivo, para uma base regerada aparecer sem reiniciar o app.

Os filtros moram na barra lateral desenhada por dashboard.py em TODA página,
para o estado não se perder ao trocar de página (o Streamlit descarta o
estado de um widget que deixa de ser desenhado). Cada página lê os valores
daqui e diz na tela quais filtros se aplicam a ela.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import dados_painel as dp
import dados_previsao as dprev
import ui

URL_RELATORIO = ("https://github.com/mbvo1/recife-sinistros/blob/master/"
                 "docs/relatorio_qualidade_silver.md")
URL_CTTU = "https://dados.recife.pe.gov.br/dataset/acidentes-de-transito-com-e-sem-vitimas"
URL_BAIRROS = "https://dados.recife.pe.gov.br/dataset/area-urbana"


def _versao(caminho: Path) -> int | None:
    return caminho.stat().st_mtime_ns if caminho.is_file() else None


@st.cache_resource
def _malha(caminho: Path, versao: int | None):
    return dp.carrega_malha(caminho)


@st.cache_data
def _silver(caminho: Path, versao: int, caminho_malha: Path, versao_malha: int | None):
    m = _malha(caminho_malha, versao_malha)
    chaves = {f["properties"]["chave"] for f in m["features"]} if m else None
    return dp.casa_bairros(dp.carrega_silver(caminho), chaves)


def malha():
    """GeoJSON de bairros (data/painel/ ou data/geo/) ou None."""
    c = dp.caminho_malha()
    return _malha(c, _versao(c))


def silver():
    """Base da página de pontos críticos casada com a malha (ADR-016):
    (df, relatório), ou (None, None) se nenhum arquivo puder ser lido."""
    c, cm = dp.caminho_silver(), dp.caminho_malha()
    if not c.is_file():
        return None, None
    try:
        return _silver(c, _versao(c), cm, _versao(cm))
    except (OSError, ValueError, KeyError):
        return None, None


@st.cache_data
def artefatos_previsao():
    """Artefatos pré-calculados dos classificadores (ADR-017) ou None."""
    return dprev.carrega_artefatos()


def filtros() -> tuple[tuple[int, int], list[str], list[str]]:
    """(anos, bairros, severidades) atuais da barra lateral."""
    return (tuple(st.session_state["f_anos"]), list(st.session_state["f_bairros"]),
            list(st.session_state["f_sev"]))


def rodape():
    """Fonte, período, extração, totais e relatório de qualidade. Chamado pelo
    roteador depois da página — e pelas páginas antes de um st.stop(), para
    aparecer também num recorte vazio."""
    df, _ = silver()
    if df is None:
        return
    ok = df.loc[~df["data_fora_do_ano"], "data"]
    data = None
    if dp.caminho_silver() == dp.CSV_PAINEL and dp.FONTES_PAINEL.is_file():
        data = pd.Timestamp(json.loads(dp.FONTES_PAINEL.read_text(encoding="utf-8"))["data_extracao"])
    elif dp.caminho_silver() == dp.CAMINHO_SILVER:
        data = dp.data_download_raw()
    extracao = f" · base extraída em {data:%d/%m/%Y}" if data is not None else ""
    art = artefatos_previsao()
    prev = (f" · {dp.fmt_int(art['cobertura']['registros'])} chamados de todos os status na previsão"
            if art else "")
    st.markdown(
        f"""<footer class="rodape">
        <a href="{URL_CTTU}">Chamados da CTTU</a> · <a href="{URL_BAIRROS}">Malha e cadastro de
        bairros</a> · Portal de Dados Abertos do Recife (ODbL)<br>
        {ui.mes_ano(ok.min())} a {ui.mes_ano(ok.max())} · {dp.fmt_int(len(df))} chamados
        finalizados nos pontos críticos{prev}{extracao}<br>
        <a href="{URL_RELATORIO}">Relatório de qualidade do silver</a>
        </footer>""", unsafe_allow_html=True)
