"""
Classificadores de volume elevado de chamados por bairro-mês (ADR-017).

Porta, para dentro do repositório, a avaliação entregue pelo grupo em
entrega_classificadores/ (preparacao_cttu.py + classificacao_cttu.py), sem
alterar limiares, modelo selecionado nem partições. Gera os artefatos que a
página "Previsão de volume elevado" do dashboard lê (data/classificacao/).

    preparacao.py      base por chamado, a partir de data/raw/
    modelos.py         painel bairro-mês, treino, métricas e artefatos
    gerar_artefatos.py ponto de entrada de linha de comando
"""
