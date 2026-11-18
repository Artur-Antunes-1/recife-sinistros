Decisões de Arquitetura (ADRs)

Registro curto das decisões e do porquê. A intenção é que qualquer pessoa (inclusive você daqui a três meses) entenda as escolhas sem arqueologia.

ADR-001 — VPC incluída por portfólio, não por necessidade funcional

Uma Lambda que só lê e escreve no S3 não precisa de VPC — o acesso ao S3 acontece pela rede da própria AWS. A VPC (com subnet privada, Gateway Endpoint e IAM na fronteira) foi incluída deliberadamente para demonstrar competência de rede, que é o que uma vaga de Cloud avalia. Decisão consciente, documentada para deixar claro que entendemos quando a VPC é necessária e quando é escolha.

ADR-002 — S3 Gateway Endpoint em vez de NAT Gateway

Dado que há um recurso dentro da VPC (a Lambda, ver ADR-001) que precisa alcançar o S3, usamos um Gateway Endpoint (grátis, ilimitado para S3/ DynamoDB) e não um NAT Gateway (cobrado por hora + por GB). Mantém o custo zero. Consequência: a Lambda na VPC não tem saída para a internet — aceitável, porque ela só fala com o S3.

ADR-003 — Schema canônico "opção A" + vitimasfatais

O silver projeta para um conjunto fixo de ~19 conceitos comuns aos anos, mais vitimasfatais. Motivo de incluir vitimasfatais mesmo sendo só de 2021+: severidade é o sinal central de um projeto de trânsito, e lidar com evolução de schema (campo que nasce no meio da série, com nulo honesto para anos antigos) é competência a demonstrar. Nulo para anos sem a coluna — nunca zero.

Correção (20/10/2026, medido nos CSVs reais): a versão anterior deste ADR dizia "2019+", e o ROADMAP dizia 2021+. O dado decide: a coluna está ausente em 2015; presente mas com 0,25% a 0,57% de preenchimento no silver em 2016-2020 (2019: 0,25%); e 100% preenchida de 2021 a 2024. A coluna só é utilizável a partir de 2021. Ver docs/relatorio_qualidade_silver.md.

ADR-004 — Detecção de severidade por VALOR (swap tipo/natureza + rename)

As colunas tipo e natureza trocaram de significado entre 2015 (tipo=severidade, natureza=espécie) e 2024 (invertido). Como não sabemos em que ano exato o swap ocorreu, o transform detecta qual coluna é severidade inspecionando os valores (subconjunto de {SEM VÍTIMA, COM VÍTIMA, VÍTIMA FATAL}), não pelo nome nem pelo ano. Falha alto (erro explícito) se nenhuma coluna bater.

Atualização (achado ao rodar 2016 real): 2016 usa o mesmo layout semântico de 2015 (espécie em tipo), mas a coluna de severidade se chama natureza_acidente, não natureza — um terceiro nome de coluna para o mesmo conceito. A detecção foi generalizada para considerar tipo, natureza e natureza_acidente como candidatas. Além disso, 2016 tem 147 linhas com severidade vazia — tratado como dado ausente legítimo (conta na métrica severidade_vazia_no_silver), não como erro que quebra o pipeline.

Atualização (achado ao rodar 2018 real): a coluna de data aparece como DATA (maiúscula) em 2018, não data. Corrigido normalizando TODOS os nomes de coluna para minúsculas logo na leitura do CSV (_detecta_coluna_* e o resto do pipeline continuam usando nomes minúsculos). Padrão geral: o portal varia nome e caixa de coluna entre anos.

Atualização (achado ao rodar 2019 real): a coluna natureza_acidente tinha 2 linhas (de ~12.000) com valores "ENTRADA E SAÍDA" e "APOIO" — ruído pontual, provavelmente vazado de outro campo administrativo. A checagem original exigia que todos os valores únicos fossem válidos, o que quebrava com qualquer contaminação, por menor que fosse. Trocado para um limiar de proporção de linhas (LIMIAR_SEVERIDADE_VALIDA = 0.95): a coluna é aceita se ≥95% das linhas preenchidas baterem com SEVERIDADE_VALIDAS, e as linhas fora do padrão são contadas na métrica severidade_ruido_no_bruto em vez de quebrar o pipeline ou serem escondidas. Ressalva: 95% foi escolhido por julgamento (bem acima do ruído real de ~0,02% em 2019, bem abaixo do ponto onde eu confiaria numa coluna errada) — não é um valor derivado estatisticamente. Se anos futuros tiverem mais ruído legítimo, revisar o limiar.

ADR-005 — Filtro de qualidade: só situacao == FINALIZADA

situacao é o status do chamado, não do acidente. CANCELADA, DUPLICIDADE, EM ATENDIMENTO, PENDENTE e EM ABERTO não são acidentes confirmados. O silver mantém só FINALIZADA. O bronze preserva tudo (filtro é não-destrutivo). O número de descartados vira métrica de CloudWatch e é documentado (em 2015, ~29%).

