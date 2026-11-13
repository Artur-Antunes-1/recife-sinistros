"""
Testes dos classificadores (src/classificacao/, ADR-017).

  - Regressão: os artefatos de data/classificacao/ reproduzem a avaliação
    entregue (números da entrega e tabelas de entrega_classificadores/).
  - Consistência: matriz de confusão soma n; predições batem com a matriz.
  - vitimasfatais vazio continua NA (desconhecido), nunca 0.
  - Regeneração completa a partir de data/raw/ (lento, ~1 min; pulado se faltar
    dado bruto, cadastro ou scikit-learn).

Rodar:  pytest -v
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from classificacao import preparacao

RAIZ = Path(__file__).resolve().parent.parent
ARTEFATOS = RAIZ / "data" / "classificacao"
ENTREGA = RAIZ / "entrega_classificadores" / "semana_1_classificadores" / "tabelas"


def _ler(nome, pasta=ARTEFATOS):
    return pd.read_csv(pasta / nome, encoding="utf-8-sig")


def _teste(modelo):
    m = _ler("metricas.csv")
    return m[(m["modelo"] == modelo) & (m["particao"] == "teste")].iloc[0]


# --- Regressão contra a entrega ---------------------------------------------

def test_logistica_reproduz_numeros_entregues():
    r = _teste("logistica")
    assert round(r["acuracia"] * 100, 1) == 84.4
    assert round(r["precisao"] * 100, 1) == 77.9
    assert round(r["recall"] * 100, 1) == 92.3
    assert round(r["f1"], 3) == 0.845
    assert round(r["roc_auc"], 3) == 0.945
    assert round(r["average_precision"], 3) == 0.940
    assert (r["tn"], r["fp"], r["fn"], r["tp"]) == (473, 136, 40, 479)


def test_selecao_fixada_logistica_016_e_particoes():
    meta = json.loads((ARTEFATOS / "metodologia.json").read_text(encoding="utf-8"))
    assert meta["modelo_selecionado"] == "logistica"
    assert meta["limiares"]["logistica"] == 0.16
    assert meta["corte_contagem"] == 3
    p = _ler("particoes.csv").set_index("particao")
    assert (p.loc["treino", "inicio"], p.loc["treino", "fim"]) == ("2021-07", "2022-12")
    assert (p.loc["validacao", "inicio"], p.loc["validacao", "fim"]) == ("2023-01", "2023-12")
    assert (p.loc["teste", "inicio"], p.loc["teste", "fim"]) == ("2024-01", "2024-12")


def test_persistencia_e_arvore_como_entregues():
    # A árvore tem F1 pontual maior no TESTE, mas a escolha foi na validação.
    assert round(_teste("persistencia")["f1"], 3) == 0.835
    assert _teste("arvore")["f1"] > _teste("logistica")["f1"]
    m = _ler("metricas.csv").set_index(["modelo", "particao"])
    assert m.loc[("logistica", "validacao"), "f1"] > m.loc[("arvore", "validacao"), "f1"]


@pytest.mark.skipif(not ENTREGA.exists(), reason="entrega_classificadores/ ausente")
@pytest.mark.parametrize("nosso, deles, chaves", [
    ("metricas.csv", "metricas.csv", ["modelo", "particao"]),
    ("metricas_mensais_teste.csv", "metricas_mensais_teste.csv", ["modelo", "periodo"]),
    ("limiares_validacao.csv", "limiares_validacao.csv", ["modelo", "limiar"]),
    ("intervalos_bootstrap_mensal.csv", "intervalos_bootstrap_mensal.csv", ["modelo", "metrica"]),
    ("particoes.csv", "particoes.csv", ["particao"]),
])
def test_artefatos_iguais_as_tabelas_da_entrega(nosso, deles, chaves):
    a = _ler(nosso).sort_values(chaves).reset_index(drop=True)
    z = _ler(deles, ENTREGA).sort_values(chaves).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[z.columns], z, check_dtype=False, atol=1e-9, rtol=0)


@pytest.mark.skipif(not ENTREGA.exists(), reason="entrega_classificadores/ ausente")
def test_predicoes_de_teste_iguais_as_da_entrega():
    z = _ler("predicoes.csv", ENTREGA)
    z = z[z["particao"] == "teste"].sort_values(["modelo", "bairro", "periodo"]).reset_index(drop=True)
    a = _ler("predicoes_teste.csv").sort_values(["modelo", "bairro", "periodo"]).reset_index(drop=True)
    assert (a["predito"] == z["predito"]).all() and (a["alvo"] == z["alvo"]).all()
    # Scores: só ruído de ponto flutuante entre versões do scikit-learn.
    assert np.abs(a["score"] - z["score"]).max() < 1e-9


# --- Consistência --------------------------------------------------------------

def test_matriz_de_confusao_soma_n_em_toda_linha():
    for t in [_ler("metricas.csv"), _ler("metricas_mensais_teste.csv")]:
        assert (t["tn"] + t["fp"] + t["fn"] + t["tp"] == t["n"]).all()


def test_predicoes_batem_com_a_matriz_oficial():
    p = _ler("predicoes_teste.csv")
    for modelo, g in p.groupby("modelo"):
        r = _teste(modelo)
        vp = int(((g["alvo"] == 1) & (g["predito"] == 1)).sum())
        fp = int(((g["alvo"] == 0) & (g["predito"] == 1)).sum())
        assert (vp, fp, len(g)) == (r["tp"], r["fp"], r["n"])


def test_cobertura_tem_as_lacunas_conhecidas():
    c = json.loads((ARTEFATOS / "cobertura.json").read_text(encoding="utf-8"))
    assert c["registros"] == 72255
    assert c["primeira_data_2015"] == "2015-06-01"
    assert c["ultima_data_2024"] == "2024-12-28"
    assert c["datas_outro_ano_2024"] == 36
    assert c["horas_validas_2022"] == 0
    assert c["primeiro_ano_vitimasfatais_completas"] == 2021


# --- vitimasfatais: vazio é desconhecido -----------------------------------------

def test_vitimasfatais_vazio_vira_na_nunca_zero(tmp_path):
    for ano in preparacao.ANOS:
        linhas = ["data;hora;bairro;situacao;vitimasfatais",
                  f"{ano}-03-01;08:00:00;BOA VIAGEM;FINALIZADA;",       # vazio
                  f"{ano}-03-02;09:00:00;BOA VIAGEM;CANCELADA;0",      # zero explícito
                  f"{ano}-03-03;10:00:00;PINA;FINALIZADA;2"]
        (tmp_path / f"acidentes-de-transito-{ano}.csv").write_text("\n".join(linhas), encoding="utf-8")
    cad = tmp_path / "bairros_oficiais.csv"
    cad.write_text('"Bairro";"rpa"\n"Boa Viagem";"6"\n"Pina";"6"\n', encoding="utf-8")
    base = preparacao.preparar(tmp_path, cad)
    v = base.loc[base["ano_origem"] == 2021, "vitimasfatais_n"].tolist()
    assert pd.isna(v[0]) and v[1] == 0 and v[2] == 2
    assert len(base) == 30  # todos os status ficam
    assert base["bairro_validado"].all()


# --- Regeneração completa (lenta) -------------------------------------------------

def _pode_regenerar():
    try:
        import sklearn  # noqa: F401
        preparacao.arquivos_por_ano()
        return preparacao.CAMINHO_CADASTRO.exists()
    except (ImportError, FileNotFoundError):
        return False


@pytest.mark.skipif(not _pode_regenerar(), reason="precisa de data/raw/, cadastro e scikit-learn")
def test_regenerar_a_partir_de_data_raw_reproduz_os_artefatos(tmp_path):
    from classificacao import gerar_artefatos
    gerar_artefatos.main(tmp_path)
    for nome, chaves in [("metricas.csv", ["modelo", "particao"]),
                         ("predicoes_teste.csv", ["modelo", "bairro", "periodo"]),
                         ("metricas_mensais_teste.csv", ["modelo", "periodo"])]:
        a = _ler(nome, tmp_path).sort_values(chaves).reset_index(drop=True)
        v = _ler(nome).sort_values(chaves).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, v, check_dtype=False, atol=1e-9, rtol=0)
    assert json.loads((tmp_path / "cobertura.json").read_text(encoding="utf-8")) == \
        json.loads((ARTEFATOS / "cobertura.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(not _pode_regenerar(), reason="precisa de data/raw/, cadastro e scikit-learn")
def test_alinhar_a_finalizada_mudaria_111_rotulos():
    """Número citado no ADR-017 (decisão do Passo 0, opção a): se o alvo
    contasse só FINALIZADA, 62 + 29 + 20 = 111 bairro-meses mudariam de classe.
    Recalculado aqui com a MESMA função do painel, para o número não ser de memória."""
    from classificacao import modelos
    base = preparacao.preparar()
    bairros = preparacao.bairros_oficiais()
    todos, corte_t = modelos.painel_mensal(base, bairros)
    fin, corte_f = modelos.painel_mensal(base[base["situacao_chave"] == "FINALIZADA"], bairros)
    assert corte_t == corte_f == 3
    m = todos.merge(fin, on=["bairro", "periodo"], suffixes=("", "_fin"))
    mudam = (m["alvo"] != m["alvo_fin"]).groupby(m["particao"]).sum().to_dict()
    assert mudam == {"treino": 62, "validacao": 29, "teste": 20}
