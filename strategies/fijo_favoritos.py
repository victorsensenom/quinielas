"""Una sola columna con el signo de mayor probabilidad de cada partido.

Fuente: % prob (de cuotas); si un partido no tiene prob, % lae; si tampoco, '1'.
Pleno: goles del favorito del partido 15 (1 gana -> 2-1, X -> 1-1, 2 gana -> 1-2); si no hay
datos del pleno, 1-1.
"""
import numpy as np

from engine.strategy import Column, prob_matrix

PLENO_BY_SIGN = {0: (2, 1), 1: (1, 1), 2: (1, 2)}


def _pleno(info):
    p = info.pleno
    if p is None:
        return (1, 1)
    for src in (p.prob, p.lae):
        a = np.array(src, float)
        if not np.isnan(a).any() and a.sum() > 0:
            return PLENO_BY_SIGN[int(a.argmax())]
    return (1, 1)


def generate(info, history, budget_eur):
    if budget_eur < info.precio_apuesta:
        return []
    P = prob_matrix(info, "prob", "lae")      # sin datos -> uniforme -> argmax = '1'
    return [Column(tuple(int(x) for x in P.argmax(1)), _pleno(info))]
