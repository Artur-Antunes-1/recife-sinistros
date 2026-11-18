"""
dashboard.py
------------
Dashboard interativo (Entregável 4) sobre os chamados de sinistro de trânsito
da CTTU, Recife, 2015-2024. Lê o silver consolidado direto do CSV.

Rodar a partir da raiz do repositório:
    streamlit run app/dashboard.py

Narrativa, de cima para baixo: onde estão os pontos críticos (ranking e mapa
por bairro) e o que os caracteriza (tempo, hora x dia, severidade). Decisões
visuais e o critério de casamento de bairro: docs/decisions.md, ADR-016.
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados_painel as dp  # noqa: E402
import tema as t  # noqa: E402

URL_RELATORIO = ("https://github.com/mbvo1/recife-sinistros/blob/master/"
                 "docs/relatorio_qualidade_silver.md")
URL_CTTU = "https://dados.recife.pe.gov.br/dataset/acidentes-de-transito-com-e-sem-vitimas"
URL_BAIRROS = "https://dados.recife.pe.gov.br/dataset/area-urbana"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]

st.set_page_config(page_title="Sinistros de trânsito — Recife",
                   layout="wide", initial_sidebar_state="auto")


# --- Estilo -----------------------------------------------------------------
# Hierarquia em 5 níveis, no máximo dois tamanhos por nível:
#   título 30px > achado 19px > indicador 28px/13px > gráfico 17px/13px > nota 12px.
# Espaçamento numa grade de 8px.

st.markdown(f"""
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
  .rodape {{ border-top: 1px solid {t.GRADE}; padding: 16px 0 0;
            font-size: 13px; line-height: 1.55; color: {t.TEXTO_2}; }}
  .rodape a {{ color: {t.TEXTO}; }}
  .limites li {{ font-size: 13px; color: {t.TEXTO_2}; line-height: 1.5; margin-bottom: 4px; }}
  .limites li b {{ color: {t.TEXTO}; }}
  @media (max-width: 900px) {{
    [data-testid="stMainBlockContainer"] {{ padding-inline: 24px; }}
    .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) {{
      flex-direction: column;
    }}
    [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"] {{
      flex: 1 1 auto; width: 100%;
    }}
    .st-key-mapa_calor .infolayer .annotation {{ display: none; }}
  }}
  @media (max-width: 520px) {{
    [data-testid="stMainBlockContainer"] {{ padding-inline: 16px; }}
    h1.titulo {{ font-size: 25px; }}
    p.achado {{ font-size: 16px; }}
    .kpi .v {{ font-size: 21px; }}
    .kpi .r {{ font-size: 12px; }}
  }}
