"""valor_mix_cal: igual que valor_mix pero con los % probables recalibrados.

Peso de cada columna ~ q(c)^a x (q(c) / lae(c))^b, con q = % probables corregidos por
``strategies.calibracion.corregir`` (temperatura + sesgo de 1/X/2 por grupo de partido; parametros
de data/calibracion.json estimados solo con temporadas anteriores). Seleccion con greedy_cover
(radius 1 -> 13+, 2 -> 12+), pleno como en valor_mix.

Parametros (--param): a (1), b (0.5), radius (1), n (columnas; def. presupuesto/precio),
hasta (ultima temporada de ajuste admitida; p. ej. 2022 = parametros fijos 2017-2022;
sin valor = walk-forward, el ajuste mas reciente anterior a la temporada).
"""
import math

import numpy as np

from engine.reduce import to_columnset
from engine.strategy import prob_matrix

from strategies import valor_model as vm
from strategies.calibracion import corregir
from strategies.valor_ev import _opt


def prob_cal(info, hasta=None):
    Q = corregir(info, None, hasta=hasta) / 100.0
    Q = np.maximum(Q, 1e-4)
    return Q / Q.sum(1, keepdims=True)


class Strategy:
    def __init__(self, a=1.0, b=0.5, radius=1, n=None, hasta=None):
        self.a, self.b, self.radius = float(a), float(b), int(radius)
        self.n = _opt(n, int)
        self.hasta = _opt(hasta, int)

    def generate(self, info, history, budget_eur):
        price = info.precio_apuesta
        kmax = int(math.floor(budget_eur / price + 1e-9))
        n = min(self.n or kmax, kmax)
        if n <= 0:
            return []
        P = prob_cal(info, self.hasta)
        L = prob_matrix(info, "lae", "prob")
        sel = vm.select_mix(P, L, n, self.a, self.b, self.radius)
        pleno = vm.pleno_choice(info)[0]
        return to_columnset(sel[:n], pleno)
