"""
dados_painel.py
---------------
Camada de dados do dashboard (app/dashboard.py): leitura do silver, casamento
de bairros com a malha oficial, filtros e agregações.

Fica separada da interface Streamlit de propósito: tudo aqui é pandas puro,
testável com pytest sem subir o app (ver tests/test_dashboard.py).

Regras de honestidade que este módulo garante (ver ADR-016):

  - O silver já vem filtrado (só FINALIZADA, ADR-005). NÃO filtramos de novo.
  - 'vitimasfatais' NÃO é usada para contar mortes: antes de 2021 ela é quase
    toda vazia (desconhecido, não zero). Fatais = severidade "VÍTIMA FATAL".
  - "NÃO INFORMADO" em bairro entra nos totais, mas sai de qualquer cálculo
    geográfico (ranking, mapa, concentração). A cobertura é reportada.
"""

from __future__ import annotations

import gzip
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


# --- Caminhos e constantes ------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_SILVER = RAIZ / "data" / "silver" / "sinistros_consolidado.csv"
CAMINHO_MALHA = RAIZ / "data" / "geo" / "bairros-do-recife.geojson"
PASTA_PAINEL = RAIZ / "data" / "painel"
CSV_PAINEL = PASTA_PAINEL / "sinistros.csv.gz"
MALHA_PAINEL = PASTA_PAINEL / "bairros.geojson.gz"
FONTES_PAINEL = PASTA_PAINEL / "fontes.json"
PASTA_RAW = RAIZ / "data" / "raw"

BAIRRO_NAO_INFORMADO = "NÃO INFORMADO"

# Ordem fixa das severidades (da menos para a mais grave, + ausente no fim).
SEVERIDADES = ["SEM VÍTIMA", "COM VÍTIMA", "VÍTIMA FATAL", BAIRRO_NAO_INFORMADO]

DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

# Linhas de ENTRADA (bruto, antes do filtro FINALIZADA) por ano, copiadas de
# docs/relatorio_qualidade_silver.md. Só servem para a nota da queda
# 2019-2021, que cita o volume bruto além do silver.
LINHAS_BRUTO = {2019: 12062, 2020: 4092, 2021: 2380}

# De-para EXPLÍCITO entre a grafia do CSV e a chave da malha, usado só no
# painel (o silver não muda). Cada entrada tem a mesma prova: o nome do CSV
# não existe na malha E o nome da malha não aparece no CSV — são o mesmo
# bairro escrito de dois jeitos. Ver ADR-016 para o critério e os números.
ALIAS_MALHA = {
    "BAIRRO DO RECIFE": "RECIFE",
    "JOANA BEZERRA": "ILHA JOANA BEZERRA",
    "ALTO SANTA TERESINHA": "ALTO SANTA TEREZINHA",
    "POCO DA PANELA": "POCO",
    "IPESEP": "IPSEP",
}


# --- Normalização de nome de bairro ---------------------------------------

def normaliza_nome(v: str) -> str:
    """Chave de comparação de bairro: sem acento, maiúscula, só letras/dígitos
    e espaço simples. Determinística — não adivinha nada."""
    s = unicodedata.normalize("NFD", str(v))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def nome_exibicao(v: str) -> str:
    """'SÃO JOSÉ' -> 'São José'; preposições ficam minúsculas."""
    minusculas = {"DA", "DE", "DO", "DAS", "DOS", "E"}
    partes = str(v).split()
    return " ".join(p.lower() if (i > 0 and p in minusculas) else p.capitalize()
                    for i, p in enumerate(partes))


# --- Leitura ---------------------------------------------------------------

# Estratégia única de carregamento (ADR-018): a base empacotada em data/painel/
# vem primeiro, porque é versionada e é o que uma cópia limpa (e o Streamlit
# Community Cloud) enxerga — assim o painel mostra os mesmos números em
# qualquer máquina. O silver e a malha locais são o fallback, para quem roda
# o pipeline sem a pasta data/painel/. As contagens são idênticas (59.006).

def caminho_silver() -> Path:
    return CSV_PAINEL if CSV_PAINEL.is_file() else CAMINHO_SILVER


def caminho_malha() -> Path:
    return MALHA_PAINEL if MALHA_PAINEL.is_file() else CAMINHO_MALHA


