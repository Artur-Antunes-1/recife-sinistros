"""
estado.py
---------
Carregamentos (com cache) e filtros compartilhados entre as páginas.

Os filtros moram na barra lateral desenhada por dashboard.py em TODA página,
para o estado não se perder ao trocar de página (o Streamlit descarta o
estado de um widget que deixa de ser desenhado). Cada página lê os valores
daqui e diz na tela quais filtros se aplicam a ela.
"""

from __future__ import annotations

import streamlit as st

import dados_painel as dp
import dados_previsao as dprev


@st.cache_resource
def malha():
    """GeoJSON de bairros (ou None). cache_resource: objeto grande, só leitura."""
    return dp.carrega_malha()


@st.cache_data
def silver():
    """Silver casado com a malha (ADR-016): (df, relatório) ou (None, None)."""
    if not dp.CAMINHO_SILVER.exists():
        return None, None
    m = malha()
    chaves = {f["properties"]["chave"] for f in m["features"]} if m else None
    return dp.casa_bairros(dp.carrega_silver(), chaves)


@st.cache_data
def artefatos_previsao():
    """Artefatos pré-calculados dos classificadores (ADR-017) ou None."""
    return dprev.carrega_artefatos()


def filtros() -> tuple[tuple[int, int], list[str], list[str]]:
    """(anos, bairros, severidades) atuais da barra lateral."""
    return (tuple(st.session_state["f_anos"]), list(st.session_state["f_bairros"]),
            list(st.session_state["f_sev"]))
