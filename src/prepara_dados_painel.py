"""Gera a cópia mínima usada pelo Streamlit em um clone limpo.

Na raiz do repositório, após instalar requirements.txt:
    python -m src.prepara_dados_painel --baixar

Sem --baixar, usa os dez CSVs e a malha já disponíveis em data/.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import urllib.request
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from app.dados_painel import ALIAS_MALHA, BAIRRO_NAO_INFORMADO, normaliza_nome
from src import baixa_malha_bairros
from src.transform_sinistros import transform


RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw"
PACOTE = RAIZ / "data" / "painel"
ANOS = range(2015, 2025)
DATASET = "acidentes-de-transito-com-e-sem-vitimas"
PORTAL = "https://dados.recife.pe.gov.br"
# vitimasfatais entrou no merge com o Ciclo 6 (ADR-018): a página de pontos
# críticos mostra o preenchimento da coluna por ano. Vazio continua sendo
# desconhecido, nunca zero (ADR-014).
COLUNAS_PAINEL = ["ano", "data", "data_fora_do_ano", "hora", "severidade",
                  "bairro", "bairro_original", "vitimasfatais"]


def arquivos_anuais() -> dict[int, Path | None]:
    """Usa a mesma convenção de nome do script de transformação local."""
    arquivos = {}
    for ano in ANOS:
        candidatos = sorted(RAW.glob(f"*{ano}*.csv"))
        if len(candidatos) > 1:
            raise ValueError(f"Mais de um CSV em data/raw/ para {ano}: {candidatos}")
        arquivos[ano] = candidatos[0] if candidatos else None
    return arquivos


def baixa_csv_faltantes(anos: list[int]) -> None:
    if not anos:
        return
    api = f"{PORTAL}/api/3/action/package_show?id={DATASET}"
    with urllib.request.urlopen(api, timeout=60) as resposta:
        recursos = json.load(resposta)["result"]["resources"]
    anuais = {}
    for recurso in recursos:
        sufixo_ano = re.search(r"\b(20\d{2})$", recurso["name"].strip())
        if recurso.get("format", "").upper() == "CSV" and sufixo_ano:
            ano = int(sufixo_ano.group(1))
            if ano in anuais:
                raise ValueError(f"Mais de um recurso CSV para {ano} no CKAN.")
            anuais[ano] = recurso
    if not set(anos).issubset(anuais):
        raise ValueError(f"CSVs ausentes no CKAN: {sorted(set(anos) - anuais.keys())}.")

    RAW.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=RAW) as pasta_temporaria:
        for ano in anos:
            recurso = anuais[ano]
            destino = RAW / f"acidentes-de-transito-{ano}.csv"
            with urllib.request.urlopen(recurso["url"], timeout=120) as resposta:
                conteudo = resposta.read()
            if not conteudo or (recurso.get("size") and len(conteudo) != int(recurso["size"])):
                raise ValueError(f"Download incompleto para {ano}.")
            if not destino.exists():
                temporario = Path(pasta_temporaria) / destino.name
                temporario.write_bytes(conteudo)
                temporario.replace(destino)


def minimiza_malha(caminho: Path) -> dict:
    malha = json.loads(caminho.read_text(encoding="utf-8"))
    if malha["type"] != "FeatureCollection" or not malha["features"]:
        raise ValueError("A malha deve ser uma coleção não vazia de bairros.")
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"EBAIRRNOME": f["properties"]["EBAIRRNOME"]},
             "geometry": f["geometry"]} for f in malha["features"]
        ],
    }


def neutraliza_bairros(silver: pd.DataFrame, malha: dict) -> int:
    """Preserva os agrupamentos e elimina texto livre fora da lista conhecida."""
    bairros_oficiais = {normaliza_nome(f["properties"]["EBAIRRNOME"])
                        for f in malha["features"]}
    conhecidos = bairros_oficiais | {origem for origem, destino in ALIAS_MALHA.items()
                                    if destino in bairros_oficiais}
    conhecidos.update({normaliza_nome(BAIRRO_NAO_INFORMADO), "SETUBAL"})
    chaves = silver["bairro"].map(normaliza_nome)
    desconhecidos = sorted(set(chaves) - conhecidos)
    rotulos = {chave: f"BAIRRO NÃO RECONHECIDO {i}" for i, chave in enumerate(desconhecidos, 1)}
    neutros = chaves.map(rotulos)
    mask = neutros.notna()
    silver.loc[mask, "bairro"] = neutros[mask]
    silver.loc[mask, "bairro_original"] = neutros[mask]
    return len(rotulos)


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def nome_canonico(caminho: Path) -> str:
    """Nome estável no manifesto, independente de como o CSV foi salvo em
    data/raw/ (o portal entrega nomes com prefixo de recurso)."""
    m = re.search(r"transito-(\d{4})", caminho.name)
    return f"acidentes-de-transito-{m.group(1)}.csv" if m else caminho.name


def data_extracao(entradas: list[Path], hashes: dict[str, str]) -> str:
    """Data da extração das fontes. Se o manifesto anterior registra as MESMAS
    entradas (mesmos SHA-256), a extração é a mesma e a data é preservada;
    senão, vale a data de modificação mais recente das entradas."""
    anterior = PACOTE / "fontes.json"
    if anterior.is_file():
        manifesto = json.loads(anterior.read_text(encoding="utf-8"))
        if manifesto.get("sha256_entradas") == hashes:
            return manifesto["data_extracao"]
    return date.fromtimestamp(max(a.stat().st_mtime for a in entradas)).isoformat()


def grava_pacote(arquivos: dict[int, Path], caminho_malha: Path) -> None:
    malha = minimiza_malha(caminho_malha)
    transformados = [transform(str(caminho), ano) for ano, caminho in arquivos.items()]
    silver = pd.concat([df[COLUNAS_PAINEL] for df, _ in transformados], ignore_index=True)
    metricas = [m for _, m in transformados]
    if any(not m["linhas_silver"] for m in metricas):
        raise ValueError("Cada ano deve conter ao menos um chamado finalizado.")
    neutralizados = neutraliza_bairros(silver, malha)
    # O gráfico usa apenas a faixa horária, sem minutos, segundos ou texto livre.
    hora = silver["hora"].str[:2]
    hora_valida = hora.str.fullmatch(r"(?:[01][0-9]|2[0-3])", na=False)
    horas_invalidas = int((~hora_valida & silver["hora"].fillna("").ne("")).sum())
    silver["hora"] = hora.where(hora_valida)
    entradas = [*arquivos.values(), caminho_malha]
    hashes_entradas = {nome_canonico(a): sha256(a) for a in entradas}

    PACOTE.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=PACOTE) as pasta_temporaria:
        pasta = Path(pasta_temporaria)
        csv = pasta / "sinistros.csv.gz"
        geo = pasta / "bairros.geojson.gz"
        # mtime=0 torna os dados comprimidos reproduzíveis a partir da mesma entrada.
        texto_csv = silver.to_csv(sep=";", index=False, lineterminator="\n")
        texto_geo = json.dumps(malha, ensure_ascii=False, separators=(",", ":"))
        csv.write_bytes(gzip.compress(texto_csv.encode("utf-8"), mtime=0))
        geo.write_bytes(gzip.compress(texto_geo.encode("utf-8"), mtime=0))
        fontes = {
            "data_extracao": data_extracao(entradas, hashes_entradas),
            "fontes": {"sinistros": f"{PORTAL}/dataset/{DATASET}",
                       "bairros": f"{PORTAL}/dataset/area-urbana"},
            "licenca": {"nome": "Open Database License (ODbL) 1.0",
                        "url": "https://opendatacommons.org/licenses/odbl/1-0/"},
            "atribuicao": "CTTU e Prefeitura do Recife, Portal de Dados Abertos do Recife.",
            "registros_por_ano": {m["ano"]: m["linhas_silver"] for m in metricas},
            "linhas_brutas_por_ano": {m["ano"]: m["linhas_entrada"] for m in metricas},
            "quantidade_bairros": len(malha["features"]),
            "rotulos_bairro_neutralizados": neutralizados,
            "horarios_invalidos_neutralizados": horas_invalidas,
            "colunas_publicadas": COLUNAS_PAINEL,
            "sha256_entradas": hashes_entradas,
            "sha256_pacote": {a.name: sha256(a) for a in (csv, geo)},
        }
        manifesto = pasta / "fontes.json"
        manifesto.write_text(json.dumps(fontes, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
        for arquivo in (csv, geo, manifesto):
            arquivo.replace(PACOTE / arquivo.name)
    print(f"{len(silver)} chamados de {len(arquivos)} anos e {len(malha['features'])} bairros em {PACOTE}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baixar", action="store_true", help="Baixa apenas as fontes que faltam.")
    args = parser.parse_args()

    arquivos = arquivos_anuais()
    if args.baixar:
        baixa_csv_faltantes([ano for ano, arquivo in arquivos.items() if arquivo is None])
        if not baixa_malha_bairros.DESTINO.exists():
            baixa_malha_bairros.main()
        arquivos = arquivos_anuais()
    faltantes = [str(ano) for ano, arquivo in arquivos.items() if arquivo is None]
    if not baixa_malha_bairros.DESTINO.is_file():
        faltantes.append("malha de bairros")
    if faltantes:
        parser.error(f"Fontes locais ausentes ({', '.join(faltantes)}). Rode com --baixar.")

    grava_pacote({ano: caminho for ano, caminho in arquivos.items() if caminho is not None},
                 baixa_malha_bairros.DESTINO)


if __name__ == "__main__":
    main()
