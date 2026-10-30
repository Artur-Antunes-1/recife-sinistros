"""
tema.py
-------
Paleta do dashboard e o cálculo de contraste WCAG usado para escolher cor de
texto sobre células coloridas (mapa de calor, mapa) e para verificar o
contraste mínimo do painel (ver ADR-016).

Paleta restrita de propósito: dois cinzas de texto, um neutro claro de fundo,
UMA cor de destaque (azul) e a rampa sequencial do mesmo azul. Cinza claro
para marcas secundárias. Nada além disso.
"""

from __future__ import annotations

# Texto
TEXTO = "#1F1F1D"        # títulos, valores
TEXTO_2 = "#4F4E4A"      # subtítulos, eixos, notas

# Superfícies
FUNDO = "#F7F7F5"        # fundo da página e dos gráficos
LATERAL = "#EDECE8"      # barra lateral
GRADE = "#E2E1DC"        # linhas de grade, bairros sem dado no mapa

# Marcas
DESTAQUE = "#256ABF"         # série principal (azul, passo 500)
DESTAQUE_CLARO = "#9EC5F4"   # mesma série, valor com ressalva (2015 parcial)
CINZA_MARCA = "#C4C3BE"      # marca secundária (SEM VÍTIMA)
ESCURO = "#0D366B"           # VÍTIMA FATAL (fim da rampa azul)
BRANCO = "#FFFFFF"

# Rampa sequencial de tom único (azul, claro -> escuro), para mapa e calor,
# em CLASSES discretas, não contínua. Motivo medido: numa rampa contínua há
# uma faixa de azul médio (~#337FDA) onde nem o texto escuro nem o branco
# chegam a 4,5:1 (pior caso 4,08:1). As classes pulam essa faixa: as três
# claras levam texto escuro (>= 6,6:1), as três escuras levam branco (>= 5,39:1).
RAMPA = ["#CDE2FB", "#9EC5F4", "#6DA7EC", "#256ABF", "#184F95", "#0D366B"]

FONTE = '"Source Sans Pro", "Source Sans 3", "Segoe UI", sans-serif'


def _rgb(hexcor: str) -> tuple[int, int, int]:
    h = hexcor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminancia(hexcor: str) -> float:
    """Luminância relativa (WCAG 2.x)."""
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rgb(hexcor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    """Razão de contraste WCAG entre duas cores (1 a 21)."""
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def cor_na_rampa(t: float) -> str:
    """Classe da RAMPA para a posição t (0..1) — a mesma que escala_plotly()
    pinta. A classe i cobre [i/n, (i+1)/n)."""
    t = min(max(t, 0.0), 1.0)
    return RAMPA[min(int(t * len(RAMPA)), len(RAMPA) - 1)]


def texto_sobre(fundo: str) -> str:
    """Entre TEXTO e BRANCO, o que contrasta mais com o fundo dado."""
    return TEXTO if contraste(TEXTO, fundo) >= contraste(BRANCO, fundo) else BRANCO


def escala_plotly() -> list[list]:
    """Escala em degraus: cada cor vale de i/n até logo antes de (i+1)/n.
    O recuo de 1e-9 garante que um valor exatamente na fronteira caia na
    classe de cima, igual a cor_na_rampa() — senão a cor do texto escolhida
    poderia não bater com a cor pintada."""
    n = len(RAMPA)
    escala = []
    for i, c in enumerate(RAMPA):
        escala += [[i / n, c], [(i + 1) / n - (1e-9 if i < n - 1 else 0), c]]
    return escala