ADR-006 — Vazio em contagem → 0, mas nunca em vitimasfatais

Célula vazia numa contagem de veículo (moto, auto, ...) é interpretada como 0 ("tipo não envolvido"), com base no padrão de preenchimento observado (muitos vazios, quase nenhum "0" explícito). É inferência, documentada. NÃO se aplica a vitimasfatais: ali, ausência é NULO, porque houve mortes em anos sem a coluna e afirmar 0 seria fabricar dado.

ADR-007 — vitimas mantido cru; sem "total de vítimas" derivado

O dicionário oficial afirma que antes de 2017 vitimas inclui os fatais. O dado de 2015 desmente: as 24 linhas fatais têm vitimas=0. Como a regra do dicionário não se confirma, não derivamos um "total de vítimas" — seria apoiar num número que o dado não sustenta. vitimas fica cru, com a ressalva registrada.

ADR-008 — Análise agregada por bairro (sem geocoding)

Os CSVs não têm latitude/longitude — só localização em texto (bairro, endereço). Mapa de pontos exigiria geocoding (custo, rate limit — fura o custo zero). A análise mira agregação por bairro (campo categórico limpo após normalização). Decisão de escopo consciente.

ADR-009 — O dicionário oficial está desatualizado; o dado real é a verdade

O JSON de metadados do portal só documenta o layout de ~2015, ignora as 18 colunas novas de 2024, lista IDs de recurso antigos e diverge da página do dataset na frequência de atualização (JSON diz "trimestral", página diz "semestral"). Tratamos o dado real como fonte de verdade e o dicionário como referência a ser verificada, não confiada cegamente.

ADR-010 — Ordem de construção da Fase 2 (por dependência)

A ordem do Terraform decorre da cadeia de dependência entre recursos, não de preferência: buckets S3 → VPC/subnet/Gateway Endpoint → IAM → CloudWatch, e depois Lambda (Fase 3). Justificativa:

Buckets não dependem de nada e são referenciados por todo o resto → base.
VPC/Endpoint dependem só de si mesmos.
IAM referencia os ARNs dos buckets nas políticas least-privilege → só pode vir depois dos buckets existirem.
CloudWatch (log group) é quase independente; destino das métricas do transform.
Lambda amarra tudo (role IAM + VPC + buckets + CloudWatch) → por último.

Nota de custo: nesta arquitetura, nada tem cobrança por hora quando ocioso (S3 = por GB armazenado ~centavos; Lambda = por invocação; VPC/subnet/ Endpoint/IAM = grátis). O terraform destroy por sessão é mais disciplina/ higiene e demonstração de portfólio do que necessidade de custo — mas permanece obrigatório pelos três motivos (hábito profissional, portfólio, proteção contra recurso caro adicionado por engano).

ADR-011 — State remoto via bootstrap em dois estágios

Escolhido state remoto (S3 + lock) em vez de state local, apesar de o projeto ser solo (backend remoto existe para evitar conflito de state entre membros de um time — necessidade funcional ausente aqui). Motivo: é portfólio — igual à VPC (ADR-001), a demonstração é o ponto, não a necessidade.

O bucket de state precisa existir antes do Terraform poder usá-lo como backend (problema "ovo e galinha"). Resolvido em dois estágios: uma config Terraform pequena, com state local, cria só o bucket+lock; a config principal usa esse bucket como backend remoto. Consequência prática: o backend de state é infra durável e grátis (poucos KB + requisições de lock) que SOBREVIVE ao terraform destroy de cada sessão; todo o resto (buckets de dado, VPC, Lambda) é infra efêmera, destruída e recriada a cada sessão.

Atualização (verificado na doc oficial em 21/08/2026) — mecanismo de lock RESOLVIDO: lock nativo do S3, via use_lockfile = true. Sem DynamoDB.

O "a verificar" acima está fechado. A doc atual do backend s3 marca dynamodb_table e dynamodb_endpoint como "(Optional, Deprecated)" e afirma: "DynamoDB-based locking is deprecated and will be removed in a future minor version". O argumento use_lockfile entrou como experimental no Terraform 1.10 e virou GA no 1.11. Nas versões atuais (1.12+) o dynamodb_table ainda funciona, mas com warning — ainda não foi removido. Escolher DynamoDB hoje seria adotar deliberadamente o caminho em vias de extinção.

Por que o DynamoDB existia ali: um lock é uma operação atômica de "criar se não existir". O S3 historicamente não tinha essa primitiva — PutObject sempre sobrescreve — então o Terraform pegou emprestada a escrita condicional do DynamoDB (attribute_not_exists). A tabela nunca guardou state; só o registro de "alguém está aplicando agora". Em ago/2024 o S3 ganhou conditional writes (header If-None-Match: *), que é exatamente a primitiva que faltava. O lock nativo grava um objeto <key>.tflock ao lado do state e o apaga ao terminar. A muleta deixou de ser necessária.

