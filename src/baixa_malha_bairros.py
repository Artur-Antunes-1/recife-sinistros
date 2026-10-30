"""
baixa_malha_bairros.py
----------------------
Baixa a malha de bairros do Recife (GeoJSON) usada pelo mapa do dashboard.

Fonte: Portal de Dados Abertos do Recife, dataset "Área urbana", recurso
"Bairros do Recife" (licença ODbL). Grava em data/geo/, que não é versionado
(mesma lógica de data/raw/: é baixável do portal).

O ID do recurso é buscado pela API do CKAN a cada execução, e não fixado numa
URL de download: os IDs do portal mudam (ver data/README.md).

Rodar a partir da raiz do repositório:
    python src/baixa_malha_bairros.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

API = "https://dados.recife.pe.gov.br/api/3/action/package_show?id=area-urbana"
NOME_RECURSO = "Bairros do Recife"
DESTINO = Path(__file__).resolve().parent.parent / "data" / "geo" / "bairros-do-recife.geojson"


def url_do_recurso() -> str:
    with urllib.request.urlopen(API, timeout=60) as r:
        pacote = json.load(r)["result"]
    for rec in pacote["resources"]:
        if rec.get("name") == NOME_RECURSO and rec.get("format", "").lower() == "geojson":
            return rec["url"]
    # Falha alto: melhor que baixar o recurso errado em silêncio.
    raise RuntimeError(f"Recurso GeoJSON '{NOME_RECURSO}' não encontrado no dataset area-urbana.")


def main():
    url = url_do_recurso()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r:
        conteudo = r.read()
    n = len(json.loads(conteudo)["features"])  # valida que é GeoJSON antes de gravar
    DESTINO.write_bytes(conteudo)
    print(f"{n} bairros gravados em {DESTINO} ({len(conteudo) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
