"""Estrategia "probabilidad condicionada": columnas elegidas con los % probables (prob1/X/2).

Idea: con los % probables de cada partido (de cuotas de apuestas) se asigna una probabilidad
a cada una de las 3^14 combinaciones posibles (partidos independientes). Opcionalmente se
CONDICIONA esa distribucion a combinaciones "tipicas" (nº de 1/X/2 dentro de un rango y pocas
sorpresas), con rangos aprendidos SOLO del historico anterior a la jornada (``history``).
Despues se eligen K columnas:
    radio=0 -> las K combinaciones mas probables (objetivo 14)
    radio=1 -> greedy_cover: maximiza P(>=13 aciertos)
    radio=2 -> greedy_cover: maximiza P(>=12 aciertos)

Parametros (--param k=v):
    K         columnas (por defecto las que permite el presupuesto: 48 EUR / 0,75 = 64)
    radio     0 | 1 | 2 (por defecto 1)
    filtro    'none' | 'abs' | 'resid'   filtro por nº de 1/X/2 (por defecto 'none')
                abs   = rango [q, 1-q] de los conteos reales del historico
                resid = conteo esperado de esta jornada (suma de probs) + cuantiles [q, 1-q] del
                        residuo (real - esperado) del historico. Es la version "condicionada".
    sorp      'off' | 'auto' | entero    maximo de sorpresas (signos con prob < umbral);
                auto = cuantil 1-q del nº de sorpresas reales en el historico
    umbral    prob por debajo de la cual un signo es sorpresa (por defecto 0.30)
    q         cola de los cuantiles (por defecto 0.05)
    condicionar  True: ademas de restringir nuestras columnas al filtro, se anula la probabilidad
                 de los resultados fuera del filtro al medir la cobertura. False: solo restringe
                 las columnas (la cobertura se mide sobre todos los resultados).
    min_hist  jornadas de historico necesarias para activar filtros (por defecto 40)
    pleno     'hist' (resultado de goles mas frecuente en el historico previo) o fijo, p.ej. '11'

Pleno al 15: el motor no expone pleno15.csv en JornadaInfo (y partidos.csv no trae % para el
partido 15), asi que se usa el resultado de goles mas frecuente en el historico previo.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from engine import reduce as R
from engine.data import GOAL_TO_CODE
from engine.strategy import prob_matrix

_COUNTS = None   # (n1, nX, n2) del espacio completo, se calcula una vez


def _space_counts():
    global _COUNTS
    if _COUNTS is None:
        _COUNTS = R.count_signs(None)
    return _COUNTS


def _bool(v):
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "yes")


class Strategy:
    def __init__(self, K=None, radio=1, filtro="none", sorp="off", umbral=0.30, q=0.05,
                 condicionar=True, min_hist=40, pleno="hist"):
        self.K = None if K in (None, "", "none") else int(K)
        self.radio = int(radio)
        self.filtro = str(filtro)
        self.sorp = str(sorp)
        self.umbral = float(umbral)
        self.q = float(q)
        self.condicionar = _bool(condicionar)
        self.min_hist = int(min_hist)
        self.pleno = str(pleno)
        self._hcache = {}      # key -> (conteos reales (3,), esperados (3,), sorpresas reales)
        self.last_info = {}    # diagnostico de la ultima jornada

    # ------------------------------------------------------------------ historico
    def _hstats(self, j):
        k = (j.temporada, j.jornada)
        if k not in self._hcache:
            P = prob_matrix(j.info)
            s = np.asarray(j.signos, int)
            real = np.bincount(s, minlength=3)
            esp = P.sum(0)
            nsor = int((P[np.arange(14), s] < self.umbral).sum())
            self._hcache[k] = (real, esp, nsor)
        return self._hcache[k]

    def _pleno(self, history):
        if self.pleno != "hist":
            p = self.pleno.upper().replace("-", "")
            return (GOAL_TO_CODE[p[0]], GOAL_TO_CODE[p[1]])
        c = Counter(tuple(j.pleno_res) for j in history if j.pleno_tipo == "goals")
        return c.most_common(1)[0][0] if c else (1, 1)

    # ------------------------------------------------------------------ generate
    def generate(self, info, history, budget_eur):
        K = int(budget_eur // info.precio_apuesta + 1e-9)
        if self.K is not None:
            K = min(K, self.K)
        if K <= 0:
            return []
        P = prob_matrix(info, "prob", "lae")
        w = R.space_weights(P)
        hist = [j for j in history if j.is_complete()]
        mask = None
        rng = {}
        if len(hist) >= self.min_hist and (self.filtro != "none" or self.sorp != "off"):
            stats = [self._hstats(j) for j in hist]
            real = np.array([s[0] for s in stats], float)
            esp = np.array([s[1] for s in stats], float)
            mask = np.ones(R.TOTAL, bool)
            if self.filtro in ("abs", "resid"):
                cnt = _space_counts()
                if self.filtro == "abs":
                    lo = np.floor(np.quantile(real, self.q, axis=0))
                    hi = np.ceil(np.quantile(real, 1 - self.q, axis=0))
                else:
                    res = real - esp
                    e = P.sum(0)
                    lo = np.floor(e + np.quantile(res, self.q, axis=0))
                    hi = np.ceil(e + np.quantile(res, 1 - self.q, axis=0))
                for k in range(3):
                    mask &= (cnt[k] >= lo[k]) & (cnt[k] <= hi[k])
                rng["n1"], rng["nX"], rng["n2"] = [(int(lo[k]), int(hi[k])) for k in range(3)]
            if self.sorp != "off":
                if self.sorp == "auto":
                    ms = int(np.ceil(np.quantile([s[2] for s in stats], 1 - self.q)))
                else:
                    ms = int(self.sorp)
                mask &= R.surprises(P, self.umbral) <= ms
                rng["max_sorp"] = ms
            if mask.sum() < K:          # filtro demasiado estricto: se ignora
                mask = None
                rng["ignorado"] = True
        self.last_info = rng

        if mask is not None and self.condicionar:
            w = np.where(mask, w, 0.0)
        cand = None if mask is None else np.flatnonzero(mask)
        if self.radio == 0:
            ww = w if cand is None else w[cand]
            top = np.argpartition(-ww, K - 1)[:K]
            sel = top if cand is None else cand[top]
        else:
            sel = R.greedy_cover(P, K, radius=self.radio, candidates=cand, w=w)
        return R.to_columnset(sel, self._pleno(history))
