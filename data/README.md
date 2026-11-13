# data/

Os dados brutos **não** são versionados (ver `.gitignore`) — são baixáveis do
Portal de Dados Abertos do Recife e ficam grandes. Guarde-os localmente aqui.

## Onde colocar

Baixe os CSVs anuais (2015–2024) do dataset "Chamados de Sinistros (Acidentes)
de Trânsito com e sem vítimas" e coloque em `data/raw/`. O script de
transformação procura por qualquer arquivo `*<ano>*.csv` nesta pasta.

Portal: https://dados.recife.pe.gov.br  (dataset publicado pela CTTU)

## Malha e cadastro de bairros

Os mapas do dashboard usam o GeoJSON "Bairros do Recife" (em `data/geo/`) e os
classificadores validam o bairro de cada chamado contra o cadastro oficial
"Bairros e RPAs do Recife" (em `data/raw/bairros_oficiais.csv`). Os dois vêm do
dataset "Área urbana" (também ODbL), não são versionados e são baixados com:

```powershell
python src/baixa_malha_bairros.py
```

Sem a malha o dashboard funciona, mas sem os mapas. Sem o cadastro, só não dá
para regerar os artefatos dos classificadores (`data/classificacao/`).

> Atenção: os IDs de recurso do portal mudam. Baixe sempre pela página do
> dataset, não por URLs de download antigas (elas retornam 404).
