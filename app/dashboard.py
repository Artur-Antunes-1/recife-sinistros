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

URL_RELATORIO = ("https://github.com/mbvo1/recife-sinistros/blob/master/"
                 "docs/relatorio_qualidade_silver.md")

st.set_page_config(page_title="Sinistros de trânsito — Recife",
                   layout="wide", initial_sidebar_state="expanded")
ui.estilo()

df, _ = estado.silver()
if df is None:
    st.error("Silver não encontrado em data/silver/sinistros_consolidado.csv. "
             "Gere com: python src/transform_sinistros.py")
    st.stop()
art = estado.artefatos_previsao()

# --- Rodapé fixo (renderizado cedo: aparece mesmo com recorte vazio) ---------

_ok = df.loc[~df["data_fora_do_ano"], "data"]
_baixado, _gerado = dp.data_download_raw(), dp.data_arquivo(dp.CAMINHO_SILVER)
_extracao = (f"<b>Extração:</b> CSVs baixados em {_baixado:%d/%m/%Y} · silver gerado em "
             f"{_gerado:%d/%m/%Y}. " if _baixado is not None and _gerado is not None else "")
_total_prev = (f" · {dp.fmt_int(art['cobertura']['registros'])} chamados de todos os status na "
               f"previsão" if art else "")
st.markdown(
    f"""<div class="rodape">
    <b>Fonte:</b> CTTU — Portal de Dados Abertos do Recife, chamados de sinistro de trânsito
    (ODbL); malha e cadastro de bairros: dataset “Área urbana” (ODbL).
    <b>Período:</b> {ui.mes_ano(_ok.min())} a {ui.mes_ano(_ok.max())}. {_extracao}
    <b>Total:</b> {dp.fmt_int(len(df))} registros FINALIZADA nos pontos críticos{_total_prev}.
    <a href="{URL_RELATORIO}" target="_blank">Relatório de qualidade do silver</a>
    </div>""", unsafe_allow_html=True)

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
