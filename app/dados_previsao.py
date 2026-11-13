"""
dados_previsao.py
-----------------
Camada de dados da página "Previsão de volume elevado". Só LÊ os artefatos de
data/classificacao/ (gerados por src/classificacao/gerar_artefatos.py) —
nada é treinado no dashboard (ADR-017).

O limiar exploratório recalcula a matriz de confusão a partir das predições
de 2024 já gravadas; ele NUNCA altera a tabela oficial (metricas.csv), que é
lida tal como foi gravada.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "data" / "classificacao"
NOMES = {"dummy": "Majoritária", "persistencia": "Persistência",
         "logistica": "Regressão logística", "arvore": "Árvore de decisão"}
ORDEM = ["dummy", "persistencia", "logistica", "arvore"]
# Rótulos das quatro células da matriz, na linguagem da página.
CATEGORIAS = {"VP": "acerto: volume elevado previsto",
              "VN": "acerto: volume regular previsto",
              "FP": "alerta falso",
              "FN": "omissão (elevado não previsto)"}


def carrega_artefatos(pasta: Path = PASTA) -> dict | None:
    """Lê os artefatos. None se a pasta não existir (o painel avisa)."""
    if not (pasta / "metricas.csv").exists():
        return None
    ler = lambda n: pd.read_csv(pasta / n, encoding="utf-8-sig")  # noqa: E731
    return {
        "metricas": ler("metricas.csv"),
        "predicoes": ler("predicoes_teste.csv"),
        "curvas": ler("curvas_teste.csv"),
        "mensal": ler("metricas_mensais_teste.csv"),
        "particoes": ler("particoes.csv"),
        "ic": ler("intervalos_bootstrap_mensal.csv"),
        "qualidade": ler("qualidade_por_ano.csv"),
        "meta": json.loads((pasta / "metodologia.json").read_text(encoding="utf-8")),
        "cobertura": json.loads((pasta / "cobertura.json").read_text(encoding="utf-8")),
    }


def oficial(art: dict, modelo: str, particao: str = "teste") -> pd.Series:
    m = art["metricas"]
    return m[(m["modelo"] == modelo) & (m["particao"] == particao)].iloc[0]


def matriz_no_limiar(pred: pd.DataFrame, limiar: float) -> dict:
    """Matriz de confusão e precisão/recall com outro limiar (exploração)."""
    p = pred["score"].to_numpy() >= limiar
    y = pred["alvo"].to_numpy() == 1
    vp, fp = int((p & y).sum()), int((p & ~y).sum())
    fn, vn = int((~p & y).sum()), int((~p & ~y).sum())
    prec = vp / (vp + fp) if vp + fp else 0.0
    rec = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"limiar": limiar, "VP": vp, "FP": fp, "FN": fn, "VN": vn, "n": len(pred),
            "precisao": prec, "recall": rec, "f1": f1}


def curva_limiares(pred: pd.DataFrame, passos=None) -> pd.DataFrame:
    """Alertas falsos e omissões para cada limiar candidato (0,05 a 0,95)."""
    passos = np.round(np.arange(.05, .951, .01), 2) if passos is None else passos
    return pd.DataFrame([matriz_no_limiar(pred, float(x)) for x in passos])


def categoria(pred: pd.DataFrame) -> pd.Series:
    """VP/FP/FN/VN de cada bairro-mês, com a predição oficial gravada."""
    a, p = pred["alvo"] == 1, pred["predito"] == 1
    return pd.Series(np.select([a & p, ~a & p, a & ~p], ["VP", "FP", "FN"], "VN"), index=pred.index)


def chaves_do_filtro(df_silver: pd.DataFrame | None, bairros_painel: list[str]) -> set[str] | None:
    """Traduz o filtro de bairro do painel (nomes de exibição) para as chaves
    do cadastro usadas pelos classificadores. None = sem filtro (todos).

    A chave da malha (ADR-016) e a do cadastro coincidem para os 94 bairros
    oficiais. Nomes fora do cadastro (NÃO INFORMADO, Setúbal...) não têm chave
    e não têm previsão."""
    if not bairros_painel:
        return None
    if df_silver is None:
        return set()
    m = df_silver[df_silver["bairro_painel"].isin(bairros_painel)]
    return set(m["bairro_chave"].dropna().unique())