</style>
""", unsafe_allow_html=True)


# --- Dados --------------------------------------------------------------------

@st.cache_resource
def _malha(caminho: Path, modificacao: int | None):
    return dp.carrega_malha(caminho)


@st.cache_data
def _dados(caminho: Path, modificacao: int, arquivo_malha: Path, modificacao_malha: int | None):
    malha = _malha(arquivo_malha, modificacao_malha)
    chaves = {f["properties"]["chave"] for f in malha["features"]} if malha else None
    return dp.casa_bairros(dp.carrega_silver(caminho), chaves)


caminho_silver = dp.caminho_silver()
caminho_malha = dp.caminho_malha()
try:
    versao_malha = caminho_malha.stat().st_mtime_ns if caminho_malha.is_file() else None
    df, rel_casamento = _dados(caminho_silver, caminho_silver.stat().st_mtime_ns,
                               caminho_malha, versao_malha)
    malha = _malha(caminho_malha, versao_malha)
except (OSError, ValueError, KeyError):
    st.error("Não foi possível carregar a base do painel. Confira os arquivos em data/painel/ "
             "ou o silver e a malha locais.")
    st.stop()
if df.empty:
    st.error("A base do painel está vazia.")
    st.stop()

ANO_MIN, ANO_MAX = int(df["ano"].min()), int(df["ano"].max())
_datas_ok = df.loc[~df["data_fora_do_ano"], "data"]
DATA_INI, DATA_FIM = _datas_ok.min(), _datas_ok.max()


def _mes_ano(d: pd.Timestamp) -> str:
    return f"{MESES[d.month - 1]}/{d.year}"


def _rodape():
    data = dp.data_download_raw() if caminho_silver == dp.CAMINHO_SILVER else None
    if caminho_silver == dp.CSV_PAINEL and dp.FONTES_PAINEL.is_file():
        metadados = json.loads(dp.FONTES_PAINEL.read_text(encoding="utf-8"))
        data = pd.Timestamp(metadados["data_extracao"])
    extracao = f" · Base extraída em {data:%d/%m/%Y}" if data is not None else ""
    st.markdown(
        f"""<footer class="rodape">
        <a href="{URL_CTTU}">Chamados da CTTU</a> ·
        <a href="{URL_BAIRROS}">Malha de bairros</a> · Portal de Dados Abertos do Recife (ODbL)<br>
        {_mes_ano(DATA_INI)} a {_mes_ano(DATA_FIM)} · {dp.fmt_int(len(df))}
        chamados finalizados{extracao}<br>
        <a href="{URL_RELATORIO}">Relatório de qualidade do silver</a>
        </footer>""", unsafe_allow_html=True)


# --- Filtros (barra lateral) ----------------------------------------------------

OPCOES_BAIRRO = sorted(df["bairro_painel"].unique(),
                       key=lambda b: (b == dp.BAIRRO_NAO_INFORMADO, dp.normaliza_nome(b)))

st.session_state.setdefault("f_anos", (ANO_MIN, ANO_MAX))
st.session_state.setdefault("f_bairros", [])
st.session_state.setdefault("f_sev", list(dp.SEVERIDADES))


def _limpa_filtros():
    st.session_state["f_anos"] = (ANO_MIN, ANO_MAX)
    st.session_state["f_bairros"] = []
    st.session_state["f_sev"] = list(dp.SEVERIDADES)


def _clique_ranking():
    """Clique numa barra do ranking = filtrar a página por aquele bairro."""
    pontos = st.session_state["sel_ranking"]["selection"]["points"]
    if pontos:
        st.session_state["f_bairros"] = [pontos[0]["y"]]


with st.sidebar:
    st.markdown('<div class="secao">Filtros</div>', unsafe_allow_html=True)
    st.slider("Anos", ANO_MIN, ANO_MAX, key="f_anos")
    st.multiselect("Bairros (vazio = todos)", OPCOES_BAIRRO, key="f_bairros",
                   placeholder="Todos os bairros")
    st.multiselect("Severidade", dp.SEVERIDADES, key="f_sev",
                   placeholder="Nenhuma selecionada")
    st.button("Limpar filtros", on_click=_limpa_filtros, width="stretch")

anos = tuple(st.session_state["f_anos"])
bairros = list(st.session_state["f_bairros"])
sevs = list(st.session_state["f_sev"])
rec = dp.aplica_filtros(df, anos, bairros, sevs)
N = len(rec)

with st.sidebar:
    st.markdown(f'<div class="secao" style="margin-top:24px">Recorte atual</div>'
                f'<div class="contador">{dp.fmt_int(N)}</div>'
                f'<div class="contador-r">registros de {dp.fmt_int(len(df))} '
                f'({dp.fmt_pct(N / len(df) * 100)})</div>', unsafe_allow_html=True)
    st.caption("Dica: clique numa barra do ranking para filtrar a página por aquele bairro.")


def _desc_recorte() -> str:
    """Texto curto do recorte, usado em todos os subtítulos."""
    a = f"{anos[0]}" if anos[0] == anos[1] else f"{anos[0]}–{anos[1]}"
    if not bairros:
        b = "todos os bairros"
    elif len(bairros) == 1:
        b = bairros[0]
    else:
        b = f"{len(bairros)} bairros selecionados"
    s = "todas as severidades" if set(sevs) == set(dp.SEVERIDADES) else \
        ", ".join(x.lower() for x in sevs)
    return f"{a} · {b} · {s}"


def _titulo_grafico(titulo: str, sub: str):
    st.markdown(f'<h3 class="ch-t">{escape(titulo)}</h3><p class="ch-s">{escape(sub)}</p>',
                unsafe_allow_html=True)


def _nota(html: str):
    st.markdown(f'<p class="nota">{html}</p>', unsafe_allow_html=True)


def _layout(fig: go.Figure, altura: int, **kw) -> go.Figure:
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


CONFIG = {"displayModeBar": False}


def _faixa_queda(fig: go.Figure, x0, x1, texto: str):
    fig.add_vrect(x0=x0, x1=x1, fillcolor=t.GRADE, opacity=0.6, line_width=0,
                  layer="below")
    fig.add_annotation(x=x0, xanchor="left", y=1, yref="paper", yanchor="top",
                       text=texto, showarrow=False, align="left",
                       font=dict(size=12, color=t.TEXTO))


# --- Topo: a resposta ------------------------------------------------------------

st.markdown('<p class="produto">Sinistros de trânsito no Recife · CTTU</p>',
            unsafe_allow_html=True)
if N == 0:
    st.markdown('<h1 class="titulo">Nenhum registro no recorte atual</h1>'
                '<p class="achado">A combinação de filtros não tem chamados. '
                'Amplie o intervalo de anos, inclua outra severidade ou use '
                '“Limpar filtros” na barra lateral.</p>', unsafe_allow_html=True)
    _rodape()
    st.stop()

k, pct_top = dp.concentracao_top(rec, 10)
rank = dp.ranking_bairros(rec, 15)
cob = dp.cobertura_geo(rec)
hd, sem_hora = dp.hora_dia(rec)

if k >= 10:
    titulo = f"10 bairros concentram {dp.fmt_pct(pct_top)} dos registros com bairro identificado"
elif k > 1:
    titulo = (f"{rank.iloc[0]['bairro_painel']} responde por {dp.fmt_pct(rank.iloc[0]['pct'])} "
              f"dos registros entre os {k} bairros do recorte")
elif k == 1:
    titulo = f"{rank.iloc[0]['bairro_painel']}: {dp.fmt_int(rank.iloc[0]['registros'])} registros no recorte"
else:
    titulo = f"{dp.fmt_int(N)} registros no recorte sem correspondência na malha de bairros"

partes = []
if k > 1:
    partes.append(f"{rank.iloc[0]['bairro_painel']} lidera, com "
                  f"{dp.fmt_int(rank.iloc[0]['registros'])} chamados "
                  f"({dp.fmt_pct(rank.iloc[0]['pct'])})")
if hd.values.sum() > 0:
    d_pico, h_pico = hd.stack().idxmax()
    pct_dia = hd.loc[:, 7:18].values.sum() / hd.values.sum() * 100
    partes.append(f"o pico é {dp.DIAS_SEMANA[d_pico].lower()} às {h_pico}h, e {dp.fmt_pct(pct_dia, 0)} dos chamados com hora caem entre 7h e 19h")
achado = " ".join(parte[:1].upper() + parte[1:] + "." for parte in partes)

st.markdown(f'<h1 class="titulo">{escape(titulo)}</h1><p class="achado">{escape(achado)}</p>',
            unsafe_allow_html=True)

anos_rec = sorted(rec["ano"].unique())
datas_rec = rec.loc[~rec["data_fora_do_ano"], "data"]
periodo = (f"{_mes_ano(datas_rec.min())} – {_mes_ano(datas_rec.max())}"
           if not datas_rec.empty else f"{anos[0]}–{anos[1]}")
r_periodo = "2015 é parcial: começa em junho" if 2015 in anos_rec else \
    f"{len(anos_rec)} ano(s) no recorte"
n_bairros = rec.loc[rec["bairro_chave"].notna(), "bairro_chave"].nunique()
n_sem_sev = int((rec["severidade"] == dp.BAIRRO_NAO_INFORMADO).sum())

st.markdown(f"""
<div class="kpis">
  <div class="kpi"><div class="v">{dp.fmt_int(N)}</div>
    <div class="r">registros no recorte · {dp.fmt_pct(N / len(df) * 100)} do total</div></div>
  <div class="kpi"><div class="v">{periodo}</div><div class="r">período coberto · {r_periodo}</div></div>
  <div class="kpi"><div class="v">{n_bairros}</div>
    <div class="r">bairros com registro</div></div>
  <div class="kpi"><div class="v">{dp.fmt_int(N - n_sem_sev)}</div>
    <div class="r">chamados com severidade conhecida · {dp.fmt_int(n_sem_sev)} sem classificação</div></div>