Consequências práticas:

Estágio 0 cria UM recurso durável (o bucket), não dois. Lock virou flag de configuração, não infraestrutura.
Requisito de versão: Terraform >= 1.11 (GA). Não usar 1.10, onde é experimental.
IAM (quando chegarmos lá): no objeto do lock, s3:GetObject + s3:PutObject + s3:DeleteObject. No objeto do state, NÃO é preciso s3:DeleteObject — a doc nota que o Terraform nunca apaga o state.
Custo: não foi o motivo. Uma tabela de lock caberia no always-free do DynamoDB (25 GB + 25 unidades), então o caminho antigo também sairia US$ 0,00. O ganho é arquitetural — um serviço a menos, uma política a menos, e nenhum risco de o argumento sumir num upgrade futuro.

Não verificado (irrelevante para este projeto, mas não afirmar sem checar): se o lock nativo dá as mesmas garantias do DynamoDB em cenário multi-região ou cross-account. Aqui é solo, uma região, uma conta.

ADR-012 — Versionamento no bucket de state

O bucket de state tem versionamento habilitado. Motivo: o lock protege contra escrita concorrente, mas não contra state corrompido, truncado ou apagado por engano — são problemas diferentes. Sem versionamento, um state danificado significa reimportar recurso por recurso na mão. Com versionamento, é restaurar a versão anterior do objeto.

Isso vale mais neste projeto do que no caso comum, porque o miolo da infra é destruído e recriado a cada sessão (ADR-011): o state é gravado com muito mais frequência que o normal, e é a única coisa que liga o código aos recursos reais.

Custo: o bucket guarda poucos KB. Mesmo com dezenas de versões acumuladas, continua na faixa de fração de centavo. Não justifica regra de ciclo de vida por ora — se um dia justificar, é sinal de que algo está errado.

ADR-013 — Credenciais: usuário IAM com access key, e NÃO IAM Identity Center

O Terraform autentica na AWS por um usuário IAM dedicado (terraform-recife-sinistros) com AdministratorAccess e uma access key de longa duração, configurada por aws configure no perfil default. O provider lê da credential chain; nenhuma credencial aparece em arquivo .tf.

Esta decisão contraria a recomendação atual da AWS, que é eliminar chaves de longa duração em favor de credenciais temporárias via IAM Identity Center. O motivo é de custo, não de mérito técnico, e está registrado aqui porque a escolha parece errada sem o contexto.

Por que o IAM Identity Center foi descartado (verificado na doc oficial em 26/08/2026):

Instância de CONTA não resolve. A tabela de comparação oficial marca "Multi-account permissions" e "AWS access portal for single-sign on access to your AWS accounts" como NÃO para instância em conta standalone. Sem permission set dando acesso à conta, não há o que o aws configure sso consuma. Instância de conta serve para atribuição de aplicações, não para credenciais de CLI.
Instância de ORGANIZAÇÃO custaria os créditos. Ela exige uma AWS Organization. O FAQ do Free Tier afirma: "When your account joins an AWS Organization or sets up an AWS Control Tower landing zone, your Free Tier credits expire immediately, and your account will be ineligible to earn more AWS Free Tier credits." Os créditos não migram para a fatura — são perdidos.

Consequência: habilitar o Identity Center custaria US$ 100 e a elegibilidade futura ao Free Tier, para mitigar um risco de segurança modesto num projeto solo. Isso viola a restrição inegociável do projeto (custo zero). Atenção prática: no console, o botão "Enable" do IAM Identity Center numa conta standalone leva à página "Enable IAM Identity Center with AWS Organizations", que cria a organização. É um clique de US$ 100 — não clicar nem por curiosidade.

Por que AdministratorAccess e não PowerUserAccess: a política gerenciada PowerUserAccess usa NotAction com iam:*, permitindo apenas iam:ListRoles e roles service-linked. A Fase 2 prevê criar role e políticas IAM para a Lambda (ADR-010) — com PowerUserAccess esse apply falharia com AccessDenied. Não é preguiça: o projeto legitimamente precisa criar IAM.

Por que não a chave do root: a AWS recomenda explicitamente não criar access key para o root. Chave de root vazada não tem teto de dano e não pode ser contida por política.

Mitigações adotadas:

Usuário IAM dedicado, sem acesso ao console — só API.
MFA registrado no usuário root (app autenticador no celular, com a secret key guardada fora do aparelho).
AWS Budget de gasto zero já ativo, alertando acima de US$ 0,01.
Credencial fora do repositório: mora em ~/.aws/, nunca em .tf; o .gitignore já cobre *.tfvars.
A chave deve ser revogada quando o projeto encerrar.

