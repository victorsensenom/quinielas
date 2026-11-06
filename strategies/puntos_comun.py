"""Comun a puntos_a, puntos_b y puntos_ref: probabilidades del modelo y formas de boleto.

Modelos: 'prob' (% probables tal cual), 'A' (puntos propios), 'B' (cuotas + correccion).
Partidos sin datos de liga: A usa los % probables tal cual; B solo el ajuste general de los %.

Parametros de Strategy:
    forma   '6D' (6 dobles), '3T1D', '2T2D', '1T4D', 'auto45' (triple si favorito < 45 %, doble si no)
    valor   1 = el modelo alimenta a la seleccion de valor_mix (b=0.5) en vez de fijos/dobles/triples
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

from engine import reduce as R
from engine.strategy import prob_matrix

import puntos_modelo as pm
from strategies import valor_model as vm

HERE = os.path.dirname(os.path.abspath(__file__))
import rutas  # noqa: E402

ROOT = rutas.CARPETA
PESOS = os.path.join(ROOT, "data", "ligas", "puntos_pesos.json")
TABLA = os.path.join(ROOT, "data", "ligas", "variables_quiniela.csv")
FORMAS = {"6D": (0, 6), "3T1D": (3, 1), "2T2D": (2, 2), "1T4D": (1, 4)}
_cache: dict = {}


def pesos():
    if "pesos" not in _cache:
        _cache["pesos"] = json.load(open(PESOS, encoding="utf-8"))
    return _cache["pesos"]


def tabla():
    """{(temporada, jornada, num): fila} de variables_quiniela.csv."""
    if "tabla" not in _cache:
        import csv
        with open(TABLA, encoding="utf-8") as fh:
            _cache["tabla"] = {(str(r["temporada"]), int(r["jornada"]), int(r["num"])): r for r in csv.DictReader(fh)}
    return _cache["tabla"]


def filas_jornada(info):
    t = tabla()
    return [t.get((str(info.temporada), int(info.jornada), n)) for n in range(1, 15)]


def puntuacion(fila, modelo="A"):
    """Puntos S (escala x10) del modelo A para una fila con variables; None sin datos."""
    if not fila or str(fila.get("cubierto")) != "1":
        return None
    a = pesos()["A"]
    return a["casa"] + sum(w * float(fila[v]) for v, w in zip(a["vars"], a["w"]))


def prob_modelo(modelo, P0, filas, anula=()):
    """P (14,3) del modelo. P0: % probables normalizados. ``anula``: variables con peso puesto a 0
    (para medir lo que aporta cada una)."""
    P0 = np.asarray(P0, float)
    if modelo == "prob":
        return P0.copy()
    w = pesos()
    cub = np.array([1.0 if f and str(f.get("cubierto")) == "1" else 0.0 for f in filas])
    if modelo == "A":
        a = w["A"]
        pw = [0.0 if v in anula else x / 10 for v, x in zip(a["vars"], a["w"])]
        X = np.array([[float(f[v]) if c else 0.0 for v in a["vars"]] for f, c in zip(filas, cub)], float)
        Pa = pm.prob_a(a["casa"] / 10, a["h"] / 10, pw, X)
        return np.where(cub[:, None] > 0, Pa, P0)
    if modelo == "B":
        b = dict(w["B"])
        b["w"] = [0.0 if v in anula else x for v, x in zip(b["vars"], b["w"])]
        X = np.array([[float(f[v]) if c else 0.0 for v in b["vars"]] for f, c in zip(filas, cub)], float)
        return pm.prob_b(b, np.log(np.maximum(P0, 1e-4)), X, cub)
    raise ValueError(modelo)


def base_boleto(P, forma):
    """Lista de 14 listas de signos: fijo (1), doble (2) o triple (3) en los partidos mas dudosos."""
    P = np.asarray(P, float)
    orden = np.argsort(P.max(1), kind="stable")      # mas dudoso primero
    top = np.argsort(-P, axis=1)
    tam = np.ones(14, int)
    if forma in FORMAS:
        t, d = FORMAS[forma]
        tam[orden[:t]] = 3
        tam[orden[t:t + d]] = 2
    elif forma.startswith("auto"):
        u = int(forma[4:]) / 100
        cols = 1
        for i in orden:
            q = 3 if P[i].max() < u else 2
            if cols * q > 64:
                q = 2 if cols * 2 <= 64 else 1
            tam[i] = q
            cols *= q
    else:
        raise ValueError(forma)
    return [[int(x) for x in top[i, :tam[i]]] for i in range(14)]


class Base:
    modelo = "prob"

    def __init__(self, forma="6D", valor=0, modelo=None):
        self.forma, self.valor = str(forma), int(valor)
        if modelo:
            self.modelo = modelo

    def probs(self, info):
        return prob_modelo(self.modelo, prob_matrix(info, "prob", "lae"), filas_jornada(info))

    def generate(self, info, history, budget_eur):
        P = self.probs(info)
        pleno = vm.pleno_choice(info)[0]
        kmax = int(math.floor(budget_eur / info.precio_apuesta + 1e-9))
        if self.valor:
            L = prob_matrix(info, "lae", "prob")
            return R.to_columnset(vm.select_mix(P, L, kmax, 1.0, 0.5, 1), pleno)
        idx = R.expand_base(base_boleto(P, self.forma))
        if len(idx) > kmax:
            raise ValueError(f"{len(idx)} columnas no caben en {budget_eur} EUR")
        return R.to_columnset(idx, pleno)
