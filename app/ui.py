"""
ui.py
-----
Peças visuais comuns a todas as páginas do dashboard: estilo, títulos de
gráfico, notas, layout Plotly e o selo de cobertura (TRN-02).

Hierarquia em 5 níveis, no máximo dois tamanhos por nível:
  título 30px > achado 19px > indicador 28px/13px > gráfico 17px/13px > nota 12px.
Espaçamento numa grade de 8px. Paleta e contraste: tema.py (ADR-016).
"""

from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import tema as t

MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]
CONFIG = {"displayModeBar": False}
# Mapas: o fundo-mundo do Plotly fica vazio e é servido pelo próprio Streamlit
# (app/static/, enableStaticServing), sem consulta ao CDN — da versão de 18/11.
CONFIG_MAPA = {**CONFIG, "topojsonURL": "./app/static/"}

CSS = f"""
<style>
  [data-testid="stMainBlockContainer"] {{ padding: 48px 40px 40px; max-width: 1440px; }}
  [data-testid="stSidebar"] {{ background: {t.LATERAL}; }}
  [data-testid="stHeader"] {{ background: transparent; }}
  .produto {{ font-size: 14px; font-weight: 700; color: {t.TEXTO_2}; margin: 0 0 12px; }}
  h1.titulo {{ font-size: 30px; line-height: 1.25; font-weight: 700; color: {t.TEXTO};
              margin: 0 0 8px 0; padding: 0; }}
  p.achado {{ font-size: 19px; line-height: 1.45; color: {t.TEXTO}; margin: 0 0 24px 0; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
  .kpi {{ border-top: 3px solid {t.TEXTO}; padding: 8px 0 0 0; }}
  .kpi .v {{ font-size: 28px; font-weight: 700; color: {t.TEXTO}; line-height: 1.2; }}
  .kpi .r {{ font-size: 13px; color: {t.TEXTO_2}; line-height: 1.4; }}
  h3.ch-t {{ font-size: 17px; font-weight: 700; color: {t.TEXTO}; line-height: 1.35;
             margin: 0; padding: 0; }}
  .ch-s {{ font-size: 13px; color: {t.TEXTO_2}; line-height: 1.4; margin: 2px 0 8px 0; }}
  .nota {{ font-size: 12px; color: {t.TEXTO_2}; line-height: 1.5; margin: 0 0 32px 0; }}
  .nota b {{ color: {t.TEXTO}; }}
  .secao {{ font-size: 13px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
           color: {t.TEXTO_2}; border-bottom: 1px solid {t.GRADE}; padding-bottom: 4px;
           margin: 8px 0 16px 0; }}
  .contador {{ font-size: 28px; font-weight: 700; color: {t.TEXTO}; line-height: 1.1; }}
  .contador-r {{ font-size: 13px; color: {t.TEXTO_2}; margin-bottom: 16px; }}
  .rodape {{ border-top: 1px solid {t.GRADE}; padding: 16px 0 0; margin-top: 16px;
            font-size: 13px; line-height: 1.55; color: {t.TEXTO_2}; }}
  .rodape a {{ color: {t.TEXTO}; }}
  .limites li {{ font-size: 13px; color: {t.TEXTO_2}; line-height: 1.5; margin-bottom: 4px; }}
  .limites li b {{ color: {t.TEXTO}; }}
  .selo {{ border: 1px solid {t.GRADE}; border-left: 3px solid {t.TEXTO_2}; background: {t.BRANCO};
          padding: 8px 16px; margin: 0 0 24px 0; font-size: 13px; line-height: 1.5; color: {t.TEXTO_2}; }}
  .selo b {{ color: {t.TEXTO}; }}
  .selo ul {{ margin: 4px 0 0 0; padding-left: 18px; }}
  .caixa {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 0 0 24px 0; }}
  .caixa div {{ border-top: 3px solid {t.GRADE}; padding: 8px 0 0 0; font-size: 13px;
               line-height: 1.5; color: {t.TEXTO_2}; }}
  .caixa b {{ color: {t.TEXTO}; }}
  table.tab {{ border-collapse: collapse; width: 100%; font-size: 13px; color: {t.TEXTO};
              margin: 0 0 8px 0; }}
  table.tab th {{ text-align: right; font-weight: 600; color: {t.TEXTO_2}; padding: 6px 8px;
                 border-bottom: 1px solid {t.TEXTO_2}; }}
  table.tab td {{ text-align: right; padding: 6px 8px; border-bottom: 1px solid {t.GRADE};
                 font-variant-numeric: tabular-nums; }}
  table.tab th:first-child, table.tab td:first-child {{ text-align: left; }}
  table.tab.txt th, table.tab.txt td {{ text-align: left; }}
  table.tab tr.sel td {{ font-weight: 700; background: {t.LATERAL}; }}
  .aplica {{ font-size: 12px; color: {t.TEXTO_2}; line-height: 1.5; }}
  .aplica b {{ color: {t.TEXTO}; }}
  /* Telas estreitas e celular (versão de 18/11, estendida às três páginas). */
  @media (max-width: 900px) {{
    [data-testid="stMainBlockContainer"] {{ padding-inline: 24px; }}
    .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .caixa {{ grid-template-columns: 1fr; }}
    [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) {{
      flex-direction: column;
    }}
    [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"] {{
      flex: 1 1 auto; width: 100%;
    }}
    /* Mapa de calor: sem rótulos nas células; o valor aparece ao tocar. */
    .st-key-mapa_calor .infolayer .annotation {{ display: none; }}
    table.tab {{ display: block; overflow-x: auto; }}
  }}
  @media (max-width: 520px) {{
    [data-testid="stMainBlockContainer"] {{ padding-inline: 16px; }}
    h1.titulo {{ font-size: 25px; }}
    p.achado {{ font-size: 16px; }}
    .kpi .v {{ font-size: 21px; }}
    .kpi .r {{ font-size: 12px; }}
  }}
</style>
"""