Condição que reverteria esta decisão: se a conta deixar de ser de créditos (créditos gastos ou expirados em 20/08/2027), o custo de criar uma Organization desaparece e o IAM Identity Center passa a ser a escolha certa. Revisar nessa data.

ADR-014 — Qualidade do silver: anomalias são sinalizadas, nunca corrigidas ou descartadas em silêncio

Rodando o transform nos 10 anos reais (2015-2024) em 09/10/2026, a validação encontrou anomalias que o transform ainda não tratava explicitamente (datas fora do ano, severidade vazia/fora do padrão, grafia de bairro inconsistente, vitimasfatais vazio em anos onde a coluna existe). A política adotada para todas elas é a mesma: **marcar e manter, nunca inventar e nunca descartar em silêncio**. Quando uma célula é reescrita, o valor original fica preservado numa coluna separada (sufixo `_original`), e uma coluna booleana sinaliza a anomalia.

1. **Data fora do ano do arquivo** (achado real: 32 linhas do arquivo de 2024, no silver pós-filtro FINALIZADA, com data em dez/2025 — causa desconhecida). Nova coluna booleana `data_fora_do_ano`. A data NÃO é corrigida — só sinalizada. Investigar a causa fica para a Fase 6 (análise), se for relevante.

2. **Severidade vazia ou fora do padrão** (achados reais: 4/13/4 linhas vazias em 2016/2017/2018; "ENTRADA E SAÍDA"/"APOIO" em 2019, "OUTROS" em 2021 — todas linhas FINALIZADA confirmadas, não ruído administrativo óbvio como em 2019 nem valor genérico do sistema como em 2021, mas em ambos os casos não é um dos três valores válidos). Decisão: `severidade` recebe "NÃO INFORMADO" (nunca inventa SEM VÍTIMA / COM VÍTIMA / VÍTIMA FATAL), o valor cru fica em `severidade_original`, e `severidade_anomala` (bool) sinaliza a linha. Optamos por manter a linha no silver (não excluir) porque são acidentes confirmados (situacao=FINALIZADA) — excluir apagaria acidentes reais da contagem por ano.

3. **Bairro: grafia/acento inconsistente entre anos** (achado real: "HIPÓDROMO" em 2015-2022 vs "HIPODROMO" em 2023-2024; 125 valores distintos no total). `bairro` passa por normalização determinística de acento (`unicodedata.normalize("NFD", ...)` removendo marcas combinantes — stdlib, sem dependência nova), e `bairro_original` preserva a grafia crua. O marcador "NÃO INFORMADO" é vocabulário controlado do próprio transform, não dado bruto, e fica de fora dessa normalização (senão virava "NAO INFORMADO" sem acento, inconsistente com o resto do código). Resultado real: 125 → 98 valores distintos após normalizar — perto dos 94 bairros oficiais do Recife (confirmado via busca externa: Diário de Pernambuco, jul/2024) + "NÃO INFORMADO". Os ~4 restantes (ex.: "IPESEP" vs "IPSEP", "JOANA BEZERRA" vs "ILHA JOANA BEZERRA") são variações de nome reais, não acento — não foram corrigidos, porque exigiriam um de-para por julgamento (adivinhação), não uma regra determinística. Fica como pendência conhecida (ver ROADMAP).

   Avaliamos e **não aplicamos** recuperar bairro vazio a partir do texto do endereço (achado real: 2019 tem 148 linhas com bairro vazio no bruto, 145 com endereço preenchido). Testamos casamento por substring do nome do bairro dentro do endereço: só 12/145 (8%) casaram, com falso-positivo claro (ex.: "AV JOAO DE BARROS" casa com o bairro "BARRO", errado). Não é confiável sem uma base de ruas real — fora do escopo de custo zero. Fica registrado como pendência.

4. **`vitimasfatais` vazio quando a coluna existe** (achado real: coluna presente mas vazia em >99% das linhas em 2016-2020; 2015 não tem a coluna; 2021+ está 100% preenchida). A regra de ADR-003/ADR-006 (ausência de coluna => NULO) continua, e passa a valer também para a CÉLULA vazia: vazio => NULO (`pd.NA`), via parser próprio (`_to_int_ou_na`), separado do `_to_int` das contagens de veículo, que continuam com vazio => 0.

   **Revisão de 20/10/2026** — a primeira versão deste item (09/10) fazia o oposto: vazio => 0, sinalizado numa coluna `vitimasfatais_inferido`. Revertido porque, na prática, 2016-2020 saíam do silver como "zero mortes", e quem soma a coluna sem ler a flag recebe um número fabricado. O dado não distingue "zero mortes" de "não apurado", então a única leitura honesta é "desconhecido". A coluna `vitimasfatais_inferido` foi removida do silver (com NULO não há inferência a sinalizar); no lugar dela entrou a métrica `vitimasfatais_vazias_no_silver` (None quando a coluna nem existe no ano).

   Observação que continua valendo, e que explica por que a versão de 09/10 era tentadora: nos anos 2016-2020, as poucas células preenchidas são quase todas ≥1, o que sugere que a CTTU preenchia o campo só quando havia morte. Isso é hipótese, não fato verificado. Para contar mortes nesses anos, o caminho que o dado sustenta é a severidade (`VÍTIMA FATAL`), não somar `vitimasfatais`.

