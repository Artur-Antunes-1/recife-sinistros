"""
dashboard.py
------------
Ponto de entrada do dashboard (E4, consolidado no E6) sobre os chamados de
sinistro de trânsito da CTTU, Recife, 2015-2024. Um único painel com três
páginas:

  Pontos críticos              silver, só FINALIZADA (ADR-005, ADR-016)
  Previsão de volume elevado   classificadores, todos os status (ADR-017)
  Metodologia                  fonte, filtros, fórmulas e método (TRN-01)

Este arquivo só monta o que é comum: estilo, rodapé, filtros da barra lateral
(desenhados em toda página para o estado sobreviver à troca de página) e a
navegação. Nada é treinado aqui: a página de previsão lê artefatos
pré-calculados em data/classificacao/.

Rodar a partir da raiz do repositório:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados_painel as dp  # noqa: E402
import estado  # noqa: E402
import ui  # noqa: E402

st.set_page_config(page_title="Sinistros de trânsito — Recife",
                   layout="wide", initial_sidebar_state="auto")
ui.estilo()

df, _ = estado.silver()
if df is None:
    st.error("Não foi possível carregar a base do painel. Confira os arquivos em data/painel/ "
             "ou gere o silver local com: python src/transform_sinistros.py")
    st.stop()
if df.empty:
    st.error("A base do painel está vazia.")
    st.stop()

# --- Filtros (barra lateral, comuns a todas as páginas) --------------------------

ANO_MIN, ANO_MAX = int(df["ano"].min()), int(df["ano"].max())
OPCOES_BAIRRO = sorted(df["bairro_painel"].unique(),
                       key=lambda b: (b == dp.BAIRRO_NAO_INFORMADO, dp.normaliza_nome(b)))
st.session_state.setdefault("f_anos", (ANO_MIN, ANO_MAX))
st.session_state.setdefault("f_bairros", [])
st.session_state.setdefault("f_sev", list(dp.SEVERIDADES))


def _limpa_filtros():
    st.session_state["f_anos"] = (ANO_MIN, ANO_MAX)
    st.session_state["f_bairros"] = []
    st.session_state["f_sev"] = list(dp.SEVERIDADES)


paginas = [
    st.Page("paginas/pontos_criticos.py", title="Pontos críticos", default=True),
    st.Page("paginas/previsao.py", title="Previsão de volume elevado", url_path="previsao"),
    st.Page("paginas/metodologia.py", title="Metodologia", url_path="metodologia"),
]
pagina = st.navigation(paginas)
st.markdown('<p class="produto">Sinistros de trânsito no Recife · CTTU</p>', unsafe_allow_html=True)

with st.sidebar:
    ui.secao("Filtros")
    st.slider("Anos", ANO_MIN, ANO_MAX, key="f_anos")
    st.multiselect("Bairros (vazio = todos)", OPCOES_BAIRRO, key="f_bairros",
                   placeholder="Todos os bairros")
    st.multiselect("Severidade", dp.SEVERIDADES, key="f_sev", placeholder="Nenhuma selecionada")
    st.button("Limpar filtros", on_click=_limpa_filtros, width="stretch")
    anos, bairros, sevs = estado.filtros()
    n = len(dp.aplica_filtros(df, anos, bairros, sevs))
    st.markdown(f'<div class="secao" style="margin-top:24px">Recorte dos pontos críticos</div>'
                f'<div class="contador">{dp.fmt_int(n)}</div>'
                f'<div class="contador-r">registros FINALIZADA de {dp.fmt_int(len(df))} '
                f'({dp.fmt_pct(n / len(df) * 100)})</div>', unsafe_allow_html=True)
    st.caption("Cada página diz, no topo, quais destes filtros se aplicam a ela.")

pagina.run()
estado.rodape()  # se a página parar antes (recorte vazio), ela mesma desenha o rodapé
