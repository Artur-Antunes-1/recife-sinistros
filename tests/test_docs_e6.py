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

requer_silver = pytest.mark.skipif(not dp.caminho_silver().is_file(),
                                   reason="base do painel (data/painel/) ou silver ausente")
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


@requer_silver
def test_errata_do_pico_835_para_833():
    """A errata do E6 (ADR-018): a regra antiga do mapa de calor contava as
    datas de outro ano e perdia 1 hora inválida. Recalcula as duas regras."""
    df = dp.carrega_silver()
    antiga = df[df["hora_int"].notna() & df["dia_semana"].notna()]
    m_antiga = (antiga.groupby([antiga["dia_semana"].astype(int), antiga["hora_int"].astype(int)])
                .size().unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0))
    m_nova, fora = dp.hora_dia(df)
    fora_ano = df[df["data_fora_do_ano"]]
    assert (m_antiga.iat[1, 8], m_nova.iat[1, 8]) == (835, 833)
    assert int(m_nova.values.sum()) + fora == len(df)
    errata = DOC.split("**Errata")[1].split("## Como rodar")[0]
    assert "835" in errata and "**833**" in errata
    assert f"contava {len(fora_ano)} chamados com data de outro ano" in errata
    assert f"dos quais {int(((fora_ano['dia_semana'] == 1) & (fora_ano['hora_int'] == 8)).sum())} caem" in errata
    # Hora fora de 0-23: nem na matriz nem no "fora". Só existe no silver: a base de
    # data/painel/ já neutraliza horários inválidos (fontes.json). O 835 saiu do silver.
    if not dp.CAMINHO_SILVER.is_file():
        pytest.skip("silver local ausente: a hora inválida só existe nele")
    sv = dp.carrega_silver(dp.CAMINHO_SILVER)
    sv_ok = sv[sv["hora_int"].notna() & sv["dia_semana"].notna()]
    perdidas = int((~sv_ok["hora_int"].between(0, 23)).sum())
    assert f"perdia sem contar {perdidas} chamado" in errata


@requer_silver
def test_numeros_da_entrega_cc_continuam_valendo():
    """docs/entrega-cc.md (versão de 18/11) usa a mesma regra adotada no merge."""
    cc = (RAIZ / "docs" / "entrega-cc.md").read_text(encoding="utf-8")
    malha = dp.carrega_malha()
    df, _ = dp.casa_bairros(dp.carrega_silver(), {f["properties"]["chave"] for f in malha["features"]})
    m, fora = dp.hora_dia(df)
    cob = dp.cobertura_geo(df)
    for v in [dp.fmt_int(len(df)), dp.fmt_int(cob["no_mapa"]), dp.fmt_int(int(m.values.sum())),
              f"**{dp.fmt_int(m.iat[1, 8])} chamados**", dp.fmt_int(cob["fora"]),
              f"{int(df['data_fora_do_ano'].sum())} datas incompatíveis",
              dp.fmt_int(int((df["severidade"] == "VÍTIMA FATAL").sum()))]:
        assert v in cc, v
    assert "E6_dashboard_consolidado.md" in cc.split("## Abrir o dashboard")[0]  # nota no topo
