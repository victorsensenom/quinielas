"""Utilidades de reduccion para estrategias.

Espacio de columnas: 3^14 = 4.782.969. Cada columna se identifica por un indice en base 3
con el partido 1 como digito MAS significativo (1->0, X->1, 2->2):
    idx = sum_i c_i * 3^(13-i)

Contenido:
  * expand_base(base)            todas las columnas de una base de fijos/dobles/triples (indices)
  * idx_to_cols / cols_to_idx    conversion indice <-> matriz (K,14) int8
  * count_signs, surprises       numero de 1/X/2 y de "sorpresas" (signos con prob < umbral)
  * filter_counts, filter_surprises
  * space_weights(P)             probabilidad de cada una de las 3^14 combinaciones reales
  * neighbors(idx, radius)       columnas a distancia de Hamming <= radius (1 -> 13+, 2 -> 12+)
  * coverage(sel, P, radius)     P(resultado real a distancia <= radius de alguna columna elegida)
  * greedy_cover(P, K, ...)      seleccion greedy (lazy greedy exacto, la cobertura es submodular)
                                 de K columnas maximizando P(>=13) (radius=1) o P(>=12) (radius=2)
  * to_columnset(idx, pleno)

Todo vectorizado con numpy. Los pesos del espacio completo se calculan con productos externos
(sin materializar la matriz 3^14 x 14), por lo que una seleccion de 64 columnas sobre el
espacio completo tarda ~1-2 s.
"""
from __future__ import annotations

import heapq
from itertools import combinations

import numpy as np

from .data import N_MATCHES, SIGN_TO_CODE

N = N_MATCHES
TOTAL = 3 ** N
POW = (3 ** np.arange(N - 1, -1, -1)).astype(np.int64)


