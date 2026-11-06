"""Interfaz de estrategias.

Una estrategia es:
  * una funcion ``generate(info, history, budget_eur) -> list[Column] | ColumnSet``, o
  * un objeto/clase con metodo ``generate(info, history, budget_eur)``.

``info``    : ``engine.data.JornadaInfo``  -> solo datos pre-partido (equipos, division,
              % lae, % prob, % quin, precio, fecha). No tiene resultado, signo, premios,
              recaudacion ni acertantes: no hay forma de leerlos desde ahi.
``history`` : tupla de ``engine.data.Jornada`` COMPLETAS de jornadas anteriores
              (estrictamente anteriores en el orden temporada/jornada).
``budget_eur``: presupuesto maximo de la jornada. El coste es n_columnas * info.precio_apuesta.

Un modulo de estrategia (para ``engine.run``) debe exponer ``generate`` o una clase
``Strategy`` (que se instancia con los ``--param k=v`` del CLI).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .data import GOAL_CHARS, GOAL_TO_CODE, N_MATCHES, SIGN_CHARS, SIGN_TO_CODE, JornadaInfo


@dataclass(frozen=True, slots=True)
class Column:
    """Una columna: 14 signos (codigos 0/1/2) + pleno (goles local, visitante; codigos 0..3, 3='M')."""
    signs: tuple
    pleno: tuple = (1, 1)

    def __post_init__(self):
        if len(self.signs) != N_MATCHES or any(s not in (0, 1, 2) for s in self.signs):
            raise ValueError(f"columna invalida: {self.signs}")
        if len(self.pleno) != 2 or any(g not in (0, 1, 2, 3) for g in self.pleno):
            raise ValueError(f"pleno invalido: {self.pleno}")

    @classmethod
    def parse(cls, signs: str, pleno: str = "1-1") -> "Column":
        """``Column.parse('1X21X21X21X21X', 'M-1')``"""
        s = signs.strip().upper()
        p = pleno.strip().upper().replace("-", "")
        return cls(tuple(SIGN_TO_CODE[c] for c in s), (GOAL_TO_CODE[p[0]], GOAL_TO_CODE[p[1]]))

    def __str__(self):
        return "".join(SIGN_CHARS[s] for s in self.signs) + " " + GOAL_CHARS[self.pleno[0]] + "-" + GOAL_CHARS[self.pleno[1]]


class ColumnSet:
    """Conjunto de columnas en forma matricial (rapido para miles de columnas).

    signs: (K, 14) int8 en {0,1,2};  plenos: (K, 2) int8 en {0..3}.
    """
    __slots__ = ("signs", "plenos")

    def __init__(self, signs, plenos=None):
        signs = np.asarray(signs, dtype=np.int8).reshape(-1, N_MATCHES)
        if plenos is None:
            plenos = np.ones((len(signs), 2), np.int8)
        plenos = np.asarray(plenos, dtype=np.int8)
        if plenos.ndim == 1:
            plenos = np.broadcast_to(plenos.reshape(1, 2), (len(signs), 2))
        plenos = np.array(plenos, dtype=np.int8).reshape(-1, 2)
        if len(plenos) != len(signs):
            raise ValueError("signs y plenos con distinta longitud")
        if signs.size and (signs.min() < 0 or signs.max() > 2):
            raise ValueError("signos fuera de {0,1,2}")
        if plenos.size and (plenos.min() < 0 or plenos.max() > 3):
            raise ValueError("goles del pleno fuera de {0..3}")
        self.signs, self.plenos = signs, plenos

    def __len__(self):
        return len(self.signs)

    @classmethod
    def from_columns(cls, cols: Iterable[Column]) -> "ColumnSet":
        cols = list(cols)
        if not cols:
            return cls(np.zeros((0, N_MATCHES), np.int8), np.zeros((0, 2), np.int8))
        return cls(np.array([c.signs for c in cols], np.int8), np.array([c.pleno for c in cols], np.int8))

    def to_columns(self) -> list[Column]:
        return [Column(tuple(int(x) for x in s), tuple(int(x) for x in p)) for s, p in zip(self.signs, self.plenos)]


def as_columnset(x) -> ColumnSet:
    if isinstance(x, ColumnSet):
        return x
    if x is None:
        return ColumnSet.from_columns([])
    return ColumnSet.from_columns(x)


# --------------------------------------------------------------------------- helpers
def prob_matrix(info: JornadaInfo, source: str = "prob", fallback: str | None = "lae",
                eps: float = 1e-4) -> np.ndarray:
    """Matriz (14, 3) de probabilidades normalizadas por fila.

    Usa ``source`` ('prob'|'lae'|'quin'); por partido, si falta, ``fallback``; si
    tambien falta, uniforme. Nunca devuelve ceros (minimo ``eps``) para que sirva en
    ``engine.reduce``.
    """
    P = np.array(getattr(info, source), float)
    if fallback:
        F = np.array(getattr(info, fallback), float)
        bad = np.isnan(P).any(1) | (np.nan_to_num(P).sum(1) <= 0)
        P[bad] = F[bad]
    bad = np.isnan(P).any(1) | (np.nan_to_num(P).sum(1) <= 0)
    P[bad] = 1.0
    P = np.clip(P, 0, None)
    P = P / P.sum(1, keepdims=True)
    P = np.maximum(P, eps)
    return P / P.sum(1, keepdims=True)


def call_strategy(strategy, info, history, budget):
    fn = strategy.generate if hasattr(strategy, "generate") else strategy
    return fn(info, history, budget)


def load_strategy(spec: str, params: dict | None = None, search_dirs: Iterable[str] = ()):
    """Carga una estrategia por nombre de modulo ('fijo_favoritos', 'strategies.aleatoria')
    o ruta a .py. Devuelve un objeto llamable o con ``generate``."""
    params = params or {}
    mod = None
    if spec.endswith(".py") or os.path.sep in spec or "/" in spec:
        path = os.path.abspath(spec)
        name = "strategy_" + os.path.splitext(os.path.basename(path))[0]
        sp = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(sp)
        sys.modules[name] = mod
        sp.loader.exec_module(mod)
    else:
        for cand in (spec, "strategies." + spec):
            try:
                mod = importlib.import_module(cand)
                break
            except ModuleNotFoundError as e:
                if e.name not in (cand, cand.split(".")[0]):
                    raise
        if mod is None:
            for d in search_dirs:
                p = os.path.join(d, spec + ".py")
                if os.path.exists(p):
                    return load_strategy(p, params)
            raise ModuleNotFoundError(f"estrategia no encontrada: {spec}")
    if hasattr(mod, "Strategy"):
        return mod.Strategy(**params)
    if params:
        if hasattr(mod, "make"):
            return mod.make(**params)
        raise ValueError(f"{spec} no acepta parametros (no tiene clase Strategy ni make())")
    if hasattr(mod, "generate"):
        return mod.generate
    raise AttributeError(f"{spec} no define generate() ni Strategy")
