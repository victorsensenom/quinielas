"""Linea base: columnas aleatorias uniformes (signos y pleno) con semilla reproducible.

Parametros (--param): seed (int, def. 12345), n (columnas; def. todas las que permita el
presupuesto). La semilla de cada jornada se deriva de (seed, temporada, jornada), asi el
resultado no depende del orden ni de las jornadas excluidas.
"""
import zlib

import numpy as np

from engine.strategy import ColumnSet


class Strategy:
    def __init__(self, seed: int = 12345, n: int | None = None):
        self.seed = int(seed)
        self.n = None if n is None else int(n)

    def generate(self, info, history, budget_eur):
        k = int(budget_eur // info.precio_apuesta + 1e-9)
        if self.n is not None:
            k = min(k, self.n)
        h = zlib.crc32(f"{self.seed}|{info.temporada}|{info.jornada}".encode())
        rng = np.random.default_rng(h)
        return ColumnSet(rng.integers(0, 3, (k, 14), dtype=np.int8),
                         rng.integers(0, 4, (k, 2), dtype=np.int8))
