"""
preparacao.py
-------------
Base dos classificadores: lê os 10 CSVs brutos de data/raw/ e marca, chamado a
chamado, se a data e o bairro são válidos. Porta fiel de preparar() de
entrega_classificadores/preparacao_cttu.py (ADR-017), reduzida ao que o alvo
e o selo de cobertura usam.

Por que NÃO reaproveita o silver (data/silver/): o silver tem só FINALIZADA
(ADR-005), casa bairro com 5 aliases (ADR-016) e remove duplicata sem
protocolo (ADR-015). Os classificadores foram avaliados com todos os status,
casamento exato com o cadastro oficial e sem essas remoções. Só o filtro
FINALIZADA já mudaria o alvo de 111 bairro-meses (62 no treino, 29 na
validação, 20 no teste) e invalidaria a avaliação entregue (medido no
Passo 0; decisão: opção (a), dois recortes rotulados — ADR-017).

O que É reaproveitado: os CSVs de data/raw/ (byte a byte iguais aos do ZIP,
SHA-256 conferido) e a malha de data/geo/.

Diferenças de propósito em relação ao script do ZIP: nada é baixado aqui
(os brutos já estão em data/raw/) e nenhuma estatística descritiva é
calculada — só o necessário para o painel bairro-mês.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
PASTA_RAW = RAIZ / "data" / "raw"
CAMINHO_CADASTRO = PASTA_RAW / "bairros_oficiais.csv"
ANOS = list(range(2015, 2025))


def chave(x):
    """Chave de comparação de texto: sem acento, maiúscula, espaço simples.
    Idêntica à do ZIP — mudar aqui muda quais bairros casam com o cadastro."""
    if pd.isna(x):
        return pd.NA
    s = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().upper()
    s = " ".join(s.strip().split())
    return s if s else pd.NA


def _coluna(x) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(chave(x)).lower()).strip("_")


def ler_csv(path: Path) -> pd.DataFrame:
    """Lê um CSV do portal detectando encoding e separador; célula vazia ou
    'NA'/'NULL' vira NA (desconhecido), nunca zero."""
    blob = Path(path).read_bytes()
    for enc in ["utf-8-sig", "cp1252", "latin1"]:
        try:
            texto = blob.decode(enc)
        except UnicodeDecodeError:
            continue
        cabecalho = texto.splitlines()[0]
        sep = max([";", ",", "\t", "|"], key=cabecalho.count)
        d = pd.read_csv(io.StringIO(texto), sep=sep, dtype="string", keep_default_na=False)
        if len(d.columns) < 2:
            raise ValueError(f"CSV inválido: {path}")
        d.columns = [_coluna(c) for c in d.columns]
        if d.columns.duplicated().any():
            raise ValueError(f"Colisão de nomes de coluna em {path}")
        d = d.apply(lambda s: s.str.strip()).replace(
            r"^\s*$|^(?i:NA|N/A|NULL|NAN)$", pd.NA, regex=True)
        return d
    raise ValueError(f"Codificação inválida: {path}")


def arquivos_por_ano(pasta: Path = PASTA_RAW) -> dict[int, Path]:
    """Os CSVs de data/raw/ por ano (o nome do portal contém 'transito-<ano>')."""
    saida = {}
    for p in pasta.glob("*.csv"):
        m = re.search(r"transito-(\d{4})", p.name)
        if m:
            saida[int(m.group(1))] = p
    faltam = sorted(set(ANOS) - set(saida))
    if faltam:
        # Falha alto: avaliação com ano faltando seria outra avaliação.
        raise FileNotFoundError(f"CSVs ausentes em {pasta} para os anos {faltam}")
    return saida


def bairros_oficiais(caminho: Path = CAMINHO_CADASTRO) -> list[str]:
    """Os 94 bairros do cadastro oficial, já como chave, na ordem do arquivo."""
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não existe. Rode: python src/baixa_malha_bairros.py")
    b = ler_csv(caminho)
    if "bairro" not in b:
        raise ValueError("Cadastro oficial não contém a coluna 'bairro'")
    nomes = b["bairro"].map(chave).dropna()
    if nomes.duplicated().any():
        raise ValueError("Colisão de nomes no cadastro de bairros")
    return nomes.tolist()


def preparar(pasta: Path = PASTA_RAW, cadastro: Path = CAMINHO_CADASTRO) -> pd.DataFrame:
    """Uma linha por chamado (todos os status), com as marcas que o alvo usa:

      data_valida      data interpretável e no ano do arquivo
      ano_divergente   data interpretável, mas de outro ano (ex.: 36 em 2024)
      hora_n           hora 0-23, ou NA (2022 não tem hora utilizável)
      bairro_validado  bairro casa EXATAMENTE (após chave()) com o cadastro
      vitimasfatais_n  inteiro >= 0 ou NA — vazio é desconhecido, nunca zero

    Só remove 'cópia técnica' (linha idêntica E com protocolo preenchido),
    como o script do ZIP. Nos dados de 2015-2024 isso remove 0 linhas."""
    oficiais = set(bairros_oficiais(cadastro))
    partes = []
    for ano, path in sorted(arquivos_por_ano(pasta).items()):
        d = ler_csv(path)
        originais = d.columns.tolist()
        d["ano_origem"] = ano
        copia = d.duplicated(subset=[c for c in originais if c != "id"], keep="first")
        copia &= d.get("protocolo", pd.Series(pd.NA, index=d.index)).notna()
        d = d.loc[~copia].copy()
        for c in ["data", "hora", "bairro", "situacao", "vitimasfatais"]:
            if c not in d:
                d[c] = pd.NA
        # ISO antes da leitura brasileira: evita trocar mês e dia em datas ISO.
        s = d["data"].astype("string")
        iso = s.str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
        dt = pd.Series(pd.NaT, index=d.index, dtype="datetime64[ns]")
        dt.loc[iso] = pd.to_datetime(s[iso], format="ISO8601", errors="coerce")
        dt.loc[~iso] = pd.to_datetime(s[~iso], format="mixed", dayfirst=True, errors="coerce")
        d["data_dt"] = dt.dt.normalize()
        d["data_valida"] = dt.notna() & dt.dt.year.eq(ano)
        d["ano_divergente"] = dt.notna() & ~dt.dt.year.eq(ano)
        h = d["hora"].astype("string").str.extract(r"^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$")
        hh, mm = pd.to_numeric(h[0], errors="coerce"), pd.to_numeric(h[1], errors="coerce")
        ss = pd.to_numeric(h[2], errors="coerce").fillna(0)
        d["hora_n"] = hh.where(hh.between(0, 23) & mm.between(0, 59) & ss.between(0, 59))
        d["bairro_chave"] = d["bairro"].map(chave)
        d["situacao_chave"] = d["situacao"].map(chave)
        x = pd.to_numeric(d["vitimasfatais"].astype("string").str.replace(",", ".", regex=False),
                          errors="coerce")
        d["vitimasfatais_n"] = x.where(x.ge(0) & x.mod(1).eq(0))
        partes.append(d[["ano_origem", "data_dt", "data_valida", "ano_divergente", "hora_n",
                         "bairro_chave", "situacao_chave", "vitimasfatais_n"]])
    base = pd.concat(partes, ignore_index=True)
    base["bairro_validado"] = base["bairro_chave"].isin(oficiais)
    return base


def qualidade_por_ano(base: pd.DataFrame) -> pd.DataFrame:
    """Resumo por ano da base dos classificadores (alimenta o selo de cobertura)."""
    g = base.groupby("ano_origem")
    q = pd.DataFrame({
        "registros": g.size(),
        "finalizada": g["situacao_chave"].apply(lambda s: int(s.eq("FINALIZADA").sum())),
        "datas_validas": g["data_valida"].sum(),
        "datas_outro_ano": g["ano_divergente"].sum(),
        "horas_validas": g["hora_n"].count(),
        "bairro_validado": g["bairro_validado"].sum(),
        "vitimasfatais_conhecidas": g["vitimasfatais_n"].count(),
    })
    validas = base.loc[base["data_valida"]].groupby("ano_origem")["data_dt"]
    q["primeira_data"] = validas.min().dt.strftime("%Y-%m-%d")
    q["ultima_data"] = validas.max().dt.strftime("%Y-%m-%d")
    q.index.name = "ano"
    return q.reset_index().astype({"datas_validas": int, "datas_outro_ano": int,
                                    "bairro_validado": int})
