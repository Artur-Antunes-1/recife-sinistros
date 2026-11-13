"""
Confere os números de docs/entregas/E6_dashboard_consolidado.md e do ADR-017
contra a saída do código. Cada número citado nos docs é recalculado aqui a
partir do silver, dos artefatos ou de data/raw/ e precisa aparecer no texto
exatamente como o painel o formata.

Se um destes testes falhar, ou o dado mudou, ou o doc afirma algo que o código
não sustenta — corrigir o doc, nunca o teste.
"""

from pathlib import Path

import pytest

import dados_painel as dp
import dados_previsao as dprev
import tema

RAIZ = Path(__file__).resolve().parent.parent
DOC = (RAIZ / "docs" / "entregas" / "E6_dashboard_consolidado.md").read_text(encoding="utf-8")
ADR = (RAIZ / "docs" / "decisions.md").read_text(encoding="utf-8").split("ADR-017")[1]

requer_silver = pytest.mark.skipif(not dp.CAMINHO_SILVER.exists(), reason="silver não gerado")
f3 = lambda v: f"{v:.3f}".replace(".", ",")  # noqa: E731


def _numeros_painel() -> dict[str, str]:
    malha = dp.carrega_malha()
    df, _ = dp.casa_bairros(dp.carrega_silver(),
                            {f["properties"]["chave"] for f in malha["features"]} if malha else None)
    k, top = dp.concentracao_top(df, 10)
    r = dp.ranking_bairros(df, 15).iloc[0]
    hd, _ = dp.hora_dia(df)
    d, h = hd.stack().idxmax()
    s = df.groupby("ano").size()
    sv = dp.severidade_por_ano(df)
    pr = sv.div(sv.sum(axis=1), axis=0) * 100
    return {
        "total silver": dp.fmt_int(len(df)),
        "top-10": dp.fmt_pct(top),
        "líder %": dp.fmt_pct(r["pct"]),
        "líder n": dp.fmt_int(r["registros"]),
        "pico hora": f"às **{h}h** ({dp.fmt_int(hd.values.max())} chamados)",
        "pico dia": f"{'terça' if dp.DIAS_SEMANA[d] == 'Ter' else dp.DIAS_SEMANA[d]}",
        "7-19h": dp.fmt_pct(hd.loc[:, 7:18].values.sum() / hd.values.sum() * 100, 0),
        "silver 2019→2021": f"{dp.fmt_int(s[2019])} a {dp.fmt_int(s[2021])}",
        "queda %": f"−{dp.fmt_pct((1 - s[2021] / s[2019]) * 100, 0)}",
        "SEM 2019→2021": f"{dp.fmt_int(sv.loc[2019, 'SEM VÍTIMA'])} → {dp.fmt_int(sv.loc[2021, 'SEM VÍTIMA'])}",
        "COM 2019→2021": f"{dp.fmt_int(sv.loc[2019, 'COM VÍTIMA'])} → {dp.fmt_int(sv.loc[2021, 'COM VÍTIMA'])}",
        "COM% 2019": f"{dp.fmt_pct(pr.loc[2019, 'COM VÍTIMA'], 0)} (2019)",
        "COM% 2024": f"{dp.fmt_pct(pr.loc[2024, 'COM VÍTIMA'], 0)} (2024)",
        "fora do mapa": f"{dp.cobertura_geo(df)['fora']} chamados FINALIZADA ficam fora do mapa",
    }


