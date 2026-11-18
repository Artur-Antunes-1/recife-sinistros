"""
Página "Pontos críticos" (Entregável 4, consolidada no E6).

Recorte: silver, só chamados FINALIZADA (ADR-005), casamento de bairro com
5 aliases (ADR-016). Narrativa: onde estão os pontos críticos (ranking e
mapa por bairro) e o que os caracteriza (tempo, hora x dia, severidade).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dados_painel as dp
import estado
import tema as t
import ui

df, rel_casamento = estado.silver()
malha = estado.malha()
anos, bairros, sevs = estado.filtros()
rec = dp.aplica_filtros(df, anos, bairros, sevs)
N = len(rec)
art = estado.artefatos_previsao()


def _clique_ranking():
    """Clique numa barra do ranking = filtrar o painel por aquele bairro."""
    pontos = st.session_state["sel_ranking"]["selection"]["points"]
    if pontos:
        st.session_state["f_bairros"] = [pontos[0]["y"]]


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


# --- Selo de cobertura (TRN-02) ------------------------------------------------

# Container reservado no topo: o título é escrito nele depois, mas aparece ACIMA
# do selo — hierarquia título > achado > selo/indicadores (ADR-016).
cab = st.container()

_fim_2024 = df.loc[(df["ano"] == 2024) & ~df["data_fora_do_ano"], "data"].max()
_fora = int(df["data_fora_do_ano"].sum())
_sem_hora_2022 = int(df.loc[df["ano"] == 2022, "hora_int"].isna().sum())
# % de células de vitimasfatais preenchidas por ano (vazio no silver = desconhecido).
_fatal = (df["vitimasfatais"] != "").groupby(df["ano"]).mean() * 100
_fatal_ruim = _fatal.loc[2016:2020]
_faixa_fatal = f"{dp.fmt_pct(_fatal_ruim.min(), 2)} a {dp.fmt_pct(_fatal_ruim.max(), 2)}"
_todos = (f"; em todos os status (página de previsão) são {art['cobertura']['datas_outro_ano_2024']}"
          if art else "")
ui.selo(
    f"anos {anos[0]}–{anos[1]} · <b>só chamados FINALIZADA</b> (silver) · "
    f"<b>{dp.fmt_int(N)}</b> de {dp.fmt_int(len(df))} registros.",
    [f"2015 começa em junho (primeira data: {df.loc[df['ano'] == 2015, 'data'].min():%d/%m/%Y}) "
     f"— ano parcial.",
     f"2022 não tem horário utilizável: os {dp.fmt_int(_sem_hora_2022)} registros do ano ficam fora "
     f"do mapa de calor.",
     f"Vítimas fatais só são conhecidas a partir de 2021: a coluna não existe em 2015 e, de 2016 a "
     f"2020, tem só {_faixa_fatal} de preenchimento — vazio é desconhecido, nunca zero.",
     f"2024 termina em {_fim_2024:%d/%m/%Y} e tem {_fora} registros datados em outro ano neste "
     f"recorte{_todos}; eles entram nos totais e saem da série mensal e do mapa de calor."])
ui.filtros_aplicados([("Anos", "aplicado"), ("Bairros", "aplicado"), ("Severidade", "aplicado")])

# --- Topo: a resposta ------------------------------------------------------------

if N == 0:
    with cab:
        ui.titulo_pagina("Nenhum registro no recorte atual",
                         "A combinação de filtros não tem chamados. Amplie o intervalo de anos, "
                         "inclua outra severidade ou use “Limpar filtros” na barra lateral.")
    estado.rodape()
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
    partes.append(f"o pico é {dp.DIAS_SEMANA[d_pico].lower()} às {h_pico}h, e "
                  f"{dp.fmt_pct(pct_dia, 0)} dos chamados com hora caem entre 7h e 19h")
achado = " ".join(parte[:1].upper() + parte[1:] + "." for parte in partes)
with cab:
    ui.titulo_pagina(titulo, achado)

anos_rec = sorted(rec["ano"].unique())
datas_rec = rec.loc[~rec["data_fora_do_ano"], "data"]
periodo = (f"{ui.mes_ano(datas_rec.min())} – {ui.mes_ano(datas_rec.max())}"
           if not datas_rec.empty else f"{anos[0]}–{anos[1]}")
r_periodo = "2015 é parcial: começa em junho" if 2015 in anos_rec else \
    f"{len(anos_rec)} ano(s) no recorte"
n_bairros = rec.loc[rec["bairro_chave"].notna(), "bairro_chave"].nunique()
n_sem_sev = int((rec["severidade"] == dp.BAIRRO_NAO_INFORMADO).sum())
pct_sev = (N - n_sem_sev) / N * 100
ui.kpis([
    (dp.fmt_int(N), f"registros no recorte · {dp.fmt_pct(N / len(df) * 100)} do total"),
    (periodo, f"período coberto · {r_periodo}"),
    (str(n_bairros), f"bairros com registro · de {rel_casamento.get('bairros_malha', 94)} na malha oficial"),
    (dp.fmt_int(N - n_sem_sev), f"chamados com severidade conhecida ({dp.fmt_pct(pct_sev)}) · "
                                f"{dp.fmt_int(n_sem_sev)} sem classificação"),
])

# --- 1 e 2. Onde: ranking e mapa ------------------------------------------------

ui.secao("Onde estão os pontos críticos")
col_rank, col_mapa = st.columns([5, 6], gap="large")

with col_rank:
    if rank.empty:
        ui.titulo_grafico("Sem bairros disponíveis para o ranking", _desc_recorte())
        ui.nota("O recorte contém chamados com bairro ausente ou sem correspondência na malha.")
    else:
        lider = rank.iloc[0]
        ui.titulo_grafico(
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
        ui.layout(fig, 40 + 30 * len(rank), dragmode=False, bargap=0.25)
        fig.update_xaxes(title=dict(text="registros (chamados)", font=dict(size=12)),
                         range=[0, r["registros"].max() * 1.32], rangemode="tozero",
                         showgrid=True)
        fig.update_yaxes(showgrid=False, tickfont=dict(color=t.TEXTO, size=13))
        st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="sel_ranking",
                        on_select=_clique_ranking, selection_mode="points")
        ui.nota("Valor de cada barra = chamados; ao passar o mouse, a % sobre os registros do "
                "recorte com bairro identificado. Ranking = contagem de "
                "chamados FINALIZADA por bairro, sem ajuste por área, população ou fluxo: bairros "
                "maiores e com vias de grande fluxo tendem a ter mais chamados.")

with col_mapa:
    if malha is None:
        ui.titulo_grafico("Mapa indisponível: malha de bairros não encontrada",
                          "O ranking ao lado é a visão geográfica deste painel.")
        ui.nota("Para ativar o mapa: <code>python src/baixa_malha_bairros.py</code>")
    else:
        cont = rec[rec["bairro_chave"].notna()].groupby("bairro_chave").size()
        total_geo = int(cont.sum())
        pct_top5 = cont.nlargest(5).sum() / total_geo * 100 if total_geo else 0
        ui.titulo_grafico(
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
        ui.layout(fig, 40 + 30 * max(len(rank), 10), dragmode=False)
        st.plotly_chart(fig, width="stretch", config=ui.CONFIG_MAPA, key="mapa")
        ui.nota(f"Mapa por bairro porque os CSVs não têm latitude/longitude. "
                f"Passe sobre o mapa para consultar cada bairro; o ranking mostra os 15 primeiros. "
                f"<b>Fora do mapa: {dp.fmt_int(cob['fora'])} registros "
                f"({dp.fmt_pct(cob['fora'] / N * 100)} do recorte)</b> — "
                f"{dp.fmt_int(cob['nao_informado'])} com bairro “NÃO INFORMADO” e "
                f"{dp.fmt_int(cob['sem_poligono'])} com nome que não é bairro oficial "
                f"(ex.: Setúbal). Esses registros entram nos totais, não no mapa nem no ranking.")

# --- 3. Quando: série temporal ------------------------------------------------------

ui.secao("Quando: o volume ao longo do tempo")
col_ano, col_mes = st.columns([2, 3], gap="large")
pa = dp.por_ano(rec)

with col_ano:
    queda = ((1 - pa[2021] / pa[2019]) * 100
             if 2019 in pa.index and 2021 in pa.index and pa[2019] > 0 else None)
    if queda is not None and queda > 0:
        tit = (f"Os registros caíram de {dp.fmt_int(pa[2019])} para {dp.fmt_int(pa[2021])} "
               f"(−{dp.fmt_pct(queda, 0)}) de 2019 a 2021 — queda de registro, não "
               f"necessariamente de sinistros")
    elif queda is not None:
        # Em alguns recortes (ex.: só COM VÍTIMA) não há queda: não afirmar uma.
        tit = (f"Os registros passaram de {dp.fmt_int(pa[2019])} para {dp.fmt_int(pa[2021])} "
               "de 2019 a 2021")
    else:
        tit = f"{pa.idxmax()} é o ano com mais registros do recorte"
    ui.titulo_grafico(tit, f"Registros por ano · {_desc_recorte()} · n = {dp.fmt_int(N)}")
    cores = [t.DESTAQUE_CLARO if a == 2015 else t.DESTAQUE for a in pa.index]
    rotulos = [f"{dp.fmt_int(v)}<br>parcial" if a == 2015 else dp.fmt_int(v)
               for a, v in pa.items()]
    fig = go.Figure(go.Bar(
        x=pa.index, y=pa.values, marker=dict(color=cores, line=dict(color=t.FUNDO, width=2)),
        text=rotulos, textposition="outside", textfont=dict(color=t.TEXTO, size=12),
        cliponaxis=False, hovertemplate="%{x}: %{y:,} registros<extra></extra>"))
    ui.layout(fig, 340)
    if pa.index.min() <= 2021 and pa.index.max() >= 2020:
        ui.faixa(fig, max(2019.5, pa.index.min() - 0.5), min(2021.5, pa.index.max() + 0.5),
                 "queda na<br>base inteira")
    fig.update_xaxes(tickmode="array", tickvals=list(pa.index),
                     ticktext=["2015<br>jun–dez" if a == 2015 else str(a) for a in pa.index],
                     showgrid=False, tickangle=0, tickfont=dict(size=12))
    fig.update_yaxes(title=dict(text="registros (chamados)", font=dict(size=12)),
                     rangemode="tozero", range=[0, pa.max() * 1.25])
    st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="anual")

with col_mes:
    pm = dp.por_mes(rec)
    fora_ano = int(rec["data_fora_do_ano"].sum())
    if pm.empty:
        ui.titulo_grafico("Sem datas válidas no recorte", _desc_recorte())
    else:
        pico = pm.idxmax()
        ui.titulo_grafico(f"O mês com mais registros foi {ui.MESES[pico.month - 1]}/{pico.year}, "
                          f"com {dp.fmt_int(pm.max())}",
                          f"Registros por mês · {_desc_recorte()} · n = {dp.fmt_int(int(pm.sum()))}")
        x = pm.index.to_timestamp()
        fig = go.Figure(go.Scatter(
            x=x, y=pm.values, mode="lines" if len(pm) > 1 else "markers",
            line=dict(color=t.DESTAQUE, width=2), marker=dict(color=t.DESTAQUE, size=9),
            hovertemplate="%{x|%m/%Y}: %{y:,} registros<extra></extra>"))
        ui.layout(fig, 340, hovermode="x")
        ini, fim = pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")
        if x.min() <= fim and x.max() >= ini:
            ui.faixa(fig, max(ini, x.min()), min(fim, x.max()),
                     "2020–2021: queda de registro na<br>base inteira, causa desconhecida")
        if 2015 in anos_rec and len(pm) > 24:
            fig.add_annotation(x=x.min(), y=pm.iloc[0], text="série começa<br>em jun/2015",
                               showarrow=True, arrowhead=0, ax=24, ay=80,
                               font=dict(size=12, color=t.TEXTO), arrowcolor=t.TEXTO_2)
        fig.update_xaxes(showgrid=False, dtick="M12" if len(pm) > 24 else None,
                         tickformat="%Y" if len(pm) > 24 else "%m/%Y")
        fig.update_yaxes(title=dict(text="registros por mês", font=dict(size=12)),
                         rangemode="tozero")
        st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="mensal")

_b = dp.LINHAS_BRUTO
_s = df.groupby("ano").size()
_sev = dp.severidade_por_ano(df)
ui.nota(f"<b>A queda de 2019 para 2021 é de registro, não necessariamente de sinistros.</b> "
        f"Na base inteira (sem filtro), no bruto: {dp.fmt_int(_b[2019])} → {dp.fmt_int(_b[2020])} → "
        f"{dp.fmt_int(_b[2021])} linhas; no silver: {dp.fmt_int(_s[2019])} → {dp.fmt_int(_s[2020])} → "
        f"{dp.fmt_int(_s[2021])}. A causa é desconhecida e não deve ser lida como trânsito mais seguro. "
        f"Quase toda a queda está nos chamados SEM VÍTIMA ({dp.fmt_int(_sev.loc[2019, 'SEM VÍTIMA'])} em "
        f"2019, {dp.fmt_int(_sev.loc[2021, 'SEM VÍTIMA'])} em 2021); os COM VÍTIMA variam menos "
        f"({dp.fmt_int(_sev.loc[2019, 'COM VÍTIMA'])} e {dp.fmt_int(_sev.loc[2021, 'COM VÍTIMA'])}). "
        f"<b>2015 é parcial</b> (jun–dez) e não é comparável a anos cheios."
        + (f" {fora_ano} registro(s) do arquivo de 2024 com data em dez/2025 ficam fora da série "
           f"mensal e do mapa de calor (data não confiável), mas entram nos totais." if fora_ano else ""))

# --- 4. Hora x dia da semana -------------------------------------------------------

ui.secao("Quando: hora do dia e dia da semana")
n_hora = int(hd.values.sum())
if n_hora == 0:
    ui.titulo_grafico("Nenhum registro do recorte tem hora e data válidas", _desc_recorte())
else:
    d_pico, h_pico = hd.stack().idxmax()
    ui.titulo_grafico(
        f"O pico é {dp.DIAS_SEMANA[d_pico].lower()} às {h_pico}h, com {dp.fmt_int(hd.values.max())} "
        f"registros. {dp.fmt_pct(pct_dia, 0)} caem entre 7h e 19h",
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
    ui.layout(fig, 300)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=t.TEXTO))
    fig.update_xaxes(showgrid=False, side="top", title=None)
    # Container com chave: no celular o CSS esconde os rótulos e o valor aparece ao tocar.
    with st.container(key="mapa_calor"):
        st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="calor")
ui.nota(f"Hora do registro do chamado. <b>{dp.fmt_int(sem_hora)} registros do recorte ficam fora</b> "
        f"por falta de hora válida ou por data incompatível com o ano do arquivo. O arquivo de 2022 "
        f"não traz horários. No celular, toque numa célula para ver o valor.")

# --- 5. Severidade ---------------------------------------------------------------

ui.secao("O que os caracteriza: severidade")
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
                           text=f"2016–2020: vitimasfatais até {dp.fmt_pct(_fatal_ruim.max(), 2)} preenchida",
                           font=dict(size=12, color=t.TEXTO))


with col_sev:
    tem_com_sem = {"COM VÍTIMA", "SEM VÍTIMA"} <= set(sevs)
    if tem_com_sem and 2019 in prop.index and prop.index.max() >= 2021:
        a1 = int(prop.index.max())
        tit = (f"Chamados com vítima eram {dp.fmt_pct(prop.loc[2019, 'COM VÍTIMA'])} em 2019 "
               f"e {dp.fmt_pct(prop.loc[a1, 'COM VÍTIMA'])} em {a1} neste recorte: "
               f"são os SEM VÍTIMA que deixam de aparecer na base")
    else:
        tit = "Composição dos registros por severidade, ano a ano"
    ui.titulo_grafico(tit, f"% dos registros de cada ano · {_desc_recorte()} · n = {dp.fmt_int(N)}")
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
    ui.layout(fig, 360, barmode="stack", showlegend=True, bargap=0.2,
              legend=dict(orientation="h", y=-0.18, x=0, font=dict(color=t.TEXTO, size=12),
                          traceorder="normal"))
    fig.update_layout(margin=dict(t=28))
    _faixa_fatais(fig, prop.index)
    fig.update_xaxes(tickmode="array", tickvals=list(prop.index),
                     ticktext=["2015<br>jun–dez" if a == 2015 else str(a) for a in prop.index],
                     showgrid=False, tickangle=0, tickfont=dict(size=12))
    fig.update_yaxes(title=dict(text="% dos registros do ano", font=dict(size=12)),
                     range=[0, 100], ticksuffix="%")
    st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="severidade")

with col_fat:
    fat = spa["VÍTIMA FATAL"]
    ui.titulo_grafico(
        f"{dp.fmt_int(int(fat.sum()))} chamados com vítima fatal no recorte",
        f"Registros com severidade “VÍTIMA FATAL”, por ano · {_desc_recorte()} · "
        f"n = {dp.fmt_int(int(fat.sum()))}")
    if fat.sum() == 0:
        ui.nota("Nenhum chamado com vítima fatal neste recorte.")
    else:
        fig = go.Figure(go.Bar(
            x=fat.index, y=fat.values, marker=dict(color=t.ESCURO, line=dict(color=t.FUNDO, width=2)),
            text=[dp.fmt_int(v) for v in fat.values], textposition="outside",
            textfont=dict(color=t.TEXTO, size=12), cliponaxis=False,
            hovertemplate="%{x}: %{y} chamados com vítima fatal<extra></extra>"))
        ui.layout(fig, 360)
        fig.update_layout(margin=dict(t=28))
        _faixa_fatais(fig, fat.index)
        fig.update_xaxes(tickmode="array", tickvals=list(fat.index),
                         ticktext=["2015<br>jun–dez" if a == 2015 else str(a) for a in fat.index],
                         showgrid=False, tickangle=0, tickfont=dict(size=12))
        fig.update_yaxes(title=dict(text="chamados com vítima fatal", font=dict(size=12)),
                         rangemode="tozero", range=[0, fat.max() * 1.3])
        st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="fatais")

ui.nota("<b>Fatais são contados pela severidade “VÍTIMA FATAL”, não pela soma de vitimasfatais.</b> "
        f"A coluna vitimasfatais não existe em 2015 e, de 2016 a 2020, tem só {_faixa_fatal} das "
        "células preenchidas: célula vazia é desconhecido, nunca zero. Ela só é utilizável de 2021 "
        "em diante. A severidade conta chamados com ao menos uma morte, não o número de mortos.")

# --- Como ler este painel -----------------------------------------------------------

ui.secao("Como ler esta página")
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
<li><b>Fatais são chamados com severidade “VÍTIMA FATAL”.</b> A coluna vitimasfatais (pessoas
vitimadas) só tem preenchimento consistente a partir de 2021; antes, vazio é desconhecido.</li>
<li><b>Sem coordenadas</b>: os CSVs não têm latitude/longitude, por isso o mapa é por bairro.</li>
<li><b>Bairro “NÃO INFORMADO”</b> ({dp.fmt_int(rc['nao_informado'])} registros no total) entra nos
totais e sai do ranking e do mapa. {casamento}</li>
<li><b>2022 não tem hora.</b> Esses registros ficam fora do mapa de calor, assim como os de data
incompatível com o ano do arquivo.</li>
</ul>""", unsafe_allow_html=True)