def carrega_silver(caminho: Path | None = None) -> pd.DataFrame:
    """Lê a base do painel (data/painel/, ou o silver local como fallback).

    Não descarta nenhuma linha: o total tem que bater com o relatório de
    qualidade (59.006 linhas em 20/10/2026)."""
    df = pd.read_csv(caminho or caminho_silver(), sep=";", dtype=str, keep_default_na=False,
                     encoding="utf-8")
    df["ano"] = df["ano"].astype(int)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["data_fora_do_ano"] = df["data_fora_do_ano"] == "True"
    # Hora vazia (2022 inteiro, e algumas linhas de 2016-2019) vira NA, não 0h.
    df["hora_int"] = pd.to_numeric(df["hora"].str[:2], errors="coerce").astype("Int64")
    df["dia_semana"] = df["data"].dt.day_of_week  # 0 = segunda
    return df


def carrega_malha(caminho: Path | None = None) -> dict | None:
    """Lê o GeoJSON de bairros e grava em cada feição a chave normalizada
    ('chave'). Devolve None se o arquivo não existir — o painel segue sem mapa.

    A chave vem de EBAIRRNOME (caixa alta, sem acento). EBAIRRNOMEOF não é
    usada: no arquivo do portal ela vem com o acento corrompido (U+FFFD)."""
    caminho = caminho or caminho_malha()
    if not caminho.is_file():
        return None
    abrir = gzip.open if caminho.suffix == ".gz" else open
    with abrir(caminho, "rt", encoding="utf-8") as arquivo:
        malha = json.load(arquivo)
    for f in malha["features"]:
        f["properties"] = {"chave": normaliza_nome(f["properties"]["EBAIRRNOME"])}
        f["geometry"] = _arredonda_geometria(f["geometry"])
    return malha


def _arredonda_geometria(geom: dict, casas: int = 5) -> dict:
    """5 casas decimais ~ 1 m: invisível no mapa, e o JSON enviado ao
    navegador encolhe bastante."""
    def arred(c):
        return [round(c[0], casas), round(c[1], casas)] if isinstance(c[0], float) \
            else [arred(x) for x in c]
    return {"type": geom["type"], "coordinates": arred(geom["coordinates"])}


# --- Casamento silver x malha ----------------------------------------------

def casa_bairros(df: pd.DataFrame, chaves_malha: set[str] | None) -> tuple[pd.DataFrame, dict]:
    """Adiciona ao df:
       - 'bairro_chave': chave da malha (ou None se não casou / não informado)
       - 'bairro_painel': nome que o painel exibe e filtra

    Devolve também um relatório do casamento, em duas etapas (só
    normalização; normalização + ALIAS_MALHA), para o painel e o ADR."""
    df = df.copy()
    informado = df["bairro"] != BAIRRO_NAO_INFORMADO
    norm = df["bairro"].map(normaliza_nome)
    canon = norm.map(lambda b: ALIAS_MALHA.get(b, b))

    if chaves_malha is None:
        # Sem malha, o ranking ainda funciona: agrupa pela chave canônica.
        df["bairro_chave"] = canon.where(informado)
        casou_sem_alias = casou_com_alias = None
    else:
        df["bairro_chave"] = canon.where(informado & canon.isin(chaves_malha))
        casou_sem_alias = norm.isin(chaves_malha)
        casou_com_alias = df["bairro_chave"].notna()

    # Nome exibido: a grafia crua mais frequente entre as linhas daquela chave
    # (preserva acento: 'SÃO JOSÉ' -> 'São José').
    grafia = (df.loc[df["bairro_chave"].notna()]
                .groupby("bairro_chave")["bairro_original"]
                .agg(lambda s: s.value_counts().index[0]))
    exib = df["bairro_chave"].map(grafia).map(nome_exibicao, na_action="ignore")
    # Linhas fora da malha mantêm o nome do silver (aparecem no filtro).
    df["bairro_painel"] = exib.astype("string").fillna(
        df["bairro"].where(~informado, df["bairro"].map(nome_exibicao)))

    rel = {"linhas": len(df), "nao_informado": int((~informado).sum())}
    if chaves_malha is not None:
        dist = norm[informado]
        sem_alias = sorted(set(dist) - chaves_malha)
        com_alias = sorted(set(dist.map(lambda b: ALIAS_MALHA.get(b, b))) - chaves_malha)
        rel.update({
            "bairros_csv": int(dist.nunique()),
            "bairros_malha": len(chaves_malha),
            "nao_casaram_sem_alias": sem_alias,
            "linhas_nao_casaram_sem_alias": int((informado & ~casou_sem_alias).sum()),
            "nao_casaram_com_alias": com_alias,
            "linhas_nao_casaram_com_alias": int((informado & ~casou_com_alias).sum()),
            "malha_sem_registro": sorted(chaves_malha - set(df["bairro_chave"].dropna())),
        })
    return df, rel


