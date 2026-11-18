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

Em um clone limpo, o dashboard usa a cópia compactada da malha em `data/painel/`.
Sem malha nenhuma (nem a local nem a de `data/painel/`) o dashboard funciona,
mas sem os mapas. Sem o cadastro, só não dá para regerar os artefatos dos
classificadores (`data/classificacao/`).

> Atenção: os IDs de recurso do portal mudam. Baixe sempre pela página do
> dataset, não por URLs de download antigas (elas retornam 404).

## Base distribuída com a entrega CC

`data/painel/` traz apenas as colunas usadas nos gráficos e os limites dos 94
bairros. Veja [fontes.json](painel/fontes.json) para autoria, licença ODbL,
data de extração, contagens anuais e hashes dos arquivos. Dois rótulos livres
de bairro foram neutralizados. As linhas continuam na contagem de chamados
sem correspondência com a malha. Os horários foram reduzidos a faixas de 00 a
23 horas. Quatro valores originalmente preenchidos ficaram vazios por
conterem horários inválidos.

Para reproduzir a base a partir dos CSVs da CTTU e da malha oficial, instale
`requirements.txt` e execute na raiz do repositório:

```powershell
python -m src.prepara_dados_painel --baixar
```

Com todos os CSVs de `data/raw/` e a malha de `data/geo/` já disponíveis,
execute o mesmo comando sem `--baixar`.
