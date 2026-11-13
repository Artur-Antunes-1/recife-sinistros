# E6 — Dashboard consolidado (Projetos 5, G15)

Painel único em Streamlit sobre os chamados de sinistro de trânsito da CTTU (Recife, 2015–2024), com três páginas: **Pontos críticos**, **Previsão de volume elevado** e **Metodologia**. Os dados são carregados dos CSVs reais. Toda visualização é interativa e reage aos filtros. Nada é treinado em tempo de execução: a página de previsão lê artefatos pré-calculados (`data/classificacao/`). Todo número abaixo foi conferido contra a saída do código por `tests/test_docs_e6.py`.

Prints em 1440px: [`prints_E6/`](prints_E6/) — uma imagem por página e um recorte filtrado.

## Dois recortes, rotulados em cada página

| | Pontos críticos | Previsão de volume elevado |
|---|---|---|
| Status | só FINALIZADA | todos (inclui 11.563 CANCELADA e 455 DUPLICIDADE) |
| Registros | 59.006 (2015–2024) | 14.033 no alvo (2021–2024), de 72.255 na base |
| Bairro | normalização + de-para de 5 grafias | casamento exato com o cadastro de 94 bairros |

A avaliação dos classificadores foi entregue com todos os status e está fixada. Alinhá-la a FINALIZADA mudaria o alvo de 111 bairro-meses e exigiria retreinar. Por isso o grupo decidiu manter os dois recortes (ADR-017), e cada página mostra o seu num **selo de cobertura**.

## Decisões visuais

- **Barras horizontais ordenadas no ranking.** Comparar comprimentos é a leitura mais precisa de magnitude, e os nomes de bairro cabem sem girar. O valor fica rotulado em cada barra.
- **Coroplético por bairro, não mapa de pontos.** A base não tem latitude/longitude, e geocodificar endereços fura o custo zero (ADR-008). O mapa usa rampa sequencial de um tom só, em 6 classes, e o ranking ao lado dá os valores exatos.
- **Linha para a série mensal e barras para o total anual.** Uma faixa cinza marca 2020–2021, a queda de registro. 2015 aparece em tom claro e rotulado "parcial".
- **Mapa de calor 24 × 7 com o número em cada célula.** A cor do texto é escolhida pelo contraste com a célula.
- **Barras empilhadas em proporção para a severidade, mais um gráfico só de fatais.** A fatia de fatais é fina demais para ser lida dentro da proporção.
- **Na previsão: tabela, matriz 2×2, curvas ROC/PR, mapa de acertos e erros por mês, curva de limiares e F1 mensal.**
- **Paleta e contraste.** Texto `#1F1F1D` sobre fundo `#F7F7F5` (15,4:1). Uma única cor de destaque, azul `#256ABF`, marca a série principal. **Menor contraste de texto do painel: 5,39:1** (WCAG AA pede 4,5:1), garantido por teste automatizado. A rampa contínua foi trocada por classes discretas porque a faixa de azul médio não chegava a 4,5:1 com nenhuma cor de texto.
- **Cor só codifica dado.** A única exceção à cor única é a previsão: **azul = acerto, laranja = erro**, escuro = volume elevado observado, claro = regular. É um par seguro para daltonismo e vem sempre com legenda e contagem rotulada. Nenhuma informação depende só de cor. Não há pizza, 3D, arco-íris nem eixo truncado.
- **Divulgação progressiva.** O título de cada página afirma o achado com o número, calculado sobre o recorte atual. Seguem selo, indicadores, gráficos e notas. Na Metodologia, o detalhe fica em blocos expansíveis.
- **Incerteza visível.** O F1 do modelo aparece com IC 95% exploratório (bootstrap por mês). A prevalência do teste (46,0%) é a linha de referência da curva PR. O limiar exploratório tem o valor oficial (0,16) marcado e um aviso de que não altera a tabela oficial. Cada gráfico mostra o *n* do seu recorte.
- **Filtros coerentes.** Anos, bairros e severidade valem em todas as páginas que os usam. Onde um filtro não se aplica, a página diz isso no topo, por exemplo anos e severidade na previsão. Recorte vazio mostra mensagem, nunca gráfico quebrado.

## Por que Streamlit

| Critério | Streamlit | Power BI Web | Tableau Public | Looker Studio |
|---|---|---|---|---|
| Custo | grátis, código aberto (Apache-2.0) | a verificar (publicar na web pode exigir licença paga) | grátis | grátis |
| Mapa por bairro com malha própria (GeoJSON) | sim, Plotly, usado neste painel | a verificar | a verificar | a verificar |
| Reprodutibilidade em Python | total: mesmo código do pipeline e dos testes | parcial, a verificar | não nativa, a verificar | não nativa |
| Publicação gratuita | Streamlit Community Cloud: a verificar, não testado | a verificar | sim, mas os dados ficam públicos (a verificar) | sim, a verificar |

O critério decisivo foi a reprodutibilidade. O painel importa o mesmo código que gera o silver e os classificadores, e a suíte de testes roda contra ele. Um exemplo: um teste garante que o título anual não afirma uma queda quando o recorte sobe. Não sabemos se as outras ferramentas permitem testes automatizados desse tipo (a verificar).

## Insights até agora

1. **Concentração.** 10 bairros concentram **46,0%** dos chamados FINALIZADA com bairro identificado, e Boa Viagem sozinha tem **12,3%** (7.220). *Página: Pontos críticos.*
2. **Pico em dia útil de manhã.** O pico é terça às **8h** (835 chamados), e **75%** dos chamados com hora caem entre 7h e 19h. *Página: Pontos críticos (hora × dia).*
3. **A queda de 2019 a 2021 é de registro, não necessariamente de sinistros.** No silver os chamados vão de 10.109 a 2.095 (−79%). Quase toda a queda está nos SEM VÍTIMA (8.046 → 434), enquanto os COM VÍTIMA variam menos (2.036 → 1.631). Por isso a parcela COM VÍTIMA passa de 20% (2019) para 88% (2024). *Página: Pontos críticos (série e severidade).*
4. **O modelo acerta muito, mas pouco além do ingênuo.** A regressão logística identifica **92,3%** dos bairro-meses de volume elevado em 2024 (F1 **0,845**), contra F1 **0,835** de repetir o mês anterior: 46 omissões a menos e 51 alertas falsos a mais. Os IC 95% exploratórios se sobrepõem (0,828–0,860 contra 0,815–0,853). *Página: Previsão.*
5. **A escolha foi feita antes do teste.** A árvore tem F1 maior no teste (0,851), mas a logística venceu na validação de 2023, como mandava o protocolo. O F1 mensal vai de 0,786 (fev/2024) a 0,897 (ago/2024). *Página: Previsão.*

**Ressalvas que valem para todos:**
- Os dados são chamados da CTTU, não acidentes confirmados.
- Não há ajuste por área, população, exposição ou fluxo.
- 254 chamados FINALIZADA ficam fora do mapa, quase todos com bairro "NÃO INFORMADO".
- 2015 começa em junho, 2022 não tem horário, vítimas fatais só são conhecidas a partir de 2021, e 2024 termina em 28/12/2024 com 36 datas de outro ano.
- A previsão é retrospectiva e não teve validação operacional.

## Como rodar

```powershell
pip install -r requirements.txt
streamlit run app/dashboard.py
```

Na primeira vez, gere os dados derivados: `python src/transform_sinistros.py` (silver), `python src/baixa_malha_bairros.py` (malha e cadastro de bairros) e, se quiser regerar os artefatos já versionados, `python src/classificacao/gerar_artefatos.py`. Testes: `pytest`.
