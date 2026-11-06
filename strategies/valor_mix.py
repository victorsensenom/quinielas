"""valor_mix: mezcla de probabilidad y valor, seleccion por cobertura (greedy_cover).

Peso de cada columna  ~  prob(c)^a x (prob(c) / lae(c))^b
    prob = % probables (de cuotas), lae = % jugado por el publico.
Como es un producto por partido, equivale a usar en cada partido p^(a+b) / lae^b normalizado,
y se pasa a ``engine.reduce.greedy_cover`` (maximiza la probabilidad -con esos pesos- de
quedar a distancia <= radius de alguna columna: radius 1 -> 13+, 2 -> 12+).
b = 0 es la estrategia de favoritos (solo probabilidad); b > 0 desplaza las columnas hacia
resultados probables pero poco jugados.

Parametros (--param): a (def. 1), b (def. 0.5), radius (1|2, def. 1), n (columnas, def.
presupuesto/precio), ev_min / ev_alto / n_alto (seleccion de jornadas con el EV estimado por
euro del modelo de valor, ver valor_ev.py).
Pleno al 15: marcador mas probable segun % probables de goles (data/pleno15.csv).
"""
import math

from engine.reduce import to_columnset
from engine.strategy import prob_matrix

from strategies import valor_model as vm
from strategies.valor_ev import _opt


class Strategy:
    def __init__(self, a=1.0, b=0.5, radius=1, n=None, ev_min=None, ev_alto=None, n_alto=None, alpha=vm.ALPHA):
        self.a, self.b, self.radius = float(a), float(b), int(radius)
        self.n = _opt(n, int)
        self.ev_min = _opt(ev_min)
        self.ev_alto = _opt(ev_alto)
        self.n_alto = _opt(n_alto, int)
        self.alpha = float(alpha)
        self.log = []

    def generate(self, info, history, budget_eur):
        price = info.precio_apuesta
        kmax = int(math.floor(budget_eur / price + 1e-9))
        n = min(self.n or kmax, kmax)
        if n <= 0:
            return []
        n_hi = min(self.n_alto, kmax) if (self.ev_alto is not None and self.n_alto) else n
        P = prob_matrix(info, "prob", "lae")
        L = prob_matrix(info, "lae", "prob")
        sel = vm.select_mix(P, L, max(n, n_hi), self.a, self.b, self.radius)
        pleno = vm.pleno_choice(info)[0]
        k = n
        if self.ev_min is not None or self.ev_alto is not None:
            m = vm.JornadaModel(info, history, alpha=self.alpha)
            ev_euro = float(m.EV[sel[:n]].sum()) / (n * price)
            if self.ev_min is not None and ev_euro < self.ev_min:
                k = 0
            elif self.ev_alto is not None and ev_euro >= self.ev_alto:
                k = n_hi
            self.log.append((info.temporada, info.jornada, ev_euro, k))
        if k == 0:
            return []
        return to_columnset(sel[:k], pleno)
