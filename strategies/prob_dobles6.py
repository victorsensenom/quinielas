"""Referencia: multiple "al directo" de 6 dobles y 8 fijos (2^6 = 64 columnas = 48 EUR).

Fijo = signo mas probable segun % probables. Los 6 dobles van a los 6 partidos con el favorito
mas debil (menor probabilidad maxima) y cubren sus 2 signos mas probables.
Pleno: resultado de goles mas frecuente en el historico previo (como prob_condicionada).

Parametros: dobles (por defecto 6).
"""
from collections import Counter

import numpy as np

from engine import reduce as R
from engine.strategy import prob_matrix


class Strategy:
    def __init__(self, dobles=6):
        self.dobles = int(dobles)

    def generate(self, info, history, budget_eur):
        P = prob_matrix(info, "prob", "lae")
        order = np.argsort(-P, axis=1)
        weak = set(np.argsort(P.max(1))[: self.dobles].tolist())
        base = [[int(order[i, 0]), int(order[i, 1])] if i in weak else [int(order[i, 0])] for i in range(14)]
        idx = R.expand_base(base)
        k = int(budget_eur // info.precio_apuesta + 1e-9)
        if len(idx) > k:
            raise ValueError(f"{len(idx)} columnas no caben en {budget_eur} EUR")
        c = Counter(tuple(j.pleno_res) for j in history if j.pleno_tipo == "goals")
        pleno = c.most_common(1)[0][0] if c else (1, 1)
        return R.to_columnset(idx, pleno)
