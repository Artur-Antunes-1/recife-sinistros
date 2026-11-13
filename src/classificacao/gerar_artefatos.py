"""
gerar_artefatos.py
------------------
Roda a avaliação dos classificadores sobre data/raw/ e grava em
data/classificacao/ os artefatos que o dashboard lê. O dashboard NUNCA treina
nada: só lê estes arquivos.

Artefatos (versionados, como docs/relatorio_qualidade_silver.md — são o
resultado oficial que o painel e os docs citam):
    metricas.csv                 4 modelos x {validação, teste}
    predicoes_teste.csv          score e predição por bairro-mês de 2024
    curvas_teste.csv             pontos das curvas ROC e precision-recall
    metricas_mensais_teste.csv   métricas por mês de 2024
    limiares_validacao.csv       métricas de cada limiar candidato em 2023
    particoes.csv                n, positivos e prevalência por partição
    intervalos_bootstrap_mensal.csv  IC 95% exploratório (blocos de mês)
    qualidade_por_ano.csv        cobertura da base dos classificadores
    metodologia.json, cobertura.json

Rodar a partir da raiz do repositório (precisa de scikit-learn):
    python src/classificacao/gerar_artefatos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classificacao import modelos, preparacao  # noqa: E402

DESTINO = preparacao.RAIZ / "data" / "classificacao"


def cobertura(base, qualidade, painel, corte) -> dict:
    """Números do selo de cobertura da página de previsão, calculados aqui
    para o painel não ter de recalcular nem citar de memória."""
    q = qualidade.set_index("ano")
    janela = base["ano_origem"].between(2021, 2024)
    alvo = base["data_valida"] & base["bairro_validado"]
    sem_fatal = q.loc[q["vitimasfatais_conhecidas"].eq(0)].index.tolist()
    return {
        "registros": int(len(base)),
        "status": "todos os status (inclui CANCELADA, DUPLICIDADE etc.)",
        "finalizada": int(q["finalizada"].sum()),
        "anos": [int(q.index.min()), int(q.index.max())],
        "janela_modelo_anos": [2021, 2024],
        "registros_janela_modelo": int(janela.sum()),
        "registros_no_alvo": int((janela & alvo).sum()),
        "registros_janela_bairro_nao_validado": int((janela & ~base["bairro_validado"]).sum()),
        "registros_janela_data_invalida": int((janela & ~base["data_valida"]).sum()),
        "bairro_meses": int(len(painel)),
        "corte_contagem": int(corte),
        "primeira_data_2015": q.loc[2015, "primeira_data"],
        "ultima_data_2024": q.loc[2024, "ultima_data"],
        "datas_outro_ano_2024": int(q.loc[2024, "datas_outro_ano"]),
        "horas_validas_2022": int(q.loc[2022, "horas_validas"]),
        "anos_sem_vitimasfatais_conhecidas": [int(a) for a in sem_fatal],
        "primeiro_ano_vitimasfatais_completas": int(
            q.index[q["vitimasfatais_conhecidas"].eq(q["registros"])].min()),
    }


def main(destino: Path = DESTINO) -> dict:
    base = preparacao.preparar()
    bairros = preparacao.bairros_oficiais()
    qualidade = preparacao.qualidade_por_ano(base)
    painel, corte = modelos.painel_mensal(base, bairros)
    tabelas = modelos.treinar(painel, corte)
    tabelas["qualidade_por_ano"] = qualidade
    extras = {"cobertura": cobertura(base, qualidade, painel, corte)}
    for caminho in modelos.gravar(tabelas, extras, destino):
        print("gravado", caminho)
    t = tabelas["metricas"]
    print(t[t["particao"].eq("teste")][["nome", "acuracia", "precisao", "recall", "f1",
                                        "roc_auc", "average_precision", "tn", "fp", "fn", "tp"]]
          .to_string(index=False))
    return tabelas


if __name__ == "__main__":
    main()