# --------------------------------------------------------------------------- conversiones
def idx_to_cols(idx) -> np.ndarray:
    idx = np.asarray(idx, np.int64).ravel()
    out = np.empty((len(idx), N), np.int8)
    for i in range(N):
        out[:, i] = (idx // POW[i]) % 3
    return out


def cols_to_idx(cols) -> np.ndarray:
    cols = np.asarray(cols).reshape(-1, N).astype(np.int64)
    return cols @ POW


def _parse_opts(b) -> list[int]:
    if isinstance(b, str):
        return sorted({SIGN_TO_CODE[c] for c in b.upper()})
    return sorted({int(x) for x in b})


def expand_base(base) -> np.ndarray:
    """Indices de todas las columnas de una base. ``base`` = 14 elementos tipo '1', '1X', '1X2'
    (o iterables de codigos). Ej.: 6 dobles y 8 fijos -> 64 columnas."""
    if len(base) != N:
        raise ValueError("la base debe tener 14 partidos")
    idx = np.zeros(1, np.int64)
    for b in base:
        o = np.array(_parse_opts(b), np.int64)
        idx = (idx[:, None] * 3 + o[None, :]).ravel()
    return idx


def _outer_reduce(vals: np.ndarray, op, dtype) -> np.ndarray:
    """Para vals (14,3) devuelve el array (3^14,) con op acumulado del valor de cada digito."""
    acc = np.asarray(vals[0], dtype)
    for i in range(1, N):
        v = np.asarray(vals[i], dtype)
        acc = op(acc[:, None], v[None, :]).ravel()
    return acc


# --------------------------------------------------------------------------- filtros
def count_signs(idx=None):
    """(n1, nX, n2) por columna. ``idx=None`` -> espacio completo (arrays de 3^14, int8)."""
    if idx is None:
        eye = np.eye(3, dtype=np.int8)
        return tuple(_outer_reduce(np.tile(eye[k], (N, 1)), np.add, np.int8) for k in range(3))
    cols = idx_to_cols(idx)
    return tuple((cols == k).sum(1).astype(np.int8) for k in range(3))


def surprises(P, threshold: float, idx=None) -> np.ndarray:
    """Numero de partidos donde la columna elige un signo con prob < threshold."""
    P = np.asarray(P, float)
    S = (P < threshold).astype(np.int8)
    if idx is None:
        return _outer_reduce(S, np.add, np.int8)
    cols = idx_to_cols(idx)
    return S[np.arange(N)[None, :], cols].sum(1).astype(np.int8)


def _rng_ok(x, r):
    if r is None:
        return np.ones(len(x), bool)
    lo, hi = r
    return (x >= lo) & (x <= hi)


def filter_counts(idx=None, n1=None, nx=None, n2=None) -> np.ndarray:
    """Filtra indices por rangos (min, max) inclusivos de numero de 1, X y 2 (idx=None: espacio completo)."""
    c1, cx, c2 = count_signs(idx)
    ok = _rng_ok(c1, n1) & _rng_ok(cx, nx) & _rng_ok(c2, n2)
    return np.flatnonzero(ok).astype(np.int64) if idx is None else np.asarray(idx, np.int64)[ok]


def filter_surprises(idx, P, threshold: float, max_surprises: int, min_surprises: int = 0) -> np.ndarray:
    s = surprises(P, threshold, idx)
    ok = (s >= min_surprises) & (s <= max_surprises)
    return np.flatnonzero(ok).astype(np.int64) if idx is None else np.asarray(idx, np.int64)[ok]


# --------------------------------------------------------------------------- probabilidades
def normalize(P, eps: float = 1e-6) -> np.ndarray:
    P = np.asarray(P, float).reshape(N, 3)
    P = np.maximum(P / P.sum(1, keepdims=True), eps)
    return P / P.sum(1, keepdims=True)


def space_weights(P) -> np.ndarray:
    """Probabilidad de cada combinacion real (3^14,) suponiendo partidos independientes."""
    return _outer_reduce(normalize(P), np.multiply, np.float64)


def col_prob(idx, P) -> np.ndarray:
    P = normalize(P)
    cols = idx_to_cols(idx)
    return np.prod(P[np.arange(N)[None, :], cols], axis=1)


def _ball_mass_factor(P, radius: int) -> np.ndarray:
    """f(c) tal que masa de la bola de radio r alrededor de c = w(c) * f(c).
    Con r_i = (1-p_i(c_i))/p_i(c_i): f = 1 + e1(r) [+ e2(r)]."""
    P = normalize(P)
    R = (1 - P) / P
    e1 = np.asarray(R[0], np.float64)
    e2 = np.zeros(3, np.float64)
    for i in range(1, N):
        r = R[i][None, :]
        if radius >= 2:
            e2 = (e2[:, None] + e1[:, None] * r).ravel()
        e1 = (e1[:, None] + r).ravel()
    f = 1.0 + (e1 if radius >= 1 else 0.0)
    if radius >= 2:
        f = f + e2
    return f


_D = np.array([[[(((c + k + 1) % 3) - c) * 3 ** (N - 1 - i) for k in range(2)] for c in range(3)]
               for i in range(N)], np.int64)          # (14, 3, 2): delta de cambiar el digito i
_PI, _PJ = np.triu_indices(N, 1)                         # 91 pares de partidos


def neighbors(idx, radius: int = 1) -> np.ndarray:
    """(K, M) indices de todas las columnas a distancia <= radius (incluida ella misma).
    radius=0 -> M=1 ; radius=1 -> M=29 ; radius=2 -> M=393."""
    idx = np.asarray(idx, np.int64).ravel()
    K = len(idx)
    parts = [idx[:, None]]
    if radius >= 1:
        cols = idx_to_cols(idx)
        Dsel = _D[np.arange(N)[None, :], cols]           # (K, 14, 2)
        parts.append(idx[:, None] + Dsel.reshape(K, 2 * N))
        if radius >= 2:
            pair = Dsel[:, _PI, :, None] + Dsel[:, _PJ, None, :]   # (K, 91, 2, 2)
            parts.append(idx[:, None] + pair.reshape(K, -1))
    if radius > 2:
        raise ValueError("radius maximo 2")
    return np.concatenate(parts, 1)


def coverage(sel_idx, P, radius: int = 1, w=None) -> float:
    """Probabilidad de que el resultado real quede a distancia <= radius de alguna columna."""
    w = space_weights(P) if w is None else w
    sel_idx = np.asarray(sel_idx, np.int64)
    if len(sel_idx) == 0:
        return 0.0
    nb = np.unique(neighbors(sel_idx, radius))
    return float(w[nb].sum())


def coverage_report(sel_idx, P, w=None) -> dict:
    """P(14), P(>=13), P(>=12) de un conjunto de columnas (sin el pleno)."""
    w = space_weights(P) if w is None else w
    return {"p14": coverage(sel_idx, P, 0, w), "p13": coverage(sel_idx, P, 1, w),
            "p12": coverage(sel_idx, P, 2, w)}


# --------------------------------------------------------------------------- greedy
def greedy_cover(P, K: int, radius: int = 1, candidates=None, w=None, return_info: bool = False,
                 batch_size: int = 256):
    """Elige K columnas (de ``candidates`` o de todo el espacio) maximizando la probabilidad
    cubierta a distancia <= radius (radius=1: P(>=13 aciertos); radius=2: P(>=12)).

    Lazy greedy exacto (la cobertura es submodular): las ganancias iniciales se calculan en forma
    cerrada para todos los candidatos y solo se reevaluan los que llegan a la cima del heap.
    Devuelve los indices elegidos (en orden de seleccion) y, opcionalmente, info con la
    ganancia de cada paso y la cobertura total.
    """
    P = normalize(P)
    w = space_weights(P) if w is None else w
    f = _ball_mass_factor(P, radius)
    if candidates is None:
        g0 = w * f
        cand = None
    else:
        cand = np.unique(np.asarray(candidates, np.int64))
        g0 = w[cand] * f[cand]
    n = len(g0)
    K = int(min(K, n))
    if K <= 0:
        sel = np.zeros(0, np.int64)
        return (sel, {"gains": [], "coverage": 0.0}) if return_info else sel

    order = np.argsort(-g0, kind="stable")
    unc = w.copy()
    heap: list = []
    ptr = 0
    chunk = max(8 * K, 4096)
    chosen, gains, fresh = [], [], {}
    step = 0
    while len(chosen) < K:
        # los candidatos aun fuera del heap tienen cota superior g0[order[ptr]]
        while ptr < n and (not heap or g0[order[ptr]] > -heap[0][0]):
            end = min(ptr + chunk, n)
            heap.extend(zip((-g0[order[ptr:end]]).tolist(), order[ptr:end].tolist()))
            heapq.heapify(heap)
            ptr = end
        if not heap:
            break
        negg, j = heapq.heappop(heap)
        if fresh.get(j) == step:
            # ganancia exacta en el estado actual y es la maxima -> elegir
            c = int(j if cand is None else cand[j])
            unc[neighbors([c], radius)[0]] = 0.0
            gains.append(-negg)
            chosen.append(c)
            step += 1
            continue
        # reevaluar en bloque este y los siguientes candidatos obsoletos de la cima del heap
        batch = [j]
        while heap and len(batch) < batch_size and fresh.get(heap[0][1]) != step:
            batch.append(heapq.heappop(heap)[1])
        bj = np.array(batch, np.int64)
        bc = bj if cand is None else cand[bj]
        g = unc[neighbors(bc, radius)].sum(1)
        for jj, gg in zip(batch, g.tolist()):
            fresh[jj] = step
            heapq.heappush(heap, (-gg, jj))
    sel = np.array(chosen, np.int64)
    if return_info:
        return sel, {"gains": gains, "coverage": float(sum(gains))}
    return sel


def to_columnset(idx, pleno=(1, 1)):
    from .strategy import ColumnSet
    return ColumnSet(idx_to_cols(idx), np.array(pleno, np.int8))
