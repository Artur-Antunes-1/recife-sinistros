"""
Página "Metodologia" (TRN-01, E6): fonte, filtros, fórmulas e método dos
classificadores. Divulgação progressiva: resumo visível, detalhe em expanders.
Todos os números são lidos do silver ou dos artefatos, nunca digitados.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import dados_painel as dp
import estado
import tema as t
import ui

df, rel = estado.silver()
art = estado.artefatos_previsao()
cob = art["cobertura"] if art else None
meta = art["meta"] if art else None

_ok = df.loc[~df["data_fora_do_ano"], "data"]
ui.selo(
    f"esta página descreve os dois recortes do painel — <b>pontos críticos</b>: "
    f"{dp.fmt_int(len(df))} chamados FINALIZADA, {ui.mes_ano(_ok.min())} a {ui.mes_ano(_ok.max())}"
    + (f"; <b>previsão</b>: {dp.fmt_int(cob['registros_no_alvo'])} chamados de todos os status, "
       f"{cob['janela_modelo_anos'][0]}–{cob['janela_modelo_anos'][1]}." if cob else "."),
    ["2015 começa em junho · 2022 não tem horário utilizável · vítimas fatais só são conhecidas "
     "a partir de 2021 · 2024 termina em "
     + (f"{pd.Timestamp(cob['ultima_data_2024']):%d/%m/%Y}" if cob else
        f"{df.loc[(df['ano'] == 2024) & ~df['data_fora_do_ano'], 'data'].max():%d/%m/%Y}")
     + " e tem datas de outro ano "
     + (f"({int(df['data_fora_do_ano'].sum())} no recorte FINALIZADA, "
        f"{cob['datas_outro_ano_2024']} em todos os status)." if cob else ".")])
ui.filtros_aplicados([("Anos, Bairros e Severidade", "não se aplicam — esta página é texto de referência")])

ui.titulo_pagina("Como os números deste painel são produzidos",
                 "Dois recortes da mesma fonte, cada um com um propósito. Resumo aqui; detalhes nos "
                 "blocos expansíveis.")

# --- Fonte ---------------------------------------------------------------------------

ui.secao("Fonte")
baixado = dp.data_download_raw()
st.markdown(
    f"Chamados de sinistro de trânsito da **CTTU**, Portal de Dados Abertos do Recife "
    f"(licença ODbL): 10 arquivos anuais, 2015 a 2024"
    + (f", baixados em {baixado:%d/%m/%Y}" if baixado is not None else "") + ". "
    "Malha e cadastro oficial de bairros: dataset “Área urbana” do mesmo portal (ODbL). "
    "A base não tem latitude/longitude: toda análise geográfica é por bairro.")
with st.expander("Detalhes da fonte e da integridade dos arquivos"):
    st.markdown(
        "- Os 10 CSVs de `data/raw/` são byte a byte iguais aos do snapshot usado na avaliação dos "
        "classificadores (SHA-256 conferido contra `manifesto_aquisicao.json`, ADR-017).\n"
        "- O dicionário oficial do portal está desatualizado; o dado real é a referência (ADR-009).\n"
        "- O layout muda entre anos (nome e significado de colunas); a severidade é detectada pelo "
        "valor, não pelo nome da coluna (ADR-004).")

# --- Os dois recortes ------------------------------------------------------------------

ui.secao("Filtros e recortes")
linhas = [
    ("Páginas", "Pontos críticos", "Previsão de volume elevado"),
    ("Status do chamado", "só FINALIZADA (ADR-005)", "todos (inclui CANCELADA, DUPLICIDADE…)"),
    ("Anos", f"{int(df['ano'].min())}–{int(df['ano'].max())}",
     f"{cob['janela_modelo_anos'][0]}–{cob['janela_modelo_anos'][1]} (painel de jul/2021 a dez/2024)"
     if cob else "—"),
    ("Registros", dp.fmt_int(len(df)),
     f"{dp.fmt_int(cob['registros_no_alvo'])} no alvo, de {dp.fmt_int(cob['registros'])} na base" if cob else "—"),
    ("Duplicatas", "linha idêntica ou protocolo repetido (ADR-015)", "só cópia com protocolo (0 casos)"),
    ("Bairro", f"normalização + de-para de {len(dp.ALIAS_MALHA)} grafias (ADR-016)",
     "casamento exato com o cadastro de 94 bairros"),
    ("Data fora do ano", "fica nos totais, sai da série mensal", "fica fora do alvo"),
]
corpo = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in linhas[1:])
st.markdown(f'<table class="tab"><tr><th></th><th>{linhas[0][1]}</th><th>{linhas[0][2]}</th></tr>'
            f'{corpo}</table>', unsafe_allow_html=True)
ui.nota("Por que dois recortes: a avaliação dos classificadores foi entregue com todos os status e "
        "está fixada; alinhá-la a FINALIZADA exigiria retreinar e mudaria o alvo de parte dos bairro-meses. "
        "Decisão registrada no ADR-017. Os números das duas páginas não se somam nem se comparam "
        "diretamente.")
with st.expander("Filtros da barra lateral"):
    st.markdown(
        "- **Anos, Bairros, Severidade** se combinam e valem para todos os gráficos de *Pontos críticos*.\n"
        "- Em *Previsão*, só o filtro de **Bairros** vale (mapa e tabela por bairro); anos e severidade "
        "não se aplicam e a página diz isso no topo. As métricas oficiais nunca mudam com filtro.\n"
        "- Bairro “NÃO INFORMADO” entra nos totais e sai de ranking, mapa e concentração; a cobertura "
        "do mapa é mostrada sob ele.")

# --- Fórmulas ---------------------------------------------------------------------------

ui.secao("Fórmulas")
st.markdown(
    "**Ranking de bairros** — para cada bairro *b* no recorte: `registros(b)` = número de chamados "
    "FINALIZADA com bairro casado a *b*; `% (b) = registros(b) / Σ registros com bairro identificado`. "
    "Ordem decrescente, top 15. A frase-título soma os 10 maiores. Contagem absoluta, **sem ajuste por "
    "área, população ou fluxo**.\n\n"
    "**Severidade** — o painel **não usa índice composto de severidade**. Mostra a composição: "
    "`% categoria no ano = chamados da categoria / chamados do ano`, para SEM VÍTIMA, COM VÍTIMA, "
    "VÍTIMA FATAL e não informado. Chamados com vítima fatal = contagem da severidade “VÍTIMA FATAL”; "
    "a soma de `vitimasfatais` não é usada porque, antes de 2021, célula vazia é desconhecida.")
with st.expander("Outras contas do painel"):
    st.markdown(
        "- **Série mensal**: pela data do registro; meses sem registro valem 0 dentro do intervalo; "
        "datas de outro ano ficam fora.\n"
        "- **Hora × dia**: hora do registro (0–23) e dia da semana da data; registros sem hora ficam "
        "fora e são contados na nota.\n"
        "- **Percentuais** nunca arredondam para 100% um valor menor que 100, nem para 0% um valor "
        "maior que 0.")

# --- Classificadores ---------------------------------------------------------------------

ui.secao("Método dos classificadores")
if meta is None:
    st.info("Artefatos da previsão não encontrados: rode python src/classificacao/gerar_artefatos.py")
else:
    p = art["particoes"].set_index("particao")
    st.markdown(
        f"**Unidade**: bairro-mês ({meta['n_bairros']} bairros oficiais). **Alvo**: "
        f"{meta['classe_positiva'].lower()} (corte = teto do percentil 75 do treino). "
        f"**Partições temporais**: treino {meta['treino']}, validação {meta['validacao']}, "
        f"teste {meta['teste']}. **Modelos**: majoritária, persistência, regressão logística e árvore "
        f"de decisão. **Seleção**: {meta['limiar_selecao'].lower()} Modelo escolhido: "
        f"regressão logística, limiar {str(meta['limiares']['logistica']).replace('.', ',')}.")
    with st.expander("Preditores, hiperparâmetros e verificações"):
        st.markdown(
            f"- **Preditores** (só passado): {', '.join(meta['num_features'])} e o bairro (one-hot). "
            "Nenhum usa o mês previsto.\n"
            f"- **Passo**: {meta['passo_previsao']}\n"
            f"- **Treino**: {meta['treinamento']}\n"
            f"- **Hiperparâmetros**: logística C={meta['hiperparametros']['logistica']['C']}, "
            f"max_iter={meta['hiperparametros']['logistica']['max_iter']}; árvore "
            f"max_depth={meta['hiperparametros']['arvore']['max_depth']}, "
            f"min_samples_leaf={meta['hiperparametros']['arvore']['min_samples_leaf']}; semente {meta['seed']}.\n"
            f"- **Scores**: {meta['observacao_score']}\n"
            f"- **Prevalência**: treino {dp.fmt_pct(p.loc['treino', 'prevalencia'] * 100)}, validação "
            f"{dp.fmt_pct(p.loc['validacao', 'prevalencia'] * 100)}, teste "
            f"{dp.fmt_pct(p.loc['teste', 'prevalencia'] * 100)}.\n"
            f"- **Incerteza**: IC 95% exploratório por bootstrap com blocos mensais "
            f"({dp.fmt_int(art['ic']['repeticoes_validas'].max())} repetições válidas).\n"
            "- **Verificações automáticas**: lag1 = mês anterior do mesmo bairro; partições sem "
            "sobreposição; nenhum bairro-mês repetido; matriz soma n. A regeneração a partir de "
            "`data/raw/` reproduz a avaliação entregue (teste de regressão).")

# --- Visual e reprodução --------------------------------------------------------------

ui.secao("Visual e reprodução")
pares = [(t.TEXTO, t.FUNDO), (t.TEXTO_2, t.FUNDO), (t.TEXTO, t.LATERAL), (t.TEXTO_2, t.LATERAL),
         (t.BRANCO, t.DESTAQUE), (t.BRANCO, t.ESCURO), (t.TEXTO, t.CINZA_MARCA)] + \
        [(t.texto_sobre(c), c) for c in t.RAMPA]
menor = min(t.contraste(a, b) for a, b in pares)
st.markdown(f"Menor contraste de texto do painel: **{menor:.2f}:1** (WCAG AA pede 4,5:1). "
            "Uma cor de destaque (azul) para a série principal; azul/laranja só para acerto/erro na "
            "previsão. Decisões completas em `docs/entregas/E6_dashboard_consolidado.md`.")
with st.expander("Como reproduzir"):
    st.code("pip install -r requirements.txt\n"
            "python src/transform_sinistros.py              # silver (pontos críticos)\n"
            "python src/baixa_malha_bairros.py              # malha e cadastro de bairros\n"
            "python src/classificacao/gerar_artefatos.py    # artefatos da previsão\n"
            "streamlit run app/dashboard.py", language="powershell")