def _numeros_previsao() -> dict[str, str]:
    a = dprev.carrega_artefatos()
    lo, pe, ar = (dprev.oficial(a, m) for m in ["logistica", "persistencia", "arvore"])
    ic = a["ic"].set_index(["modelo", "metrica"])
    il, ip = ic.loc[("logistica", "f1")], ic.loc[("persistencia", "f1")]
    m = a["mensal"][a["mensal"]["modelo"] == "logistica"]
    mn, mx = m.loc[m["f1"].idxmin()], m.loc[m["f1"].idxmax()]
    mes = lambda p: f"{['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'][int(p[-2:]) - 1]}/{p[:4]}"  # noqa: E731
    cob = a["cobertura"]
    return {
        "recall": dp.fmt_pct(lo["recall"] * 100),
        "F1": f3(lo["f1"]), "F1 persistência": f3(pe["f1"]), "F1 árvore": f3(ar["f1"]),
        "omissões a menos": f"{pe['fn'] - lo['fn']} omissões a menos",
        "alertas a mais": f"{lo['fp'] - pe['fp']} alertas falsos a mais",
        "IC logística": f"{f3(il['ic95_inferior'])}–{f3(il['ic95_superior'])}",
        "IC persistência": f"{f3(ip['ic95_inferior'])}–{f3(ip['ic95_superior'])}",
        "F1 mensal mín": f"{f3(mn['f1'])} ({mes(mn['periodo'])})",
        "F1 mensal máx": f"{f3(mx['f1'])} ({mes(mx['periodo'])})",
        "prevalência teste": dp.fmt_pct(a["particoes"].set_index("particao").loc["teste", "prevalencia"] * 100),
        "limiar": str(a["meta"]["limiares"]["logistica"]).replace(".", ","),
        "no alvo": dp.fmt_int(cob["registros_no_alvo"]),
        "base": dp.fmt_int(cob["registros"]),
        "última data 2024": f"{cob['ultima_data_2024'][8:10]}/{cob['ultima_data_2024'][5:7]}/2024",
        "datas outro ano": f"{cob['datas_outro_ano_2024']} datas de outro ano",
    }


@requer_silver
def test_numeros_do_painel_citados_no_doc_e6():
    faltam = {k: v for k, v in _numeros_painel().items() if v not in DOC}
    assert not faltam, faltam


def test_numeros_da_previsao_citados_no_doc_e6():
    faltam = {k: v for k, v in _numeros_previsao().items() if v not in DOC}
    assert not faltam, faltam


def test_contraste_citado_e_o_calculado():
    pares = [(tema.TEXTO, tema.FUNDO), (tema.TEXTO_2, tema.FUNDO), (tema.TEXTO, tema.LATERAL),
             (tema.TEXTO_2, tema.LATERAL), (tema.TEXTO, tema.GRADE), (tema.TEXTO_2, tema.GRADE),
             (tema.BRANCO, tema.DESTAQUE), (tema.BRANCO, tema.ESCURO), (tema.TEXTO, tema.CINZA_MARCA)] \
        + [(tema.texto_sobre(c), c) for c in tema.RAMPA] \
        + [(tema.texto_sobre(c), c) for c in tema.CORES_RESULTADO.values()]
    menor = min(tema.contraste(a, b) for a, b in pares)
    assert f"{menor:.2f}:1".replace(".", ",") in DOC
    assert f"({tema.contraste(tema.TEXTO, tema.FUNDO):.1f}:1)".replace(".", ",") in DOC


def test_numeros_entregues_citados_no_adr_017():
    lo = dprev.oficial(dprev.carrega_artefatos(), "logistica")
    for v in ["84,4%", "77,9%", "92,3%", f"F1 {f3(lo['f1'])}", "473-136-40-479",
              f"{lo['tn']}/{lo['fp']}/{lo['fn']}/{lo['tp']}"]:
        assert v in ADR, v


def _tem_raw():
    from classificacao import preparacao
    try:
        preparacao.arquivos_por_ano()
        return preparacao.CAMINHO_CADASTRO.exists()
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not _tem_raw(), reason="precisa de data/raw/ e do cadastro")
def test_contagens_por_status_citadas_no_doc_e_no_adr():
    from classificacao import preparacao
    b = preparacao.preparar()
    st = b["situacao_chave"].value_counts()
    janela = b["ano_origem"].between(2021, 2024)
    for v in [dp.fmt_int(len(b)), dp.fmt_int(st["FINALIZADA"]), dp.fmt_int(st["CANCELADA"]),
              dp.fmt_int(st["DUPLICIDADE"]), dp.fmt_int(int(janela.sum()))]:
        assert v in ADR, v
    assert f"{dp.fmt_int(st['CANCELADA'])} CANCELADA e {dp.fmt_int(st['DUPLICIDADE'])} DUPLICIDADE" in DOC
