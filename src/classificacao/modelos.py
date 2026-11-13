"""
modelos.py
----------
Painel bairro-mês, treino dos quatro modelos, métricas e artefatos para o
dashboard. Porta fiel de painel_mensal() e treinar() de
entrega_classificadores/classificacao_cttu.py (ADR-017).

FIXADO (não mudar sem nova avaliação e novo ADR):
  - alvo: bairro-mês com >= corte chamados, corte = teto do p75 do treino (= 3)
  - partições: treino 2021-07..2022-12, validação 2023, teste 2024
  - limiar escolhido SÓ na validação (maior F1; desempate por recall, depois
    maior limiar); modelo escolhido pelo F1 de validação entre logística e
    árvore -> regressão logística, limiar 0,16
  - treino só até dez/2022; o modelo não é reajustado em 2023 nem em 2024

As figuras PNG do ZIP não são regeradas: o dashboard desenha os gráficos a
partir dos artefatos (tabelas), com a paleta do painel.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_recall_curve, precision_score,
                             recall_score, roc_auc_score, roc_curve)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

NUM = ["lag1", "lag2", "lag3", "lag6", "media3", "media6", "dp6", "tendencia", "mes_sin", "mes_cos"]
NOMES = {"dummy": "Majoritária", "persistencia": "Persistência",
         "logistica": "Regressão logística", "arvore": "Árvore de decisão"}
MODELOS = list(NOMES)
SEMENTE = 42


def metricas(y, score, limiar: float) -> dict:
    """Métricas de classificação com o limiar dado. tn+fp+fn+tp == n sempre."""
    pred = np.asarray(score) >= limiar
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return dict(acuracia=accuracy_score(y, pred), precisao=precision_score(y, pred, zero_division=0),
                recall=recall_score(y, pred, zero_division=0), f1=f1_score(y, pred, zero_division=0),
                acuracia_balanceada=balanced_accuracy_score(y, pred), roc_auc=roc_auc_score(y, score),
                average_precision=average_precision_score(y, score),
                tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                n=len(y), positivos=int(np.sum(y)), limiar=float(limiar))


def painel_mensal(base: pd.DataFrame, bairros: list[str]) -> tuple[pd.DataFrame, int]:
    """Contagem de chamados por bairro oficial e mês (2021-01..2024-12), com
    preditores só do passado (lags, médias móveis) e o alvo binário.

    Entram só chamados com data E bairro válidos — todos os status. Mês sem
    chamado num bairro vale 0 (contagem, não lacuna)."""
    v = base.loc[base["data_valida"] & base["bairro_validado"]].copy()
    v["periodo"] = v["data_dt"].dt.to_period("M").astype(str)
    idx = pd.MultiIndex.from_product(
        [bairros, pd.period_range("2021-01", "2024-12", freq="M").astype(str)],
        names=["bairro", "periodo"])
    c = v.groupby(["bairro_chave", "periodo"]).size()
    c.index = c.index.set_names(["bairro", "periodo"])
    painel = (c.reindex(idx, fill_value=0).rename("chamados").reset_index()
                .sort_values(["bairro", "periodo"]))
    # Mês inteiro sem nenhum chamado na cidade = falha de cobertura, não "zeros".
    assert painel.groupby("periodo")["chamados"].sum().gt(0).all(), "Há mês inteiro sem dados"
    g = painel.groupby("bairro", sort=False)
    for k in [1, 2, 3, 6]:
        painel[f"lag{k}"] = g["chamados"].shift(k)
    for k in [3, 6]:
        painel[f"media{k}"] = g["chamados"].transform(lambda x: x.shift(1).rolling(k).mean())
    painel["dp6"] = g["chamados"].transform(lambda x: x.shift(1).rolling(6).std(ddof=0))
    painel["tendencia"] = painel["lag1"] - painel["lag3"]
    mes = painel["periodo"].str[-2:].astype(int)
    painel["mes_sin"] = np.sin(2 * np.pi * mes / 12)
    painel["mes_cos"] = np.cos(2 * np.pi * mes / 12)
    painel = painel.dropna(subset=NUM).copy()  # jan-jun/2021 não têm 6 meses de histórico
    painel["particao"] = np.select([painel["periodo"].le("2022-12"), painel["periodo"].le("2023-12")],
                                   ["treino", "validacao"], default="teste")
    treino = painel.loc[painel["particao"].eq("treino")]
    corte = max(1, int(np.ceil(treino["chamados"].quantile(.75))))
    painel["alvo"] = (painel["chamados"] >= corte).astype(int)
    # Verificações do script original: lag1 = mês anterior; partições em ordem; sem chave repetida.
    hist = c.to_dict()
    assert all(r.lag1 == hist.get((r.bairro, str(pd.Period(r.periodo) - 1)), 0)
               for r in painel.itertuples())
    p = painel.groupby("particao")["periodo"]
    assert p.max()["treino"] < p.min()["validacao"] and p.max()["validacao"] < p.min()["teste"]
    assert not painel.duplicated(["bairro", "periodo"]).any()
    return painel, corte


def _pipelines() -> dict:
    def onehot():
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    return {
        "dummy": Pipeline([("pre", ColumnTransformer([("numericas", StandardScaler(), NUM),
                                                      ("bairro", onehot(), ["bairro"])])),
                           ("modelo", DummyClassifier(strategy="prior"))]),
        "logistica": Pipeline([("pre", ColumnTransformer([("numericas", StandardScaler(), NUM),
                                                          ("bairro", onehot(), ["bairro"])])),
                               ("modelo", LogisticRegression(C=1, max_iter=2000, random_state=SEMENTE))]),
        "arvore": Pipeline([("pre", ColumnTransformer([("numericas", "passthrough", NUM),
                                                       ("bairro", onehot(), ["bairro"])])),
                            ("modelo", DecisionTreeClassifier(max_depth=4, min_samples_leaf=30,
                                                              random_state=SEMENTE))]),
    }


def treinar(painel: pd.DataFrame, corte: int) -> dict:
    """Treina, escolhe limiares na validação, avalia no teste. Devolve um dict
    de tabelas (DataFrames) e o dict de metodologia — sem gravar nada."""
    treino = painel[painel["particao"].eq("treino")]
    val = painel[painel["particao"].eq("validacao")]
    teste = painel[painel["particao"].eq("teste")]
    pipes = _pipelines()
    scores, limiares, linhas_limiar = {}, {}, []
    for nome in MODELOS:
        if nome == "persistencia":
            # Índice monotônico do mês anterior, não probabilidade.
            sv = val["lag1"].to_numpy() / (val["lag1"].to_numpy() + corte)
            st = teste["lag1"].to_numpy() / (teste["lag1"].to_numpy() + corte)
        else:
            pipes[nome].fit(treino[NUM + ["bairro"]], treino["alvo"])
            sv = pipes[nome].predict_proba(val[NUM + ["bairro"]])[:, 1]
            st = pipes[nome].predict_proba(teste[NUM + ["bairro"]])[:, 1]
        scores[nome] = {"validacao": sv, "teste": st}
        opcoes = np.round(np.arange(.05, .951, .01), 2) if nome in ["logistica", "arvore"] else [.5]
        cand = []
        for lim in opcoes:
            z = {"modelo": nome, "nome": NOMES[nome], **metricas(val["alvo"], sv, lim)}
            linhas_limiar.append(z)
            cand.append(z)
        melhor = sorted(cand, key=lambda z: (z["f1"], z["recall"], z["limiar"]), reverse=True)[0]
        limiares[nome] = melhor["limiar"]

    linhas, preds = [], []
    for nome in MODELOS:
        for part, d in [("validacao", val), ("teste", teste)]:
            s = scores[nome][part]
            linhas.append({"modelo": nome, "nome": NOMES[nome], "particao": part,
                           **metricas(d["alvo"], s, limiares[nome])})
            z = d[["bairro", "periodo", "particao", "chamados", "alvo", "lag1", "media3", "media6"]].copy()
            z["modelo"], z["score"], z["limiar"] = nome, s, limiares[nome]
            z["predito"] = (s >= limiares[nome]).astype(int)
            preds.append(z)
    met = pd.DataFrame(linhas)
    vencedor = (met[met["particao"].eq("validacao") & met["modelo"].isin(["logistica", "arvore"])]
                .sort_values(["f1", "recall", "nome"], ascending=[False, False, True]).iloc[0]["modelo"])
    preds = pd.concat(preds, ignore_index=True)
    teste_preds = preds[preds["particao"].eq("teste")]

    curvas = []
    for nome, g in teste_preds.groupby("modelo"):
        fpr, tpr, _ = roc_curve(g["alvo"], g["score"])
        curvas += [{"modelo": nome, "curva": "roc", "x": x, "y": y} for x, y in zip(fpr, tpr)]
        p, r, _ = precision_recall_curve(g["alvo"], g["score"])
        curvas += [{"modelo": nome, "curva": "pr", "x": x, "y": y} for x, y in zip(r, p)]

    mensal = [{"modelo": nome, "periodo": per, **metricas(g["alvo"], g["score"], limiares[nome])}
              for (nome, per), g in teste_preds.groupby(["modelo", "periodo"])]

    part = painel.groupby("particao").agg(n=("alvo", "size"), positivos=("alvo", "sum"),
                                         inicio=("periodo", "min"), fim=("periodo", "max"))
    part["prevalencia"] = part["positivos"] / part["n"]

    meta = {
        "classe_positiva": f"Bairro-mês com pelo menos {corte} chamados datados e com bairro validado",
        "corte_contagem": corte, "quantil_treino": .75, "modelo_selecionado": vencedor,
        "limiares": limiares,
        "hiperparametros": {"logistica": {"C": 1, "max_iter": 2000},
                            "arvore": {"max_depth": 4, "min_samples_leaf": 30}},
        "treino": "2021-07 a 2022-12", "validacao": "2023-01 a 2023-12", "teste": "2024-01 a 2024-12",
        "passo_previsao": "Ao fim de t-1, prever o bairro-mês t; avaliação sequencial de um passo "
                          "com histórico observado.",
        "treinamento": "Treino somente até dez/2022; não reajustado em 2023 ou 2024.",
        "limiar_selecao": "F1 em validação 2023; desempate por recall, depois maior limiar.",
        "observacao_score": "Scores não calibrados; persistência é índice monotônico, não probabilidade.",
        "bairro_meses": int(len(painel)), "n_bairros": int(painel["bairro"].nunique()),
        "num_features": NUM, "seed": SEMENTE,
        # Data do snapshot da entrega (manifesto_aquisicao.json). Os CSVs de
        # data/raw/ são byte a byte iguais a ele (SHA-256 conferido, ADR-017).
        "data_obtencao": "2026-11-04",
    }
    return {"metricas": met, "predicoes_teste": teste_preds.reset_index(drop=True),
            "curvas_teste": pd.DataFrame(curvas), "metricas_mensais_teste": pd.DataFrame(mensal),
            "limiares_validacao": pd.DataFrame(linhas_limiar), "particoes": part.reset_index(),
            "intervalos_bootstrap_mensal": bootstrap_mensal(teste_preds, limiares),
            "metodologia": meta}


def bootstrap_mensal(teste_preds: pd.DataFrame, limiares: dict, repeticoes: int = 1000) -> pd.DataFrame:
    """IC 95% exploratório por bootstrap em blocos de mês (12 blocos): mantém a
    dependência entre bairros do mesmo mês. Mesma semente e ordem do ZIP."""
    rng = np.random.default_rng(SEMENTE)
    saida = []
    for nome in MODELOS:
        z = teste_preds[teste_preds["modelo"].eq(nome)]
        grupos = [g for _, g in z.groupby("periodo")]
        vals = []
        for _ in range(repeticoes):
            amostra = pd.concat([grupos[k] for k in rng.integers(0, len(grupos), len(grupos))],
                                ignore_index=True)
            y, s = amostra["alvo"].to_numpy(), amostra["score"].to_numpy()
            p = s >= limiares[nome]
            if len(np.unique(y)) < 2:
                continue
            vals.append([f1_score(y, p, zero_division=0), recall_score(y, p, zero_division=0),
                         precision_score(y, p, zero_division=0), roc_auc_score(y, s),
                         average_precision_score(y, s)])
        arr = np.asarray(vals)
        for j, m in enumerate(["f1", "recall", "precisao", "roc_auc", "average_precision"]):
            lo, hi = np.quantile(arr[:, j], [.025, .975])
            saida.append({"modelo": nome, "metrica": m, "ic95_inferior": lo, "ic95_superior": hi,
                          "repeticoes_validas": len(arr),
                          "unidade_bootstrap": "mês; 12 blocos, aproximação exploratória"})
    return pd.DataFrame(saida)


def gravar(tabelas: dict, extras: dict, pasta: Path) -> list[Path]:
    """Grava cada tabela como CSV e a metodologia + cobertura como JSON."""
    pasta.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nome, t in tabelas.items():
        if nome == "metodologia":
            continue
        caminho = pasta / f"{nome}.csv"
        t.to_csv(caminho, index=False, encoding="utf-8", lineterminator="\n")
        escritos.append(caminho)
    for nome, obj in [("metodologia", tabelas["metodologia"]), *extras.items()]:
        caminho = pasta / f"{nome}.json"
        caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False),
                           encoding="utf-8", newline="\n")
        escritos.append(caminho)
    return escritos