# --- Filtros ----------------------------------------------------------------

def aplica_filtros(df: pd.DataFrame, anos: tuple[int, int],
                   bairros: list[str] | None, severidades: list[str]) -> pd.DataFrame:
    """Recorte do painel. bairros vazio/None = todos; severidades vazio = nenhuma
    (recorte vazio — a interface avisa em vez de quebrar)."""
    m = df["ano"].between(anos[0], anos[1]) & df["severidade"].isin(severidades)
    if bairros:
        m &= df["bairro_painel"].isin(bairros)
    return df[m]


# --- Agregações ---------------------------------------------------------------

def ranking_bairros(rec: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Top n bairros (só os que casaram com a malha) com contagem e % sobre
    os registros geolocalizáveis do recorte."""
    geo = rec[rec["bairro_chave"].notna()]
    r = geo.groupby("bairro_painel").size().sort_values(ascending=False)
    total = int(r.sum())
    out = r.head(n).rename("registros").reset_index()
    out["pct"] = out["registros"] / total * 100 if total else 0.0
    return out


def concentracao_top(rec: pd.DataFrame, k: int = 10) -> tuple[int, float]:
    """(k efetivo, % dos registros geolocalizáveis nos k maiores bairros)."""
    r = rec[rec["bairro_chave"].notna()].groupby("bairro_chave").size()
    if r.empty:
        return 0, 0.0
    k = min(k, len(r))
    return k, float(r.nlargest(k).sum() / r.sum() * 100)


def cobertura_geo(rec: pd.DataFrame) -> dict:
    """Quantos registros do recorte ficam fora do mapa, e por quê."""
    nao_inf = int((rec["bairro"] == BAIRRO_NAO_INFORMADO).sum())
    fora = int(rec["bairro_chave"].isna().sum())
    return {"total": len(rec), "no_mapa": len(rec) - fora, "fora": fora,
            "nao_informado": nao_inf, "sem_poligono": fora - nao_inf}


def por_ano(rec: pd.DataFrame) -> pd.Series:
    return rec.groupby("ano").size()


def por_mes(rec: pd.DataFrame) -> pd.Series:
    """Série mensal pela data do registro. Linhas com data_fora_do_ano (32 do
    arquivo de 2024 datadas em dez/2025) ficam fora: a data delas não é
    confiável. O painel informa quantas."""
    ok = rec[~rec["data_fora_do_ano"] & rec["data"].notna()]
    s = ok.groupby(ok["data"].dt.to_period("M")).size()
    if s.empty:
        return s
    # Meses sem registro dentro do intervalo valem 0 (contagem), não lacuna.
    idx = pd.period_range(s.index.min(), s.index.max(), freq="M")
    return s.reindex(idx, fill_value=0)


def hora_dia(rec: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Matriz 7x24 (dia da semana x hora) e quantos registros ficaram de fora
    por terem hora ou data inválida."""
    ok = rec[rec["hora_int"].between(0, 23) & rec["dia_semana"].notna()
             & ~rec["data_fora_do_ano"]]
    m = (ok.groupby([ok["dia_semana"].astype(int), ok["hora_int"].astype(int)])
           .size().unstack(fill_value=0)
           .reindex(index=range(7), columns=range(24), fill_value=0))
    return m, len(rec) - len(ok)


def por_hora(rec: pd.DataFrame) -> tuple[pd.Series, int]:
    """Registros por hora do dia (0-23), sem separar por dia da semana.

    É a soma das linhas da matriz de hora_dia: usa exatamente o mesmo
    critério de exclusão, para o gráfico por hora e o mapa de calor terem o
    mesmo n na tela (feedback da professora: ver sinistros x hora sem o dia)."""
    m, fora = hora_dia(rec)
    return m.sum(axis=0), fora


def severidade_por_ano(rec: pd.DataFrame) -> pd.DataFrame:
    """Contagem por ano x severidade, colunas na ordem de SEVERIDADES."""
    return (rec.groupby(["ano", "severidade"]).size().unstack(fill_value=0)
               .reindex(columns=SEVERIDADES, fill_value=0))


def pct_com_vitima_por_ano(rec: pd.DataFrame) -> pd.DataFrame:
    """Por ano: registros com severidade conhecida, quantos têm vítima
    (COM VÍTIMA + VÍTIMA FATAL) e o %. Severidade "NÃO INFORMADO" sai do
    denominador — não sabemos se teve vítima. Anos sem severidade conhecida
    no recorte ficam de fora (evita divisão por zero)."""
    spa = severidade_por_ano(rec)
    conhecida = spa[["SEM VÍTIMA", "COM VÍTIMA", "VÍTIMA FATAL"]].sum(axis=1)
    com_vitima = spa["COM VÍTIMA"] + spa["VÍTIMA FATAL"]
    out = pd.DataFrame({"conhecida": conhecida, "com_vitima": com_vitima})
    out = out[out["conhecida"] > 0]
    out["pct"] = out["com_vitima"] / out["conhecida"] * 100
    return out


# A coluna vitimasfatais só tem preenchimento consistente a partir de 2021
# (antes: 0% a 1% das células). Ver ADR-016 e o selo de cobertura.
ANO_INICIO_VITIMASFATAIS = 2021


def fatais_por_registro(rec: pd.DataFrame) -> pd.DataFrame:
    """Por ano, de 2021 em diante: registros, soma de vitimasfatais (pessoas
    mortas) e mortes por 1.000 registros.

    Por 1.000 porque a taxa por registro é ~0,01 e ficaria ilegível. Anos
    antes de ANO_INICIO_VITIMASFATAIS NÃO entram: lá célula vazia é
    desconhecido, e somar daria um falso zero. Célula vazia em 2021+ (rara)
    também fica fora do numerador e do denominador."""
    r = rec[(rec["ano"] >= ANO_INICIO_VITIMASFATAIS) & (rec["vitimasfatais"] != "")]
    if r.empty:
        return pd.DataFrame(columns=["registros", "mortes", "por_mil"])
    mortes = pd.to_numeric(r["vitimasfatais"], errors="raise")  # falha alto se vier lixo
    out = pd.DataFrame({"registros": r.groupby("ano").size(),
                        "mortes": mortes.groupby(r["ano"]).sum().astype(int)})
    out["por_mil"] = out["mortes"] / out["registros"] * 1000
    return out


# --- Metadados para o rodapé ---------------------------------------------------

def data_download_raw(pasta: Path = PASTA_RAW) -> pd.Timestamp | None:
    """Data dos CSVs brutos em data/raw/ (a mais antiga). É a data em que os
    arquivos foram baixados do portal nesta máquina."""
    arqs = list(pasta.glob("*.csv"))
    return min(pd.Timestamp(a.stat().st_mtime, unit="s") for a in arqs) if arqs else None


def fmt_int(n: int) -> str:
    """59006 -> '59.006'."""
    return f"{int(n):,}".replace(",", ".")


def fmt_pct(v: float, casas: int = 1) -> str:
    """Formata percentual em pt-BR.

    Nunca arredonda para 100% um valor menor que 100, nem para 0% um valor
    maior que 0. O arredondamento afirmaria o que o dado não sustenta: a
    severidade conhecida é 99,95085% (29 registros sem severidade em 59.006)
    e aparecia como "100,0% ... 29 sem severidade", que se contradiz na tela.
    """
    passo = 10 ** -casas
    texto = f"{v:.{casas}f}"
    if v < 100 and float(texto) >= 100:
        texto = f"{100 - passo:.{casas}f}"
    elif v > 0 and float(texto) <= 0:
        texto = f"{passo:.{casas}f}"
    return texto.replace(".", ",") + "%"