</div>""", unsafe_allow_html=True)


# --- 1 e 2. Onde: ranking e mapa ------------------------------------------------

st.markdown('<div class="secao">Onde estão os pontos críticos</div>', unsafe_allow_html=True)
col_rank, col_mapa = st.columns([5, 6], gap="large")

with col_rank:
    if rank.empty:
        _titulo_grafico("Sem bairros disponíveis para o ranking", _desc_recorte())
        _nota("O recorte contém chamados com bairro ausente ou sem correspondência na malha.")
    else:
        lider = rank.iloc[0]
        _titulo_grafico(
            f"{lider['bairro_painel']} lidera, com {dp.fmt_pct(lider['pct'])} dos registros"
            if len(rank) > 1 else
            f"{lider['bairro_painel']}: {dp.fmt_int(lider['registros'])} registros com bairro identificado",
            f"Top {len(rank)} bairros, registros (chamados) · {_desc_recorte()} · "
            f"n = {dp.fmt_int(cob['no_mapa'])} com bairro identificado")
        r = rank.iloc[::-1]
        fig = go.Figure(go.Bar(
            x=r["registros"], y=r["bairro_painel"], orientation="h",
            marker=dict(color=t.DESTAQUE, line=dict(color=t.FUNDO, width=2)),
            text=[dp.fmt_int(v) for v in r["registros"]],
            customdata=[dp.fmt_pct(p) for p in r["pct"]],
            textposition="outside", textfont=dict(color=t.TEXTO, size=12), cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:,} registros (%{customdata})"
                          "<extra>clique para filtrar</extra>"))
        _layout(fig, 40 + 30 * len(rank), dragmode=False, bargap=0.25)
        fig.update_xaxes(title=dict(text="registros (chamados)", font=dict(size=12)),
                         range=[0, r["registros"].max() * 1.32], rangemode="tozero",
                         showgrid=True)
        fig.update_yaxes(showgrid=False, tickfont=dict(color=t.TEXTO, size=13))
        st.plotly_chart(fig, width="stretch", config=CONFIG, key="sel_ranking",
                        on_select=_clique_ranking, selection_mode="points")
        _nota("% sobre os registros do recorte com bairro identificado. "
              "Contagem absoluta: bairros maiores e com vias de grande fluxo tendem a ter mais chamados.")

with col_mapa:
    if malha is None:
        _titulo_grafico("Mapa indisponível: malha de bairros não encontrada",
                        "O ranking ao lado é a visão geográfica deste painel.")
        _nota("Para ativar o mapa: <code>python src/baixa_malha_bairros.py</code>")
    else:
        cont = rec[rec["bairro_chave"].notna()].groupby("bairro_chave").size()
        total_geo = int(cont.sum())
        pct_top5 = cont.nlargest(5).sum() / total_geo * 100 if total_geo else 0
        _titulo_grafico(
            f"Os 5 bairros com mais registros somam {dp.fmt_pct(pct_top5)} dos registros do mapa"
            if len(cont) > 5 else f"{len(cont)} bairro(s) com registro no mapa",
            f"Registros por bairro · {_desc_recorte()} · n = {dp.fmt_int(total_geo)} no mapa")
        chaves = [f["properties"]["chave"] for f in malha["features"]]
        nome_por_chave = (df.dropna(subset=["bairro_chave"]).drop_duplicates("bairro_chave")
                            .set_index("bairro_chave")["bairro_painel"])
        fig = go.Figure()
        # Camada de base: todos os bairros em cinza (contorno da cidade e
        # bairros sem registro no recorte).
        fig.add_trace(go.Choropleth(
            geojson=malha, featureidkey="properties.chave", locations=chaves,
            z=[0] * len(chaves), colorscale=[[0, t.GRADE], [1, t.GRADE]], showscale=False,
            marker=dict(line=dict(color=t.FUNDO, width=0.8)),
            text=[nome_por_chave.get(c, dp.nome_exibicao(c)) for c in chaves],
            hovertemplate="<b>%{text}</b><br>0 registros no recorte<extra></extra>"))
        if not cont.empty:
            zmax = float(cont.max())
            fig.add_trace(go.Choropleth(
                geojson=malha, featureidkey="properties.chave",
                locations=cont.index, z=cont.values, zmin=0, zmax=zmax,
                colorscale=t.escala_plotly(),
                marker=dict(line=dict(color=t.FUNDO, width=0.8)),
                text=[nome_por_chave.get(c, c) for c in cont.index],
                customdata=(cont.values / total_geo * 100),
                hovertemplate="<b>%{text}</b><br>%{z:,} registros"
                              "<br>%{customdata:.1f}% do mapa<extra></extra>",
                colorbar=dict(title=dict(text="registros", font=dict(size=12)),
                              thickness=12, len=0.6, outlinewidth=0,
                              tickfont=dict(color=t.TEXTO_2, size=12))))
        fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator",
                        bgcolor=t.FUNDO)
        _layout(fig, 40 + 30 * max(len(rank), 10), dragmode=False)
        # Os polígonos vêm da malha da prefeitura. O fundo global fica vazio
        # e é servido pelo próprio Streamlit para evitar uma consulta ao CDN.
        st.plotly_chart(fig, width="stretch", key="mapa",
                        config={**CONFIG, "topojsonURL": "./app/static/"})
        _nota(f"Mapa por bairro porque os CSVs não têm latitude/longitude. "
              f"Passe sobre o mapa para consultar cada bairro. O ranking mostra os 15 primeiros. "
              f"<b>Fora do mapa: {dp.fmt_int(cob['fora'])} registros "
              f"({dp.fmt_pct(cob['fora'] / N * 100)} do recorte)</b> — "
              f"{dp.fmt_int(cob['nao_informado'])} com bairro “NÃO INFORMADO” e "
              f"{dp.fmt_int(cob['sem_poligono'])} com nome que não é bairro oficial "
              f"(ex.: Setúbal). Esses registros entram nos totais, não no mapa nem no ranking.")


# --- 3. Quando: série temporal ------------------------------------------------------

st.markdown('<div class="secao">Quando: o volume ao longo do tempo</div>', unsafe_allow_html=True)
col_ano, col_mes = st.columns([2, 3], gap="large")
pa = dp.por_ano(rec)

with col_ano:
    queda = ((1 - pa[2021] / pa[2019]) * 100
             if 2019 in pa.index and 2021 in pa.index and pa[2019] > 0 else None)
    if queda is not None and queda > 0:
        tit = f"Os registros caíram de {dp.fmt_int(pa[2019])} para {dp.fmt_int(pa[2021])} de 2019 a 2021"
    elif queda is not None:
        # Em alguns recortes (ex.: só COM VÍTIMA) não há queda: não afirmar uma.
        tit = (f"Os registros passaram de {dp.fmt_int(pa[2019])} para {dp.fmt_int(pa[2021])} "
               "de 2019 a 2021")
    else:
        tit = f"{pa.idxmax()} é o ano com mais registros do recorte"
    _titulo_grafico(tit, f"Registros por ano · {_desc_recorte()} · n = {dp.fmt_int(N)}")
    cores = [t.DESTAQUE_CLARO if a == 2015 else t.DESTAQUE for a in pa.index]
    rotulos = [f"{dp.fmt_int(v)}<br>parcial" if a == 2015 else dp.fmt_int(v)
               for a, v in pa.items()]
    fig = go.Figure(go.Bar(
        x=pa.index, y=pa.values, marker=dict(color=cores, line=dict(color=t.FUNDO, width=2)),
        text=rotulos, textposition="outside", textfont=dict(color=t.TEXTO, size=12),
        cliponaxis=False, hovertemplate="%{x}: %{y:,} registros<extra></extra>"))
    _layout(fig, 340)
    if pa.index.min() <= 2021 and pa.index.max() >= 2020:
        _faixa_queda(fig, max(2019.5, pa.index.min() - 0.5), min(2021.5, pa.index.max() + 0.5),
                     "queda na<br>base inteira")
    fig.update_xaxes(tickmode="array", tickvals=list(pa.index),
                     ticktext=["2015<br>jun–dez" if a == 2015 else str(a) for a in pa.index],
                     showgrid=False, tickangle=0, tickfont=dict(size=12))
    fig.update_yaxes(title=dict(text="registros (chamados)", font=dict(size=12)),
                     rangemode="tozero", range=[0, pa.max() * 1.25])
    st.plotly_chart(fig, width="stretch", config=CONFIG, key="anual")

with col_mes:
    pm = dp.por_mes(rec)
    fora_ano = int(rec["data_fora_do_ano"].sum())
    if pm.empty:
        _titulo_grafico("Sem datas válidas no recorte", _desc_recorte())
    else:
        pico = pm.idxmax()
        _titulo_grafico(f"O mês com mais registros foi {MESES[pico.month - 1]}/{pico.year}, "
                        f"com {dp.fmt_int(pm.max())}",
                        f"Registros por mês · {_desc_recorte()} · n = {dp.fmt_int(int(pm.sum()))}")
        x = pm.index.to_timestamp()
        fig = go.Figure(go.Scatter(
            x=x, y=pm.values, mode="lines" if len(pm) > 1 else "markers",
            line=dict(color=t.DESTAQUE, width=2), marker=dict(color=t.DESTAQUE, size=9),
            hovertemplate="%{x|%m/%Y}: %{y:,} registros<extra></extra>"))
        _layout(fig, 340, hovermode="x")
        ini, fim = pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")
        if x.min() <= fim and x.max() >= ini:
            _faixa_queda(fig, max(ini, x.min()), min(fim, x.max()),
                         "2020–2021: queda de registro na<br>base inteira, causa desconhecida")
        fig.update_xaxes(showgrid=False, dtick="M12" if len(pm) > 24 else None,
                         tickformat="%Y" if len(pm) > 24 else "%m/%Y")
        fig.update_yaxes(title=dict(text="registros por mês", font=dict(size=12)),
                         rangemode="tozero")
        st.plotly_chart(fig, width="stretch", config=CONFIG, key="mensal")

_b = dp.LINHAS_BRUTO
_s = df.groupby("ano").size()
_sev = dp.severidade_por_ano(df)
_nota(f"<b>A queda de 2019 para 2021 é de registro, não necessariamente de sinistros.</b> "
      f"Na base inteira (sem filtro), no bruto: {dp.fmt_int(_b[2019])} → {dp.fmt_int(_b[2020])} → {dp.fmt_int(_b[2021])} linhas; "
      f"no silver: {dp.fmt_int(_s[2019])} → {dp.fmt_int(_s[2020])} → {dp.fmt_int(_s[2021])}. "
      f"A causa é desconhecida e não deve ser lida como trânsito mais seguro. Quase toda a queda "
      f"está nos chamados SEM VÍTIMA ({dp.fmt_int(_sev.loc[2019, 'SEM VÍTIMA'])} em 2019, "
      f"{dp.fmt_int(_sev.loc[2021, 'SEM VÍTIMA'])} em 2021); os COM VÍTIMA variam menos "
      f"({dp.fmt_int(_sev.loc[2019, 'COM VÍTIMA'])} e {dp.fmt_int(_sev.loc[2021, 'COM VÍTIMA'])}). "
      f"<b>2015 é parcial</b> (jun–dez) e não é comparável a anos cheios."
      + (f" {fora_ano} registro(s) do arquivo de 2024 com data em dez/2025 ficam fora da série mensal "
         f"(data não confiável), mas entram nos totais." if fora_ano else ""))


# --- 4. Hora x dia da semana -------------------------------------------------------

st.markdown('<div class="secao">Quando: hora do dia e dia da semana</div>', unsafe_allow_html=True)
n_hora = int(hd.values.sum())
if n_hora == 0:
    _titulo_grafico("Nenhum registro do recorte tem hora e data válidas", _desc_recorte())
else:
    d_pico, h_pico = hd.stack().idxmax()
    _titulo_grafico(
        f"O pico é {dp.DIAS_SEMANA[d_pico].lower()} às {h_pico}h, com {dp.fmt_int(hd.values.max())} registros. "
        f"{dp.fmt_pct(pct_dia, 0)} caem entre 7h e 19h",
        f"Registros por hora de início do chamado e dia da semana · {_desc_recorte()} · "
        f"n = {dp.fmt_int(n_hora)} com hora")
    zmax = float(hd.values.max())
    fig = go.Figure(go.Heatmap(
        z=hd.values, x=[f"{h}h" for h in range(24)], y=dp.DIAS_SEMANA,
        colorscale=t.escala_plotly(), zmin=0, zmax=zmax, xgap=2, ygap=2,
        colorbar=dict(title=dict(text="registros", font=dict(size=12)), thickness=12,
                      outlinewidth=0, tickfont=dict(color=t.TEXTO_2, size=12)),
        hovertemplate="%{y}, %{x}: %{z:,} registros<extra></extra>"))
    # Valor em cada célula, com cor de texto escolhida pelo contraste.
    for i in range(7):
        for h in range(24):
            v = int(hd.iat[i, h])
            fig.add_annotation(x=f"{h}h", y=dp.DIAS_SEMANA[i], text=dp.fmt_int(v),
                               showarrow=False, font=dict(
                                   size=11, color=t.texto_sobre(t.cor_na_rampa(v / zmax))))
    _layout(fig, 300)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=t.TEXTO))
    fig.update_xaxes(showgrid=False, side="top", title=None)
    with st.container(key="mapa_calor"):
        st.plotly_chart(fig, width="stretch", config=CONFIG, key="calor")
_nota(f"Hora do registro do chamado. <b>{dp.fmt_int(sem_hora)} registros do recorte "
      f"ficam fora</b> por falta de hora válida ou por data incompatível com o ano do arquivo. "
      f"O arquivo de 2022 não traz horários.")


# --- 5. Severidade ---------------------------------------------------------------

st.markdown('<div class="secao">O que os caracteriza: severidade</div>', unsafe_allow_html=True)
col_sev, col_fat = st.columns([3, 2], gap="large")
spa = dp.severidade_por_ano(rec)
spa = spa[spa.sum(axis=1) > 0]
prop = spa.div(spa.sum(axis=1), axis=0) * 100

ESTILO_SEV = {  # cor, cor do rótulo interno, hachura
    "COM VÍTIMA": (t.DESTAQUE, t.BRANCO, ""),
    "VÍTIMA FATAL": (t.ESCURO, t.BRANCO, ""),
    "SEM VÍTIMA": (t.CINZA_MARCA, t.TEXTO, ""),
    dp.BAIRRO_NAO_INFORMADO: (t.FUNDO, t.TEXTO, "/"),
}


def _faixa_fatais(fig: go.Figure, idx):
    if idx.min() <= 2020 and idx.max() >= 2016:
        fig.add_vrect(x0=max(2015.5, idx.min() - 0.5), x1=min(2020.5, idx.max() + 0.5),
                      fillcolor=t.GRADE, opacity=0.6, line_width=0, layer="below")
        fig.add_annotation(x=max(2015.5, idx.min() - 0.5), xanchor="left", y=1.0, yref="paper",
                           yanchor="bottom", showarrow=False, align="left",
                           text="2016–2020: vitimasfatais &lt;0,6% preenchida",
                           font=dict(size=12, color=t.TEXTO))


with col_sev:
    tem_com_sem = {"COM VÍTIMA", "SEM VÍTIMA"} <= set(sevs)
    if tem_com_sem and 2019 in prop.index and prop.index.max() >= 2021:
        a1 = int(prop.index.max())
        tit = (f"Chamados com vítima eram {dp.fmt_pct(prop.loc[2019, 'COM VÍTIMA'])} em 2019 "
               f"e {dp.fmt_pct(prop.loc[a1, 'COM VÍTIMA'])} em {a1} neste recorte")
    else:
        tit = "Composição dos registros por severidade, ano a ano"
    _titulo_grafico(tit, f"% dos registros de cada ano · {_desc_recorte()} · n = {dp.fmt_int(N)}")
    fig = go.Figure()
    for sev in ["COM VÍTIMA", "VÍTIMA FATAL", "SEM VÍTIMA", dp.BAIRRO_NAO_INFORMADO]:
        if spa[sev].sum() == 0:
            continue
        cor, cor_txt, hach = ESTILO_SEV[sev]
        rot = [dp.fmt_pct(v, 0) if v >= 8 and sev in ("COM VÍTIMA", "SEM VÍTIMA") else ""
               for v in prop[sev]]
        fig.add_trace(go.Bar(
            x=prop.index, y=prop[sev], name=sev.capitalize() if sev != dp.BAIRRO_NAO_INFORMADO
            else "Não informado",
            marker=dict(color=cor, line=dict(color=t.TEXTO_2 if hach else t.FUNDO, width=1 if hach else 2),
                        pattern=dict(shape=hach, fgcolor=t.TEXTO_2, size=6) if hach else None),
            text=rot, textposition="inside", insidetextanchor="middle",
            textfont=dict(color=cor_txt, size=12),
            customdata=spa[sev], hovertemplate=f"{sev} · %{{x}}: %{{y:.1f}}% "
                                               f"(%{{customdata:,}} registros)<extra></extra>"))
    _layout(fig, 360, barmode="stack", showlegend=True, bargap=0.2,
            legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=t.TEXTO, size=12),
                        traceorder="normal"))
    fig.update_layout(margin=dict(t=28))
    _faixa_fatais(fig, prop.index)
    fig.update_xaxes(tickmode="array", tickvals=list(prop.index),
                     ticktext=["2015<br>jun–dez" if a == 2015 else str(a) for a in prop.index],
                     showgrid=False, tickangle=0, tickfont=dict(size=12))
    fig.update_yaxes(title=dict(text="% dos registros do ano", font=dict(size=12)),
                     range=[0, 100], ticksuffix="%")
    st.plotly_chart(fig, width="stretch", config=CONFIG, key="severidade")

with col_fat:
    fat = spa["VÍTIMA FATAL"]
    _titulo_grafico(
        f"{dp.fmt_int(int(fat.sum()))} chamados com vítima fatal no recorte",
        f"Registros com severidade “VÍTIMA FATAL”, por ano · {_desc_recorte()} · "
        f"n = {dp.fmt_int(int(fat.sum()))}")
    if fat.sum() == 0:
        _nota("Nenhum chamado com vítima fatal neste recorte.")
    else:
        fig = go.Figure(go.Bar(
            x=fat.index, y=fat.values, marker=dict(color=t.ESCURO, line=dict(color=t.FUNDO, width=2)),
            text=[dp.fmt_int(v) for v in fat.values], textposition="outside",
            textfont=dict(color=t.TEXTO, size=12), cliponaxis=False,
            hovertemplate="%{x}: %{y} chamados com vítima fatal<extra></extra>"))
        _layout(fig, 360)
        fig.update_layout(margin=dict(t=28))
        _faixa_fatais(fig, fat.index)
        fig.update_xaxes(tickmode="array", tickvals=list(fat.index),
                         ticktext=["2015<br>jun–dez" if a == 2015 else str(a) for a in fat.index],
                         showgrid=False, tickangle=0, tickfont=dict(size=12))
        fig.update_yaxes(title=dict(text="chamados com vítima fatal", font=dict(size=12)),
                         rangemode="tozero", range=[0, fat.max() * 1.3])
        st.plotly_chart(fig, width="stretch", config=CONFIG, key="fatais")

_nota("<b>Fatais são contados pela severidade “VÍTIMA FATAL”, não pela soma de vitimasfatais.</b> "
      "A coluna vitimasfatais não existe em 2015 e, de 2016 a 2020, tem só 0,25% a 0,57% das "
      "células preenchidas: célula vazia é desconhecido, nunca zero. Ela só é utilizável de 2021 "
      "em diante. A severidade conta chamados com ao menos uma morte, não o número de mortos.")


# --- Como ler este painel -----------------------------------------------------------

st.markdown('<div class="secao">Como ler este painel</div>', unsafe_allow_html=True)
rc = rel_casamento
casamento = (f"Casamento de nomes de bairro com a malha oficial: {len(rc['nao_casaram_sem_alias'])} "
             f"de {rc['bairros_csv']} grafias não casaram só com normalização de acento e caixa "
             f"({dp.fmt_int(rc['linhas_nao_casaram_sem_alias'])} registros); após um de-para explícito "
             f"de {len(dp.ALIAS_MALHA)} grafias, restam {len(rc['nao_casaram_com_alias'])} "
             f"({', '.join(dp.nome_exibicao(x) for x in rc['nao_casaram_com_alias'])}; "
             f"{dp.fmt_int(rc['linhas_nao_casaram_com_alias'])} registros), que não são bairros oficiais."
             if malha is not None else "Malha de bairros indisponível: sem casamento a reportar.")
st.markdown(f"""<ul class="limites">
<li><b>São chamados da CTTU, não todos os sinistros do Recife.</b> Só entram chamados com situação
FINALIZADA (filtro aplicado na camada silver).</li>
<li><b>2015 é parcial</b>: os registros começam em junho.</li>
<li><b>A queda de 2019 a 2021 é de registro</b>, com causa desconhecida — não indica trânsito mais seguro.</li>
<li><b>Fatais são chamados com severidade “VÍTIMA FATAL”.</b> A coluna de pessoas vitimadas
tem preenchimento consistente a partir de 2021.</li>
<li><b>Sem coordenadas</b>: os CSVs não têm latitude/longitude, por isso o mapa é por bairro.</li>
<li><b>Bairro “NÃO INFORMADO”</b> ({dp.fmt_int(rc['nao_informado'])} registros no total) entra nos
totais e sai do ranking e do mapa. {casamento}</li>
<li><b>2022 não tem hora.</b> Esses registros ficam fora do mapa de calor.</li>
</ul>""", unsafe_allow_html=True)
_rodape()
