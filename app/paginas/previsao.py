"""
Página "Previsão de volume elevado" (E6).

Só EXIBE e explora a avaliação dos classificadores (ADR-017): lê os artefatos
de data/classificacao/. Nada é treinado aqui. Limiar oficial (0,16), modelo
(regressão logística) e partições estão fixados; o limiar exploratório não
muda a tabela oficial.

Recorte diferente da página de pontos críticos: todos os status, bairro com
casamento exato no cadastro oficial (sem os aliases do ADR-016).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dados_painel as dp
import dados_previsao as dprev
import estado
import tema as t
import ui

art = estado.artefatos_previsao()
if art is None:
    ui.titulo_pagina("Artefatos da previsão não encontrados",
                     "Gere com: python src/classificacao/gerar_artefatos.py")
    st.stop()

df, _ = estado.silver()
malha = estado.malha()
_, bairros_filtro, _ = estado.filtros()
meta, cob = art["meta"], art["cobertura"]
MOD = meta["modelo_selecionado"]
LIM = float(meta["limiares"][MOD])
of = dprev.oficial(art, MOD)
pers = dprev.oficial(art, "persistencia")
arv = dprev.oficial(art, "arvore")
of_val, arv_val = dprev.oficial(art, MOD, "validacao"), dprev.oficial(art, "arvore", "validacao")
pred_all = art["predicoes"]
pred = pred_all[pred_all["modelo"] == MOD].copy()
pred["cat"] = dprev.categoria(pred)
part = art["particoes"].set_index("particao")

COR_CAT = t.CORES_RESULTADO  # azul = acerto, laranja = erro (tema.py)


def f3(v: float) -> str:
    return f"{v:.3f}".replace(".", ",")


def lim2(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def pct(v: float, casas: int = 1) -> str:
    return dp.fmt_pct(v * 100, casas)


def nome_bairro(chave: str) -> str:
    """Nome exibido. Para os 5 bairros do de-para do ADR-016 usa o nome do
    cadastro (ex.: 'Recife', não 'Bairro do Recife'): aqui eles só contam os
    chamados com o nome exato do cadastro."""
    if chave in set(dp.ALIAS_MALHA.values()):
        return dp.nome_exibicao(chave)
    return NOME_E4.get(chave, dp.nome_exibicao(chave))


NOME_E4 = (df.dropna(subset=["bairro_chave"]).drop_duplicates("bairro_chave")
             .set_index("bairro_chave")["bairro_painel"].to_dict()) if df is not None else {}

# --- Selo e filtros ----------------------------------------------------------------

# Container reservado no topo: o título é escrito nele depois, mas aparece ACIMA
# do selo — hierarquia título > achado > selo/indicadores (ADR-016).
cab = st.container()
fora_alvo = cob["registros_janela_modelo"] - cob["registros_no_alvo"]
fim_2024 = pd.Timestamp(cob["ultima_data_2024"])
dias_sem = fim_2024.days_in_month - fim_2024.day
qa = art["qualidade"].set_index("ano")
ui.selo(
    f"chamados de {cob['janela_modelo_anos'][0]}–{cob['janela_modelo_anos'][1]} · "
    f"<b>todos os status</b> (inclui cancelados e duplicidades; a página de pontos críticos usa só "
    f"FINALIZADA) · <b>{dp.fmt_int(cob['registros_no_alvo'])}</b> de "
    f"{dp.fmt_int(cob['registros_janela_modelo'])} chamados entram no alvo ({dp.fmt_int(fora_alvo)} "
    f"ficam fora por bairro fora do cadastro oficial ou data de outro ano) · "
    f"{dp.fmt_int(cob['bairro_meses'])} bairro-meses ({meta['n_bairros']} bairros, "
    f"{part.loc['treino', 'inicio']} a {part.loc['teste', 'fim']}); teste = "
    f"{dp.fmt_int(part.loc['teste', 'n'])} bairro-meses de 2024.",
    [f"2015 começa em junho ({pd.Timestamp(cob['primeira_data_2015']):%d/%m/%Y}) — fora da janela "
     f"do modelo, não afeta esta página.",
     f"2022 não tem horário utilizável ({cob['horas_validas_2022']} horas válidas) — o modelo não "
     f"usa hora, não afeta esta página.",
     f"Vítimas fatais só são conhecidas a partir de {cob['primeiro_ano_vitimasfatais_completas']} — "
     f"o alvo é volume de chamados, não gravidade; não afeta esta página.",
     f"2024 tem {cob['datas_outro_ano_2024']} datas de outro ano (ficam fora do alvo) e termina em "
     f"{fim_2024:%d/%m/%Y}: dezembro de 2024 tem {dias_sem} dias sem registro no arquivo."])
ui.filtros_aplicados([
    ("Anos", "não se aplica — a avaliação é fixa (teste = 2024)"),
    ("Severidade", "não se aplica — o alvo conta chamados de qualquer severidade"),
    ("Status", "esta página usa todos os status, sem filtro"),
    ("Bairros", "aplicado ao mapa e à tabela por bairro; as métricas oficiais não mudam"),
])

# --- Topo ----------------------------------------------------------------------------

with cab:
    ui.titulo_pagina(
    f"O modelo escolhido identificou {pct(of['recall'])} dos bairro-meses de volume elevado em "
    f"2024, com {dp.fmt_int(of['fp'])} alertas falsos",
    f"Ganho pequeno sobre simplesmente repetir o mês anterior (persistência): F1 {f3(pers['f1'])} → "
    f"{f3(of['f1'])}, com {dp.fmt_int(pers['fn'] - of['fn'])} omissões a menos e "
    f"{dp.fmt_int(of['fp'] - pers['fp'])} alertas falsos a mais.")
cab.markdown(f"""<div class="caixa">
<div><b>O que é.</b> Para cada bairro e mês, a previsão diz se o volume de <b>chamados registrados</b>
será elevado: pelo menos {meta['corte_contagem']} chamados, corte calculado no treino (percentil 75).
É uma avaliação <b>retrospectiva, de um passo à frente</b>: ao fim de cada mês de 2024, prevê o mês
seguinte com o histórico até ali. Modelo treinado só até dez/2022.</div>
<div><b>O que não é.</b> Não prevê gravidade, mortalidade nem risco individual. Não é previsão de
acidentes confirmados (são chamados da CTTU) e não tem ajuste por fluxo ou exposição. Os scores não são
probabilidades calibradas. <b>Não houve validação operacional</b> — ninguém usou estes alertas na rua.</div>
</div>""", unsafe_allow_html=True)

ic = art["ic"].set_index(["modelo", "metrica"])
ic_f1 = ic.loc[(MOD, "f1")]
ui.kpis([
    (f3(of["f1"]), f"F1 no teste 2024 · IC 95% exploratório {f3(ic_f1['ic95_inferior'])}–"
                   f"{f3(ic_f1['ic95_superior'])} (bootstrap por mês)"),
    (pct(of["recall"]), f"recall · {dp.fmt_int(of['tp'])} de {dp.fmt_int(of['positivos'])} "
                        f"bairro-meses elevados"),
    (pct(of["precisao"]), f"precisão · {dp.fmt_int(of['tp'])} de {dp.fmt_int(of['tp'] + of['fp'])} alertas"),
    (pct(part.loc["teste", "prevalencia"]), f"prevalência no teste · {dp.fmt_int(of['positivos'])} de "
                                            f"{dp.fmt_int(of['n'])} bairro-meses"),
])

# --- Comparação dos modelos ------------------------------------------------------------

ui.secao("Comparação dos quatro modelos")
col_tab, col_cm = st.columns([11, 9], gap="large")
with col_tab:
    ui.titulo_grafico(
        f"A árvore tem o maior F1 no teste ({f3(arv['f1'])}), mas a escolha foi feita na validação, "
        f"onde a logística venceu ({f3(of_val['f1'])} × {f3(arv_val['f1'])})",
        f"Métricas oficiais no teste 2024 · n = {dp.fmt_int(of['n'])} bairro-meses · "
        f"limiar de cada modelo escolhido em 2023")
    m = art["metricas"].set_index(["modelo", "particao"])
    linhas = []
    for mod in dprev.ORDEM:
        te, va = m.loc[(mod, "teste")], m.loc[(mod, "validacao")]
        rot = dprev.NOMES[mod] + (" — selecionado" if mod == MOD else "")
        linhas.append(f'<tr class="{"sel" if mod == MOD else ""}"><td>{rot}</td>'
                      f'<td>{f3(va["f1"])}</td><td>{lim2(te["limiar"])}</td>'
                      f'<td>{pct(te["acuracia"])}</td><td>{pct(te["precisao"])}</td>'
                      f'<td>{pct(te["recall"])}</td><td>{f3(te["f1"])}</td>'
                      f'<td>{f3(te["roc_auc"])}</td><td>{f3(te["average_precision"])}</td></tr>')
    st.markdown('<table class="tab" data-testid="tabela-oficial"><tr><th>Modelo</th>'
                '<th>F1 validação 2023</th><th>Limiar</th><th>Acurácia</th><th>Precisão</th>'
                '<th>Recall</th><th>F1 teste</th><th>ROC AUC</th><th>AP</th></tr>'
                + "".join(linhas) + "</table>", unsafe_allow_html=True)
    ui.nota(f"Escolher pelo teste seria usar 2024 para decidir e depois avaliar em 2024. "
            f"Persistência = prever elevado se o mês anterior teve ao menos {meta['corte_contagem']} "
            f"chamados. Majoritária = sempre prever “regular” (acurácia {pct(dprev.oficial(art, 'dummy')['acuracia'])} "
            f"sem acertar nenhum elevado). AP = average precision.")

with col_cm:
    ui.titulo_grafico(f"{dprev.NOMES[MOD]}: {dp.fmt_int(of['fn'])} omissões e "
                      f"{dp.fmt_int(of['fp'])} alertas falsos",
                      f"Matriz de confusão no teste 2024 · limiar {lim2(LIM)} · "
                      f"n = {dp.fmt_int(of['n'])} bairro-meses")
    celulas = [["FN", "VP"], ["VN", "FP"]]  # linhas: observado elevado / regular
    val = {"VP": of["tp"], "FP": of["fp"], "FN": of["fn"], "VN": of["tn"]}
    fig = go.Figure(go.Heatmap(
        z=[[0, 1], [2, 3]], x=["previsto regular", "previsto elevado"],
        y=["observado elevado", "observado regular"], showscale=False, xgap=3, ygap=3,
        # z = 0,1,2,3 normalizado em 0, 1/3, 2/3, 1: cada valor cai no meio de um degrau.
        colorscale=[[0, COR_CAT["FN"]], [.25, COR_CAT["FN"]], [.25, COR_CAT["VP"]], [.5, COR_CAT["VP"]],
                    [.5, COR_CAT["VN"]], [.75, COR_CAT["VN"]], [.75, COR_CAT["FP"]], [1, COR_CAT["FP"]]],
        hoverinfo="skip"))
    for i, linha in enumerate(celulas):
        for j, c in enumerate(linha):
            fig.add_annotation(x=j, y=i, showarrow=False,
                               text=f"<b>{c} {dp.fmt_int(val[c])}</b><br>{pct(val[c] / of['n'])}",
                               font=dict(size=15, color=t.texto_sobre(COR_CAT[c])))
    ui.layout(fig, 320)
    fig.update_xaxes(side="top", showgrid=False, tickangle=0, tickfont=dict(color=t.TEXTO))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=t.TEXTO))
    st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="matriz")
    ui.nota("VP = acerto de volume elevado · VN = acerto de volume regular · FP = alerta falso · "
            "FN = omissão. % sobre os bairro-meses do teste.")

# --- Curvas ROC e PR -------------------------------------------------------------------

ui.secao("Curvas ROC e precision-recall (teste 2024)")
cur = art["curvas"]
prev_teste = float(part.loc["teste", "prevalencia"])
ESTILO = {MOD: dict(color=t.DESTAQUE, width=3),
          "persistencia": dict(color=t.TEXTO_2, width=2, dash="dash"),
          "arvore": dict(color="#8A8984", width=2, dash="dot")}
col_roc, col_pr = st.columns(2, gap="large")
for col, tipo in [(col_roc, "roc"), (col_pr, "pr")]:
    with col:
        if tipo == "roc":
            ui.titulo_grafico(f"ROC AUC da logística: {f3(of['roc_auc'])} (persistência "
                              f"{f3(pers['roc_auc'])})",
                              f"Recall × taxa de falsos positivos em todos os limiares · "
                              f"n = {dp.fmt_int(of['n'])}")
        else:
            ui.titulo_grafico(f"Average precision da logística: {f3(of['average_precision'])}, "
                              f"contra {pct(prev_teste)} de prevalência",
                              f"Precisão × recall em todos os limiares · n = {dp.fmt_int(of['n'])}")
        fig = go.Figure()
        if tipo == "roc":
            fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="referência aleatória",
                                     line=dict(color=t.CINZA_MARCA, width=1, dash="dash"),
                                     hoverinfo="skip"))
        else:
            fig.add_trace(go.Scatter(x=[0, 1], y=[prev_teste, prev_teste], mode="lines",
                                     name=f"prevalência do teste ({pct(prev_teste)})",
                                     line=dict(color=t.CINZA_MARCA, width=1, dash="dash"),
                                     hoverinfo="skip"))
        for mod in ["arvore", "persistencia", MOD]:
            c = cur[(cur["modelo"] == mod) & (cur["curva"] == tipo)]
            r = dprev.oficial(art, mod)
            extra = f"AUC {f3(r['roc_auc'])}" if tipo == "roc" else f"AP {f3(r['average_precision'])}"
            fig.add_trace(go.Scatter(
                x=c["x"], y=c["y"], mode="lines", name=f"{dprev.NOMES[mod]} · {extra}",
                line=dict(shape="hv" if tipo == "pr" else "linear", **ESTILO[mod]),
                hovertemplate=f"{dprev.NOMES[mod]}<br>x %{{x:.2f}} · y %{{y:.2f}}<extra></extra>"))
        ui.layout(fig, 340, showlegend=True,
                  legend=dict(x=0.98 if tipo == "roc" else 0.02, xanchor="right" if tipo == "roc" else "left",
                              y=0.02, yanchor="bottom", font=dict(color=t.TEXTO, size=12),
                              bgcolor="rgba(255,255,255,0.85)"))
        fig.update_xaxes(range=[0, 1], title=dict(
            text="taxa de falsos positivos" if tipo == "roc" else "recall", font=dict(size=12)))
        fig.update_yaxes(range=[0, 1.02], title=dict(
            text="recall" if tipo == "roc" else "precisão", font=dict(size=12)))
        st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key=f"curva_{tipo}")
ui.nota("A majoritária não aparece: seu score é constante e a curva coincide com a referência. "
        "Os scores não são calibrados; a persistência é um índice monotônico do mês anterior.")

# --- Mapa 2024 ------------------------------------------------------------------------

ui.secao("Onde o modelo acertou e errou em 2024")
periodos = sorted(pred["periodo"].unique())
mes = st.select_slider("Mês de 2024", options=periodos, value=periodos[0], key="prev_mes",
                       format_func=lambda p: f"{ui.MESES[int(p[-2:]) - 1]}/{p[:4]}")
chaves_f = dprev.chaves_do_filtro(df, bairros_filtro)
pm = pred[pred["periodo"] == mes]
if chaves_f is not None:
    pm = pm[pm["bairro"].isin(chaves_f)]

col_m, col_c = st.columns([3, 2], gap="large")
if pm.empty:
    with col_m:
        ui.titulo_grafico("Nenhum bairro do filtro tem previsão",
                          f"{ui.MESES[int(mes[-2:]) - 1]}/{mes[:4]} · filtro de bairros da barra lateral")
        ui.nota("Os bairros selecionados não estão no cadastro oficial dos 94 bairros (ex.: “NÃO "
                "INFORMADO”, Setúbal) e por isso não têm previsão. Limpe ou troque o filtro de bairros.")
else:
    cont = pm["cat"].value_counts().reindex(["VP", "FN", "FP", "VN"], fill_value=0)
    rot_mes = f"{ui.MESES[int(mes[-2:]) - 1]}/{mes[:4]}"
    with col_m:
        ui.titulo_grafico(
            f"Em {rot_mes}: {cont['VP']} acertos de volume elevado, {cont['FN']} omissões e "
            f"{cont['FP']} alertas falsos",
            f"Bairros por resultado da {dprev.NOMES[MOD].lower()} · "
            f"{'todos os bairros' if chaves_f is None else f'{len(pm)} bairro(s) do filtro'} · "
            f"n = {len(pm)} bairro-meses")
        if malha is None:
            ui.nota("Malha de bairros indisponível: veja a contagem ao lado. "
                    "Para ativar o mapa: <code>python src/baixa_malha_bairros.py</code>")
        else:
            chaves = [f["properties"]["chave"] for f in malha["features"]]
            fig = go.Figure(go.Choropleth(
                geojson=malha, featureidkey="properties.chave", locations=chaves,
                z=[0] * len(chaves), colorscale=[[0, t.GRADE], [1, t.GRADE]], showscale=False,
                marker=dict(line=dict(color=t.FUNDO, width=0.8)),
                text=[nome_bairro(c) for c in chaves],
                hovertemplate="<b>%{text}</b><br>fora do filtro<extra></extra>"))
            for c in ["VP", "FN", "FP", "VN"]:
                g = pm[pm["cat"] == c]
                if g.empty:
                    continue
                fig.add_trace(go.Choropleth(
                    geojson=malha, featureidkey="properties.chave", locations=g["bairro"],
                    z=[1] * len(g), colorscale=[[0, COR_CAT[c]], [1, COR_CAT[c]]], showscale=False,
                    marker=dict(line=dict(color=t.FUNDO, width=0.8)), name=f"{c}: {dprev.CATEGORIAS[c]}",
                    text=[nome_bairro(b) for b in g["bairro"]],
                    customdata=np.c_[g["chamados"], g["score"], g["lag1"]],
                    hovertemplate=(f"<b>%{{text}}</b><br>{c}: {dprev.CATEGORIAS[c]}<br>"
                                   "chamados no mês: %{customdata[0]:.0f}<br>"
                                   "mês anterior: %{customdata[2]:.0f}<br>"
                                   "score: %{customdata[1]:.2f}<extra></extra>")))
            fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator",
                            bgcolor=t.FUNDO)
            ui.layout(fig, 460, dragmode=False)
            st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="mapa_prev")
    with col_c:
        ui.titulo_grafico("Contagem do mês", f"{rot_mes} · n = {len(pm)} bairro-meses")
        corpo = "".join(
            f'<tr><td><span style="display:inline-block;width:12px;height:12px;background:{COR_CAT[c]};'
            f'border:1px solid {t.TEXTO_2};margin-right:8px;vertical-align:middle"></span>'
            f'{c} — {dprev.CATEGORIAS[c]}</td><td>{cont[c]}</td></tr>' for c in ["VP", "FN", "FP", "VN"])
        st.markdown(f'<table class="tab"><tr><th>Resultado</th><th>Bairros</th></tr>{corpo}</table>',
                    unsafe_allow_html=True)
        ui.nota("Cor = resultado: azul é acerto, laranja é erro; escuro = volume elevado observado, "
                "claro = regular observado. Cinza = fora do filtro de bairros.")
        if chaves_f is not None:
            g = pred[pred["bairro"].isin(chaves_f)]
            tab = g.groupby(["bairro", "cat"]).size().unstack(fill_value=0).reindex(
                columns=["VP", "FN", "FP", "VN"], fill_value=0)
            corpo = "".join(f"<tr><td>{nome_bairro(b)}</td>" + "".join(f"<td>{r[c]}</td>" for c in tab.columns)
                            + "</tr>" for b, r in tab.iterrows())
            ui.titulo_grafico("Bairros do filtro, 2024 inteiro", "meses por resultado (de 12)")
            st.markdown('<table class="tab"><tr><th>Bairro</th><th>VP</th><th>FN</th><th>FP</th>'
                        f'<th>VN</th></tr>{corpo}</table>', unsafe_allow_html=True)
ui.nota(f"Bairro com casamento exato no cadastro oficial (sem o de-para do ADR-016): por isso "
        f"“Recife”, “Ilha Joana Bezerra”, “Alto Santa Terezinha”, “Poco” e “Ipsep” contam aqui só os "
        f"chamados com o nome do cadastro. Na janela 2021–2024, "
        f"{dp.fmt_int(cob['registros_janela_bairro_nao_validado'])} chamados têm bairro fora do cadastro "
        f"e ficam fora do alvo.")

# --- Limiar exploratório ----------------------------------------------------------------

ui.secao("Exploração: e se o limiar fosse outro?")
st.markdown('<p class="aplica"><b>Exploração, não resultado oficial.</b> O slider recalcula a matriz '
            'sobre as predições de 2024 já gravadas. A tabela oficial acima não muda. O limiar oficial '
            f'({lim2(LIM)}) foi escolhido na validação 2023; escolher olhando 2024 '
            'seria usar o teste para decidir.</p>', unsafe_allow_html=True)
lim = st.slider("Limiar exploratório do score", 0.05, 0.95, LIM, 0.01, key="lim_explora")
ex, base_of = dprev.matriz_no_limiar(pred, lim), dprev.matriz_no_limiar(pred, LIM)


def _delta(chave: str) -> str:
    d = ex[chave] - base_of[chave]
    return "igual ao oficial" if d == 0 else f"{'+' if d > 0 else '−'}{abs(d)} vs. oficial"


ui.kpis([
    (dp.fmt_int(ex["FP"]), f"alertas falsos · {_delta('FP')}"),
    (dp.fmt_int(ex["FN"]), f"omissões · {_delta('FN')}"),
    (pct(ex["precisao"]), f"precisão · oficial {pct(base_of['precisao'])}"),
    (pct(ex["recall"]), f"recall · oficial {pct(base_of['recall'])}"),
])
cl = dprev.curva_limiares(pred)
ui.titulo_grafico(
    f"Com limiar {lim2(lim)}: {ex['FP']} alertas falsos e {ex['FN']} omissões "
    f"(oficial: {base_of['FP']} e {base_of['FN']})",
    f"Alertas falsos e omissões no teste 2024 para cada limiar · n = {dp.fmt_int(ex['n'])} bairro-meses")
fig = go.Figure()
for chave, cor, rotulo in [("FP", COR_CAT["FP"], "alertas falsos"), ("FN", COR_CAT["FN"], "omissões")]:
    fig.add_trace(go.Scatter(x=cl["limiar"], y=cl[chave], mode="lines", name=rotulo,
                             line=dict(color=cor, width=3),
                             hovertemplate=f"limiar %{{x:.2f}}: %{{y}} {rotulo}<extra></extra>"))
    fig.add_annotation(x=cl["limiar"].iloc[-1], y=cl[chave].iloc[-1], text=rotulo, showarrow=False,
                       xanchor="left", xshift=6, font=dict(size=12, color=t.TEXTO))
fig.add_vline(x=LIM, line=dict(color=t.TEXTO, width=1.5))
fig.add_annotation(x=LIM, y=1, yref="paper", yanchor="bottom", text="oficial (validação 2023)",
                   showarrow=False, font=dict(size=12, color=t.TEXTO))
if abs(lim - LIM) > 1e-9:
    fig.add_vline(x=lim, line=dict(color=t.TEXTO_2, width=1.5, dash="dash"))
    fig.add_annotation(x=lim, y=0.9, yref="paper", text="explorado", showarrow=False,
                       xanchor="left", xshift=4, font=dict(size=12, color=t.TEXTO_2))
ui.layout(fig, 300)
fig.update_layout(margin=dict(t=28, r=90))
fig.update_xaxes(range=[0.05, 0.95], title=dict(text="limiar do score", font=dict(size=12)))
fig.update_yaxes(rangemode="tozero", title=dict(text="bairro-meses", font=dict(size=12)))
st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="curva_limiar")

# --- F1 mensal -------------------------------------------------------------------------

ui.secao("Estabilidade ao longo de 2024")
mm = art["mensal"]
lm, pmen = mm[mm["modelo"] == MOD].sort_values("periodo"), mm[mm["modelo"] == "persistencia"].sort_values("periodo")
pmin, pmax = lm.loc[lm["f1"].idxmin()], lm.loc[lm["f1"].idxmax()]
lbl = lambda p: f"{ui.MESES[int(p[-2:]) - 1]}/{p[:4]}"  # noqa: E731
ui.titulo_grafico(
    f"O F1 mensal da logística vai de {f3(pmin['f1'])} ({lbl(pmin['periodo'])}) a "
    f"{f3(pmax['f1'])} ({lbl(pmax['periodo'])})",
    f"F1 por mês do teste 2024 · {meta['n_bairros']} bairro-meses por ponto · limiar oficial")
fig = go.Figure()
for g, nome, est in [(pmen, "Persistência", dict(color=t.TEXTO_2, width=2, dash="dash")),
                     (lm, dprev.NOMES[MOD], dict(color=t.DESTAQUE, width=3))]:
    fig.add_trace(go.Scatter(
        x=[lbl(p) for p in g["periodo"]], y=g["f1"], mode="lines+markers", name=nome, line=est,
        marker=dict(size=8), customdata=np.c_[g["positivos"], g["n"]],
        hovertemplate=f"{nome} · %{{x}}: F1 %{{y:.3f}}<br>%{{customdata[0]}} elevados de "
                      f"%{{customdata[1]}}<extra></extra>"))
ui.layout(fig, 300, showlegend=True, legend=dict(orientation="h", y=-0.2, x=0,
                                                 font=dict(color=t.TEXTO, size=12)))
fig.update_yaxes(range=[0, 1], title=dict(text="F1", font=dict(size=12)))
fig.update_xaxes(showgrid=False)
st.plotly_chart(fig, width="stretch", config=ui.CONFIG, key="f1_mensal")
ui.nota(f"O arquivo de 2024 termina em {fim_2024:%d/%m/%Y}: dezembro tem {dias_sem} "
        f"dias a menos de registro, o que reduz as contagens do mês e pode mudar o alvo de bairros perto do "
        f"corte. Cada ponto tem só {meta['n_bairros']} bairro-meses: oscilação mensal é esperada.")

# --- Como ler -------------------------------------------------------------------------

ui.secao("Como ler esta página")
st.markdown(f"""<ul class="limites">
<li><b>Chamados não são acidentes confirmados</b>: a contagem inclui todos os status, até cancelados e
duplicidades.</li>
<li><b>Sem ajuste por exposição ou fluxo</b>: bairros com mais tráfego tendem a ter mais chamados.</li>
<li><b>A prevalência muda entre períodos</b>: {pct(part.loc['treino', 'prevalencia'])} no treino,
{pct(part.loc['validacao', 'prevalencia'])} na validação e {pct(prev_teste)} no teste — o corte de
{meta['corte_contagem']} chamados é fixo e o volume registrado cresce de
{dp.fmt_int(qa.loc[2021, 'registros'])} chamados em 2021 para {dp.fmt_int(qa.loc[2024, 'registros'])} em 2024
(todos os status).</li>
<li><b>Intervalos exploratórios</b>: o IC 95% do F1 vem de bootstrap com 12 blocos mensais; é
aproximação, não garantia.</li>
<li><b>Recorte diferente da página de pontos críticos</b> (todos os status e casamento exato de bairro):
os números das duas páginas não devem ser somados nem comparados diretamente.</li>
</ul>""", unsafe_allow_html=True)
