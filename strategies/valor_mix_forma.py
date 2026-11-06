"""valor_mix_forma: valor_mix con filtro de "forma de jornada".

Igual que valor_mix (pesos p^(a+b)/lae^b, greedy_cover), pero solo se admiten como candidatas
las columnas cuya forma se parece a la de una jornada real:
  * nº de favoritos (signo de mayor % probable del partido) entre fav_min y fav_max;
  * nº de "sorpresas gordas" (signo de MENOR % probable del partido) entre sorp_min y sorp_max.
Historico 2017-2026: ganan 5-10 favoritos en ~80 % de las jornadas (media ~7,5) y salen 1-5
sorpresas gordas en ~92 %.

Parametros (--param): a (1), b (0.5), radius (1), n, fav_min (0), fav_max (14), sorp_min (0),
sorp_max (14), cal (0|1: usar % corregidos de strategies.calibracion para pesos y forma),
hasta (como en valor_mix_cal).
"""
import math

import numpy as np

from engine.reduce import N, _ball_mass_factor, _outer_reduce, greedy_cover, normalize, space_weights, to_columnset
from engine.strategy import prob_matrix

from strategies import valor_model as vm
from strategies.valor_ev import _opt


def forma_counts(P):
    """(nfav, nsorp) para las 3^14 columnas (int8). Favorito = argmax de P, sorpresa = argmin."""
    P = np.asarray(P, float)
    F = np.zeros((N, 3), np.int8)
    S = np.zeros((N, 3), np.int8)
    F[np.arange(N), P.argmax(1)] = 1
    S[np.arange(N), P.argmin(1)] = 1
    return _outer_reduce(F, np.add, np.int8), _outer_reduce(S, np.add, np.int8)


def candidatos(P, fav=(0, 14), sorp=(0, 14), counts=None):
    nf, ns = forma_counts(P) if counts is None else counts
    ok = (nf >= fav[0]) & (nf <= fav[1]) & (ns >= sorp[0]) & (ns <= sorp[1])
    return np.flatnonzero(ok).astype(np.int64)


def select_forma(M, n, radius, cand, w=None, top=200_000):
    """greedy_cover restringido a ``cand``. Para ir rapido se pasa solo el top de candidatos por
    ganancia inicial g0 = w*f (cota superior de la ganancia real). El resultado es EXACTAMENTE el
    de greedy_cover(M, n, candidates=cand) si cada ganancia elegida >= mayor g0 excluido; si no se
    cumple, se repite con todos los candidatos."""
    if cand is None:
        return greedy_cover(M, n, radius=radius, w=w)
    P = normalize(M)
    w = space_weights(P) if w is None else w
    g0 = w[cand] * _ball_mass_factor(P, radius)[cand]
    if len(cand) > top:
        part = np.argpartition(-g0, top)
        keep, rest = part[:top], part[top:]
        thr = float(g0[rest].max())
        sel, inf = greedy_cover(M, n, radius=radius, candidates=np.sort(cand[keep]), w=w, return_info=True)
        if len(sel) == n and min(inf["gains"]) >= thr:
            return sel
    return greedy_cover(M, n, radius=radius, candidates=cand, w=w)


class Strategy:
    def __init__(self, a=1.0, b=0.5, radius=1, n=None, fav_min=0, fav_max=14, sorp_min=0, sorp_max=14,
                 cal=0, hasta=None):
        self.a, self.b, self.radius = float(a), float(b), int(radius)
        self.n = _opt(n, int)
        self.fav = (int(fav_min), int(fav_max))
        self.sorp = (int(sorp_min), int(sorp_max))
        self.cal = bool(int(cal))
        self.hasta = _opt(hasta, int)

    def generate(self, info, history, budget_eur):
        price = info.precio_apuesta
        kmax = int(math.floor(budget_eur / price + 1e-9))
        n = min(self.n or kmax, kmax)
        if n <= 0:
            return []
        if self.cal:
            from strategies.valor_mix_cal import prob_cal
            P = prob_cal(info, self.hasta)
        else:
            P = prob_matrix(info, "prob", "lae")
        L = prob_matrix(info, "lae", "prob")
        M = vm.mix_matrix(P, L, self.a, self.b)
        cand = candidatos(P, self.fav, self.sorp)
        if len(cand) < n:          # filtro imposible en esta jornada -> sin filtro
            cand = None
        sel = select_forma(M, n, self.radius, cand)
        pleno = vm.pleno_choice(info)[0]
        return to_columnset(sel[:n], pleno)