5. **Persistência do silver**: `data/silver/sinistros_<ano>.csv` (CSV, não Parquet — zero dependência nova, simplicidade, projeto pequeno; `pyarrow` ficaria pendente para quando/se o volume ou a necessidade de tipos nativos justificar). Já estava no `.gitignore` (dado derivado, não versionado — mesma lógica de `data/raw/`). Relatório de qualidade por ano em `docs/relatorio_qualidade_silver.md` (versionado, para citar).

Pendências conscientemente fora de escopo desta rodada (ver ROADMAP): variação de volume bruto entre anos (2019→2024) não investigada a fundo — hipótese de pandemia não confirmada, documentada como limitação, não "corrigida".

ADR-015 — Dedup técnico: só o que é comprovadamente registro em dobro

O silver remove apenas duplicados técnicos, depois do filtro FINALIZADA (ADR-005), por dois critérios aplicados nesta ordem, sempre mantendo a primeira ocorrência:

1. **Linha idêntica em todas as colunas do bruto**, comparando o texto cru (sem normalizar espaço, caixa ou acento — se diferir em qualquer caractere, não é duplicata). Métrica: `duplicados_linha_identica`.
2. **Mesmo protocolo repetido** entre as linhas que sobraram. Só se aplica a anos com protocolo nativo; o id sintético dos outros anos é único por construção. Métrica: `duplicados_protocolo`.

Por que depois do filtro: assim cada linha removida cai em uma única métrica — um par idêntico de CANCELADA conta como descartada, não como duplicata — e `linhas_entrada = linhas_silver + descartadas_nao_finalizada + duplicados_linha_identica + duplicados_protocolo`.

O que NÃO é removido: linhas parecidas que diferem em qualquer campo (ex.: mesmo local, data e hora, mas outro número de autos) e linhas de conteúdo igual com protocolos diferentes. Num cruzamento movimentado, dois sinistros no mesmo minuto são plausíveis; sem uma chave que prove o contrário, removê-los apagaria acidente real. Não fazemos dedup "por semelhança".

Achados reais (20/10/2026, CSVs de data/raw/): `protocolo` só existe em 2022-2024, e nesses anos não há nenhum protocolo repetido. Linhas idênticas: 1 par em 2017 e 1 par em 2021 (ambos FINALIZADA, mesma data/hora/endereço/contagens); 0 nos outros anos. Ou seja, a dedup removeu 2 linhas em 10 anos.

Ressalva sobre o critério 2: "manter a primeira" é arbitrário quando o protocolo repete com conteúdo DIFERENTE (pode ser uma correção posterior do chamado, e aí a última seria a certa). Como hoje há zero casos reais, a escolha não afeta nenhum número. Se aparecer caso real, inspecionar antes de confiar na regra.

ADR-016 — Dashboard (Entregável 4): Streamlit local lendo o silver, regras de honestidade e critério de casamento de bairro

Primeira versão do dashboard em `app/dashboard.py` (Streamlit + Plotly), lendo `data/silver/sinistros_consolidado.csv` direto — sem backend, sem banco. A lógica de dados fica em `app/dados_painel.py` (pandas puro, testada em `tests/test_dashboard.py`) e a paleta em `app/tema.py`. Roda local, custo zero; não toca a AWS.

**Narrativa.** A pergunta é "onde estão os pontos críticos e o que os caracteriza". De cima para baixo: título que afirma o achado com o número (calculado sobre o recorte, nunca texto fixo), quatro indicadores, ranking + mapa (onde), série anual/mensal e hora × dia (quando), severidade (o que caracteriza), e uma lista "Como ler este painel" com todas as limitações. Filtros de ano, bairro e severidade na barra lateral, combináveis, aplicados a todos os gráficos; clicar numa barra do ranking filtra a página por aquele bairro. Recorte vazio mostra um aviso no lugar dos gráficos, sem quebrar.

**Regras de honestidade embutidas no código** (cada uma visível no painel, não só aqui):