def estilo():
    st.markdown(CSS, unsafe_allow_html=True)


def mes_ano(d: pd.Timestamp) -> str:
    return f"{MESES[d.month - 1]}/{d.year}"


def titulo_pagina(titulo: str, achado: str = ""):
    """Título que afirma o achado. Texto puro: é escapado (vem de dados)."""
    st.markdown(f'<h1 class="titulo">{escape(titulo)}</h1>'
                + (f'<p class="achado">{escape(achado)}</p>' if achado else ""),
                unsafe_allow_html=True)


def secao(texto: str):
    st.markdown(f'<div class="secao">{texto}</div>', unsafe_allow_html=True)


def titulo_grafico(titulo: str, sub: str):
    """Título (h3, para leitores de tela) e subtítulo de um gráfico. Escapados."""
    st.markdown(f'<h3 class="ch-t">{escape(titulo)}</h3><p class="ch-s">{escape(sub)}</p>',
                unsafe_allow_html=True)


def nota(html: str):
    st.markdown(f'<p class="nota">{html}</p>', unsafe_allow_html=True)


def kpis(itens: list[tuple[str, str]]):
    """Linha de indicadores: [(valor, rótulo), ...]."""
    corpo = "".join(f'<div class="kpi"><div class="v">{v}</div><div class="r">{r}</div></div>'
                    for v, r in itens)
    st.markdown(f'<div class="kpis">{corpo}</div>', unsafe_allow_html=True)


def selo(recorte: str, lacunas: list[str]):
    """Selo de cobertura (TRN-02): o recorte de dados da página e as lacunas
    conhecidas. Aparece no topo de TODA página."""
    itens = "".join(f"<li>{x}</li>" for x in lacunas)
    st.markdown(f'<div class="selo" data-testid="selo-cobertura"><b>Cobertura deste recorte:</b> '
                f'{recorte}<ul>{itens}</ul></div>', unsafe_allow_html=True)


def filtros_aplicados(linhas: list[tuple[str, str]]):
    """Diz, na tela, o que cada filtro da barra lateral faz nesta página —
    em vez de ignorar um filtro em silêncio."""
    corpo = " · ".join(f"<b>{f}:</b> {txt}" for f, txt in linhas)
    st.markdown(f'<p class="aplica">Filtros da barra lateral nesta página — {corpo}</p>',
                unsafe_allow_html=True)


def layout(fig: go.Figure, altura: int, **kw) -> go.Figure:
    """Layout comum: fundo da página, grade recessiva, separador pt-BR."""
    fig.update_layout(
        height=altura, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=t.FUNDO, plot_bgcolor=t.FUNDO, separators=",.",
        font=dict(family=t.FONTE, size=13, color=t.TEXTO_2),
        hoverlabel=dict(bgcolor=t.BRANCO, font_color=t.TEXTO, font_size=13,
                        bordercolor=t.GRADE),
        **{"showlegend": False, **kw})
    fig.update_xaxes(gridcolor=t.GRADE, linecolor=t.GRADE, zeroline=False,
                     tickfont=dict(color=t.TEXTO_2))
    fig.update_yaxes(gridcolor=t.GRADE, linecolor=t.GRADE, zeroline=False,
                     tickfont=dict(color=t.TEXTO_2))
    return fig


def faixa(fig: go.Figure, x0, x1, texto: str, y_ancora: str = "top"):
    """Faixa cinza de ressalva (ex.: queda de registro 2020-2021)."""
    fig.add_vrect(x0=x0, x1=x1, fillcolor=t.GRADE, opacity=0.6, line_width=0, layer="below")
    fig.add_annotation(x=x0, xanchor="left", y=1, yref="paper", yanchor=y_ancora,
                       text=texto, showarrow=False, align="left",
                       font=dict(size=12, color=t.TEXTO))
