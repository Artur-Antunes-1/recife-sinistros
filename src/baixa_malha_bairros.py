"""
baixa_malha_bairros.py
----------------------
Baixa os dois arquivos de referência de bairros do Recife:

  - a malha (GeoJSON) usada pelos mapas do dashboard -> data/geo/
  - o cadastro oficial dos 94 bairros (CSV) usado pelos classificadores para
    validar o bairro de cada chamado (ADR-017) -> data/raw/bairros_oficiais.csv

Fonte: Portal de Dados Abertos do Recife, dataset "Área urbana", recursos
"Bairros do Recife" (GeoJSON) e "Bairros e RPAs do Recife" (CSV), licença
ODbL. Nenhum dos dois é versionado (mesma lógica de data/raw/: é baixável do
portal).

O ID de cada recurso é buscado pela API do CKAN a cada execução, e não fixado
numa URL de download: os IDs do portal mudam (ver data/README.md).

Conferido em 13/11/2026: o CSV baixado pela URL do recurso é byte a byte igual
ao snapshot usado na avaliação dos classificadores
(entrega_classificadores/dados/brutos/bairros_oficiais.csv). O "dump" do
datastore NÃO serve: vem com outro separador e uma coluna _id a mais.

Rodar a partir da raiz do repositório:
    python src/baixa_malha_bairros.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

API = "https://dados.recife.pe.gov.br/api/3/action/package_show?id=area-urbana"
RAIZ = Path(__file__).resolve().parent.parent

# Caminho da malha. Mantido como constante porque src/prepara_dados_painel.py
# (base distribuída em data/painel/, ADR-018) importa DESTINO.
DESTINO = RAIZ / "data" / "geo" / "bairros-do-recife.geojson"

# (nome do recurso no portal, formato, destino local)
RECURSOS = [
    ("Bairros do Recife", "geojson", DESTINO),
    ("Bairros e RPAs do Recife", "csv", RAIZ / "data" / "raw" / "bairros_oficiais.csv"),
]


def urls_dos_recursos() -> dict[tuple[str, str], str]:
    with urllib.request.urlopen(API, timeout=60) as r:
        pacote = json.load(r)["result"]
    return {(rec.get("name"), rec.get("format", "").lower()): rec["url"]
            for rec in pacote["resources"]}


def _valida(conteudo: bytes, formato: str) -> str:
    """Confere o conteúdo antes de gravar e devolve um resumo para o log."""
    if formato == "geojson":
        return f"{len(json.loads(conteudo)['features'])} bairros"
    linhas = conteudo.decode("utf-8-sig").splitlines()
    # Cabeçalho esperado: "Bairro";"rpa". Falha alto se o portal mudar o layout.
    if "bairro" not in linhas[0].lower():
        raise RuntimeError(f"Cadastro de bairros com cabeçalho inesperado: {linhas[0]!r}")
    return f"{len(linhas) - 1} bairros"


def main():
    urls = urls_dos_recursos()
    for nome, formato, destino in RECURSOS:
        url = urls.get((nome, formato))
        if url is None:
            # Falha alto: melhor que baixar o recurso errado em silêncio.
            raise RuntimeError(f"Recurso '{nome}' ({formato}) não encontrado no dataset area-urbana.")
        with urllib.request.urlopen(url, timeout=120) as r:
            conteudo = r.read()
        resumo = _valida(conteudo, formato)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        print(f"{resumo} gravados em {destino} ({len(conteudo) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