1. O filtro FINALIZADA já está no silver (ADR-005) e não é reaplicado.
2. Fatais são contados pela severidade "VÍTIMA FATAL", nunca somando `vitimasfatais` (ADR-003/ADR-014). A faixa 2016–2020 aparece marcada nos gráficos de severidade.
3. A queda 2019→2021 é mostrada como queda de **registro**, com causa desconhecida. Achado ao montar o painel: quase toda a queda está nos chamados SEM VÍTIMA (8.046 em 2019 → 434 em 2021), enquanto os COM VÍTIMA variam menos (2.036 → 1.631). Isso reforça que mudou o que é registrado; não prova a causa.
4. Títulos de gráfico são calculados sobre o recorte e só afirmam o que o recorte sustenta. Achado ao testar: com Boa Viagem + só COM VÍTIMA, o título anual dizia "os registros caem -3%" quando o recorte subia (180 → 186). Corrigido, com teste de regressão.
5. "NÃO INFORMADO" em bairro entra nos totais e sai de ranking, mapa e % de concentração; a cobertura do mapa (quantos ficaram de fora e por quê) é exibida sob o mapa.
6. Os números de "linhas de entrada" do relatório (12.062 → 4.092 → 2.380) são do bruto; o painel mostra o silver (10.109 → 3.496 → 2.095) e cita os dois na nota.
7. A série mensal exclui as 32 linhas com `data_fora_do_ano` (dez/2025 no arquivo de 2024); elas continuam nos totais, e a nota diz quantas.
8. 2022 não tem hora em nenhuma linha (2.391); o mapa de calor diz quantos registros ficaram de fora.

**Critério de casamento bairro (CSV) × malha oficial.** Malha: GeoJSON "Bairros do Recife" do dataset "Área urbana" do portal (ODbL), 94 bairros, baixado por `src/baixa_malha_bairros.py` para `data/geo/` (não versionado, como `data/raw/`). Medido em 30/10/2026:

- Normalização determinística dos dois lados (`normaliza_nome`: sem acento, maiúscula, só letras/dígitos, espaço simples). A chave da malha vem de `EBAIRRNOME`; `EBAIRRNOMEOF` (nome com acento) **não** é usada porque vem corrompida do próprio portal (caractere U+FFFD no lugar de acento, ex.: "S�o Jos�"). O nome exibido no painel é a grafia crua mais frequente do silver (`bairro_original`).
- Só com normalização: **8 de 97 grafias do CSV não casam (8,2%), 1.057 registros (1,8%)**.
- De-para explícito de 5 grafias (`ALIAS_MALHA`), aplicado **só no painel** — o silver não muda: BAIRRO DO RECIFE→RECIFE, JOANA BEZERRA→ILHA JOANA BEZERRA, ALTO SANTA TERESINHA→ALTO SANTA TEREZINHA, POCO DA PANELA→POCO, IPESEP→IPSEP. Critério para entrar: o nome do CSV não existe na malha **e** o nome da malha não aparece no CSV (conjuntos complementares), ou é erro de digitação de uma letra com 1 registro (IPESEP). É julgamento, não regra — por isso a lista é curta, explícita e reversível, e o painel reporta os dois números.
- Depois do de-para: **3 de 97 não casam (3,1%), 3 registros** (SETUBAL, MARCELO, FABIO — não são bairros oficiais) e ficam fora do mapa. 2 bairros da malha não têm nenhum registro (PAU FERRO, PEIXINHOS) e aparecem com 0.
- Relação com ADR-014: lá o de-para foi recusado **no silver** (que é fonte para qualquer uso). Aqui ele é uma camada de apresentação, documentada e medida; o silver segue sem julgamento.

**Decisões visuais.**

- Paleta restrita: texto `#1F1F1D`, texto secundário `#4F4E4A`, fundo `#F7F7F5` (lateral `#EDECE8`), uma cor de destaque (azul `#256ABF`) para a série principal, cinza `#C4C3BE` para marca secundária. Sem arco-íris, sem 3D, sem pizza, eixos começando em zero.
- Sequencial de tom único (azul) em **6 classes discretas**, não rampa contínua. Motivo medido: numa rampa contínua há uma faixa de azul médio (~`#337FDA`) onde nem texto escuro nem branco chegam a 4,5:1 (pior caso 4,08:1) — e o mapa de calor tem número dentro de cada célula. As classes pulam essa faixa: as três claras levam texto escuro, as três escuras levam branco.
- **Contraste mínimo de texto medido: 5,39:1** (branco sobre o azul de destaque, nos rótulos dentro das barras e nas classes escuras). Texto principal sobre o fundo: 15,4:1; secundário: 7,8:1. Teste automatizado garante ≥ 4,5:1 em todos os pares.
- Cor nunca é o único portador: barras e células com valor rotulado; severidade com legenda + rótulo de % + hachura em "não informado"; 2015 em azul claro **e** rotulado "parcial" / "jun–dez". O mapa não tem rótulos de texto (sobrepunham-se no centro); os valores estão no ranking ao lado, na mesma ordem, e no hover.
- Hierarquia tipográfica: título 30px > achado 19px > indicador 28px/13px > título de gráfico 17px/13px > nota 12px; espaçamento numa grade de 8px. Cada gráfico tem título que afirma algo, subtítulo com o recorte, unidade no eixo e o n daquele recorte.
- Rodapé fixo com fonte, período, data de extração (data dos CSVs em `data/raw/` e do silver), total e link para o relatório de qualidade.

**Fatais em 2015.** A coluna `vitimasfatais` não existe em 2015, mas a severidade existe: o gráfico de fatais inclui 2015 (23 chamados), marcado como ano parcial.

Pendências: normalizar por área ou população do bairro (hoje é contagem absoluta, e o painel avisa); publicar o painel (hoje é local).

ADR-017 — Classificadores integrados ao painel (E6) e dois recortes de base rotulados

**Contexto.** O grupo entregou, fora do repositório, uma avaliação de classificadores que prevê se um bairro-mês terá ≥ 3 chamados. O material está em `entrega_classificadores/` e é o ZIP do grupo sem a pasta intermediária. O painel do E4 usa o silver (só FINALIZADA, ADR-005). Os classificadores usam todos os status. Medido no Passo 0 (13/11/2026), com uma replicação conferida contra as tabelas publicadas no ZIP:

- Silver: 59.006 chamados FINALIZADA. Base dos classificadores: 72.255 chamados, dos quais 59.008 FINALIZADA, 11.563 CANCELADA e 455 DUPLICIDADE. A diferença de 2 FINALIZADA vem da dedup do silver (ADR-015).
- O alvo usa só 2021–2024, com data válida e bairro com casamento **exato** no cadastro oficial de 94 bairros: 14.033 de 14.396 chamados da janela.
- O casamento de bairro também diverge. As 5 grafias que o ADR-016 aproveita no painel (BAIRRO DO RECIFE, JOANA BEZERRA, ALTO SANTA TERESINHA, POCO DA PANELA, IPESEP) não casam no classificador.
- Se o alvo contasse só FINALIZADA, o corte continuaria 3, mas 111 bairro-meses mudariam de classe: 62 no treino, 29 na validação e 20 no teste. Os positivos do teste iriam de 519 para 499. O cálculo é refeito por `tests/test_classificacao.py`.

**Decisão (opção a, escolhida pelo grupo em 13/11/2026).** Manter os dois recortes, cada um rotulado na sua página por um selo de cobertura. As alternativas foram descartadas:
- **(b) Alinhar tudo a FINALIZADA e retreinar.** Invalidaria todos os números entregues (84,4%, F1 0,845, matriz 473/136/40/479).
- **(c) Alinhar tudo a todos os status.** Reverteria o ADR-005 (cancelados e duplicados contariam como sinistros) e mudaria os números do E4 (59.006 → 72.255; top-10 de 46,0% para 45,4%).

**Integração.**
- `src/classificacao/` é uma porta fiel de `preparacao_cttu.py` e `classificacao_cttu.py`, reduzida ao necessário.
- **Reaproveita** os CSVs de `data/raw/`, que são byte a byte iguais aos do ZIP (SHA-256 conferido contra `manifesto_aquisicao.json`), e a malha de `data/geo/`, também idêntica.
- **Não reaproveita o silver**: isso mudaria o alvo.
- O cadastro oficial vai para `data/raw/bairros_oficiais.csv`, baixado por `src/baixa_malha_bairros.py`. O CSV pela URL do recurso é igual ao do ZIP; o "dump" do datastore vem em outro formato e não serve.
- `python src/classificacao/gerar_artefatos.py` grava `data/classificacao/`. Esses artefatos são versionados, como o relatório de qualidade, porque são o resultado oficial que painel e docs citam.
- O dashboard só lê os artefatos e nunca treina.

**Regressão.** Rodando em Python 3.14, pandas 3.0.5 e scikit-learn 1.9.1 (a entrega usou Python 3.12, pandas 2.2.3 e scikit-learn 1.8.0), a logística no teste reproduz os números entregues: 84,4% / 77,9% / 92,3% / F1 0,845 / AUC 0,945 / AP 0,940 / 473-136-40-479. Métricas, limiares, partições, métricas mensais e bootstrap são **idênticos** às tabelas do ZIP. As predições batem e os scores diferem em menos de 1e-12. Limiares, modelo e partições seguem fixados; o limiar exploratório da página não altera a tabela oficial.

**Achados sobre a entrega do ZIP.**
- `dados/chamados_tratados.csv.gz` está truncado: o CRC do ZIP confere e só 53.991 linhas descomprimem. Não é usado, porque é regenerável.
- O `requirements.txt` da entrega pede `pandas<3`; o painel roda em pandas 3 sem diferença nos resultados.

**Consequências.**
- Os números das duas páginas não se somam nem se comparam diretamente, e o painel diz isso.
- Na previsão, "Recife", "Ilha Joana Bezerra", "Alto Santa Terezinha", "Poco" e "Ipsep" contam só os chamados com o nome exato do cadastro.
- Ao abrir uma subpágina direto pela URL, o frontend do Streamlit registra 404 em `/<página>/_stcore/health` e `/<página>/_stcore/host-config`. O app não gera esses pedidos e funciona normalmente. Inferência: é o frontend testando caminhos-base.

ADR-018 — Merge do Ciclo 6 com a versão de página única (entrega CC de 18/11): carregamento, regra do mapa de calor e base empacotada

**Contexto.** O `master` local tinha os 8 commits do Ciclo 6 (painel multipágina, classificadores, ADR-017). O `origin/master` tinha o commit `d7222fc` do Artur, que partiu do estado do Ciclo 4 (`3f2d684`) e já foi apresentado na entrega CC: base empacotada em `data/painel/`, `src/prepara_dados_painel.py`, adaptação a celular e regra nova para o mapa de calor. Juntados por `git merge` (sem rebase nem force), com backups em `backup/ciclo6-local` e `backup/origin-artur`.

**1. Carregamento (estratégia única).** A página de pontos críticos lê `data/painel/sinistros.csv.gz` e `data/painel/bairros.geojson.gz` quando existem; se não existirem, cai para o silver local (`data/silver/`) e a malha de `data/geo/`. A previsão lê `data/classificacao/`. Os três diretórios são versionados, então uma cópia limpa (e o Streamlit Community Cloud) abre as três páginas sem rodar pipeline. A base empacotada vem primeiro porque é o que todo ambiente enxerga: o painel mostra os mesmos números em qualquer máquina. As contagens são idênticas às do silver (59.006; mesmo total por ano). O Artur usava a ordem inversa (silver primeiro); a ordem foi trocada por decisão do grupo no merge.

**2. Regra do mapa de calor.** Vale a regra da versão de 18/11. Entram só chamados com hora entre 0 e 23 **e** data no ano do arquivo; o resto é contado em "fora". Motivos:
- É coerente com a série mensal, que já exclui as 32 datas de outro ano (dez/2025) por não serem confiáveis. Se a data não é confiável, o dia da semana também não é.
- Fecha a conta: matriz + fora = total. A regra antiga do Ciclo 6 perdia 1 chamado do silver com hora `"29208:00"` (hora 29), que não entrava na matriz nem no "fora".

Efeito, medido: a base do mapa de calor vai de 56.567 para 56.535 e o pico de terça às 8h de 835 para 833. Os 75% entre 7h e 19h não mudam. O E6 ganhou uma errata, porque o relatório de 13/11 (`docs/entregas/Relatorio_Ciclo6_G15.pdf`) cita 835. A `docs/entrega-cc.md` já usava 833.

As "32" e as "36" datas de outro ano não são divergência: são 32 no recorte FINALIZADA e 36 em todos os status (32 + 2 CANCELADA + 2 DUPLICIDADE). Cada página mostra a do seu recorte.

**3. Base empacotada com uma coluna a mais.** A página de pontos críticos do Ciclo 6 mostra o preenchimento de `vitimasfatais` por ano, e a base do Artur não tinha a coluna. `src/prepara_dados_painel.py` passou a publicar `vitimasfatais`, com vazio = desconhecido (ADR-014), e a base foi regerada com o próprio script.
- As entradas são byte a byte as mesmas registradas pelo Artur (SHA-256 dos 10 CSVs e da malha conferidos). As colunas antigas da base ficaram idênticas.
- O script agora usa nomes canônicos no manifesto e preserva a `data_extracao` quando os hashes das entradas não mudam (18/11/2026).
- A malha regerada tinha conteúdo idêntico e só um byte diferente no cabeçalho do gzip (sistema operacional), então foi mantido o arquivo original do Artur.
- `src/baixa_malha_bairros.py` voltou a expor `DESTINO`, que o script do Artur importa e que o Ciclo 6 tinha removido. Era um conflito semântico que o git não acusou.

**4. O que entrou de cada lado.**
- **Estrutura do Ciclo 6:** três páginas, selo de cobertura, previsão.
- **Da versão de 18/11, nas três páginas:**
  - CSS para telas estreitas e celular (indicadores em duas colunas, gráficos empilhados, rótulos do mapa de calor ocultos com valor ao tocar);
  - títulos de gráfico em `h3` com texto escapado;
  - rodapé no fim da página, com a data de extração do `fontes.json`;
  - fundo-mundo do Plotly servido de `app/static/`, sem CDN;
  - série mensal com marcador quando há um mês só;
  - mensagens de recorte vazio e textos de título revistos.
- **Onde os dois lados tinham texto diferente, ficou a união:**
  - o título anual tem os números absolutos (18/11) e a leitura "queda de registro" (Ciclo 6);
  - o indicador de severidade mostra a contagem (18/11) e o percentual (Ciclo 6);
  - o título de severidade tem a proporção com uma casa decimal (18/11) e a leitura de que são os SEM VÍTIMA que somem (Ciclo 6).

Nenhuma funcionalidade foi removida.
