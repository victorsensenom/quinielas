"""Modelo de premio esperado por columna (enfoque "valor").

Idea: en La Quiniela los premios se reparten entre acertantes. Si el resultado real es r, el
numero de acertantes rivales de cada categoria se puede estimar con los % LAE (lo que juega el
publico) suponiendo que el publico rellena cada partido de forma independiente:

    rivales_k(r) = N * q(r) * e_d(R(r))      d = 14 - k  (d fallos)

donde N = columnas jugadas (recaudacion / 0,75), q(r) = prod_i lae_i(r_i) y e_d es el
polinomio simetrico elemental de grado d de R_i = (1 - lae_i(r_i)) / lae_i(r_i).
Ese modelo se corrige con una regresion de Poisson (log-cuadratica) ajustada SOLO con jornadas
anteriores (acertantes reales vs predichos).

Premio por acertante de la categoria k si el resultado es r:
    bruto = fondo_k * h(lambda)   con h(l) = (1 - e^-l) / l  (E[1/(1+X)], X ~ Poisson(l))
    neto  = descuento del gravamen del 20 % por encima del umbral exento vigente
    fondo_k = recaudacion * PRIZE_PCT[k]  (+ bote esperado en la categoria 15)

Valor esperado de una columna c (todas las categorias, sin el efecto de compartir con nuestras
propias columnas):
    EV(c) = sum_{d=0..4} sum_{r : dist(c, r) = d} p(r) * V_{14-d}(r)
con p(r) = prod_i prob_i(r_i) (% probables, la mejor estimacion). La suma por "capas" de
Hamming se hace para las 3^14 columnas a la vez con una recursion por partido (ver
``shell_combine``), ~1 s por jornada.

Informacion usada para la jornada en curso (todo pre-partido):
  * % LAE y % probables de los 14 partidos (JornadaInfo)
  * % probables / LAE de goles del Pleno al 15 (data/pleno15.csv; solo columnas prob_* y lae_*,
    nunca el resultado)
  * fecha de la jornada (dia de la semana)
  * historia: recaudacion, bote, acertantes y premios de jornadas ANTERIORES.
La recaudacion y el bote de la jornada en curso NO se usan: se estiman con la historia.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os

import numpy as np

from engine.data import N_MATCHES
from engine.reduce import POW, TOTAL, normalize
from engine.rules import PRIZE_PCT
from engine.strategy import prob_matrix

N = N_MATCHES
CATS = (14, 13, 12, 11, 10)            # d = 0..4 fallos
PRICE = 0.75
TAX_RATE = 0.20
# Peso de % probables en la probabilidad "real" (resto: % LAE). Elegido por log-loss por partido
# en 2017-2022 (optimo ~0,9; con 1,0 el modelo sobrestima la ventaja de prob frente a LAE en
# combinaciones de 14 partidos: log(prob/lae) observado 0,42 vs esperado 0,53).
ALPHA = 0.9
import rutas  # noqa: E402

DATA_DIR = os.path.join(rutas.CARPETA, "data")


# --------------------------------------------------------------------------- impuestos
def tax_threshold(fecha: str) -> float:
    """Importe exento del gravamen especial sobre premios (20 %) vigente en la fecha.
    Comprobado con jornadas.csv: los premios publicados son NETOS."""
    try:
        d = dt.date.fromisoformat(fecha[:10])
    except (ValueError, TypeError):
        return 40000.0
    if d < dt.date(2018, 7, 5):
        return 2500.0
    if d < dt.date(2019, 1, 1):
        return 10000.0
    if d < dt.date(2020, 1, 1):
        return 20000.0
    return 40000.0


def net_prize(gross, threshold):
    g = np.asarray(gross)
    return np.minimum(g, threshold) + (1 - TAX_RATE) * np.maximum(g - threshold, 0)


def weekday(fecha: str) -> int:
    try:
        return dt.date.fromisoformat(fecha[:10]).weekday()
    except (ValueError, TypeError):
        return 6


def is_weekend(fecha: str) -> bool:
    """Jornada de fin de semana (vie-dom). Las de entre semana recaudan menos y casi nunca
    llevan bote."""
    return weekday(fecha) >= 4


# --------------------------------------------------------------------------- pleno al 15
_PLENO = None


def _load_pleno():
    global _PLENO
    if _PLENO is not None:
        return _PLENO
    _PLENO = {}
    path = os.path.join(DATA_DIR, "pleno15.csv")
    if not os.path.exists(path):
        return _PLENO
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                key = (str(r["temporada"]).strip(), int(r["jornada"]))
                # SOLO porcentajes pre-partido; resultado y signo_goles no se leen
                pr = np.array([[float(r[f"prob_{s}{g}"]) for g in "012M"] for s in "LV"])
                la = np.array([[float(r[f"lae_{s}{g}"]) for g in "012M"] for s in "LV"])
            except (KeyError, ValueError):
                continue
            _PLENO[key] = (pr / pr.sum(1, keepdims=True), la / la.sum(1, keepdims=True))
    return _PLENO


def pleno_choice(info):
    """(pleno elegido (gl, gv), P(acertar pleno), % LAE del pleno elegido).
    Se elige el marcador mas probable segun % probables (independencia local/visitante)."""
    d = _load_pleno().get((str(info.temporada), int(info.jornada)))
    if d is None:
        return (1, 1), 0.10, 0.10
    pr, la = d
    M = np.outer(pr[0], pr[1])
    gl, gv = np.unravel_index(int(M.argmax()), M.shape)
    return (int(gl), int(gv)), float(M[gl, gv]), float(la[0, gl] * la[1, gv])


# --------------------------------------------------------------------------- utilidades 3^14
def esym(R, dmax=4):
    e = np.zeros(dmax + 1)
    e[0] = 1.0
    for r in R:
        for d in range(dmax, 0, -1):
            e[d] += e[d - 1] * r
    return e


def space_esym(L, dmax=4):
    """Para cada resultado r (3^14) -> q(r)=prod lae y lista E con e_d(R(r)), d=0..dmax
    (E[0] = None, vale 1). float32."""
    L = normalize(L).astype(np.float32)
    R = (1 - L) / L
    q = L[0].copy()
    E = [None, R[0].copy()] + [np.zeros(3, np.float32) for _ in range(dmax - 1)]
    for i in range(1, N):
        r = R[i][None, :]
        for d in range(dmax, 1, -1):
            E[d] = (E[d][:, None] + E[d - 1][:, None] * r).ravel()
        E[1] = (E[1][:, None] + r).ravel()
        q = (q[:, None] * L[i][None, :]).ravel()
    return q, E


def shell_combine(F):
    """F = [F_0..F_D] arrays (3^14,). Devuelve G(c) = sum_d sum_{r: dist(c,r)=d} F_d(r).
    Recursion H_j <- H_j + A_n H_{j+1} sobre los 14 partidos (H_j^(0) = F_j), donde A_n suma
    sobre los otros 2 signos del partido n. Se actualiza j ascendente para usar H_{j+1} antiguo."""
    H = [np.array(f, np.float32) for f in F]
    D = len(H) - 1
    for n in range(N):
        a, b = 3 ** n, 3 ** (N - 1 - n)
        for j in range(D):
            hj = H[j].reshape(a, 3, b)
            hn = H[j + 1].reshape(a, 3, b)
            hj += hn.sum(1, keepdims=True)
            hj -= hn
    return H[0]


# --------------------------------------------------------------------------- historia
_HCACHE: dict = {}


def _hist_row(j):
    """Rasgos de una jornada PASADA (solo se usa cuando ya forma parte de la historia)."""
    k = (j.temporada, j.jornada)
    row = _HCACHE.get(k)
    if row is not None:
        return row
    L = prob_matrix(j.info, "lae", "prob")
    s = np.asarray(j.signos, int)
    l = L[np.arange(N), s]
    e = esym((1 - l) / l)
    q = float(np.prod(l))
    rec = j.recaudacion
    th = tax_threshold(j.info.fecha)
    acert = {k2: (j.acertantes.get(k2) or 0) for k2 in CATS}
    row = {
        "key": k, "we": is_weekend(j.info.fecha), "rec": rec, "th": th,
        "bote": j.bote if not math.isnan(j.bote) else 0.0,
        "a15": j.acertantes.get(15) or 0, "a14": acert[14],
        "qe": {k2: q * e[d] for d, k2 in enumerate(CATS)},          # rivales predichos / N
        "lam": {k2: rec / PRICE * q * e[d] for d, k2 in enumerate(CATS)},
        "acert": acert,
        # lo que habria cobrado una columna acertante adicional (neto de impuestos)
        "real": {k2: float(net_prize(rec * PRIZE_PCT[k2] / (acert[k2] + 1), th)) for k2 in CATS},
    }
    _HCACHE[k] = row
    return row


def _binned_log_ratio(x, num, den, nb_max=10, per_bin=25):
    """Tramos por cuantiles de x: (media de x, log(sum num / sum den)) para interpolar."""
    nb = int(min(nb_max, max(2, len(x) // per_bin)))
    edges = np.quantile(x, np.linspace(0, 1, nb + 1))
    b = np.clip(np.searchsorted(edges, x, side="right") - 1, 0, nb - 1)
    xs, ys = [], []
    for t in range(nb):
        m = b == t
        if m.sum() == 0:
            continue
        xs.append(float(x[m].mean()))
        ys.append(math.log(max(num[m].sum(), 0.5) / max(den[m].sum(), 1e-12)))
    return np.array(xs), np.array(ys)


def _interp_ratio(cal, x):
    """exp(interpolacion lineal de log-razon); constante fuera del rango observado."""
    xs, ys = cal
    x = np.asarray(x, np.float32)
    if xs is None:
        return np.ones_like(x)
    return np.exp(np.interp(x, xs, ys)).astype(np.float32)


class _Fit:
    """Parametros estimados con un prefijo de la historia (filas ``rows``)."""

    def __init__(self, rows, base, feat, min_rows):
        n = len(rows)
        self.alpha = self.beta = 0.0
        ok = [i for i in range(n) if base[i] is not None]
        if len(ok) >= min_rows:
            Xf = np.column_stack([np.ones(len(ok)), [feat[i] for i in ok]])
            y = np.array([math.log(max(rows[i]["rec"], 1.0)) - base[i] for i in ok])
            coef = np.linalg.lstsq(Xf, y, rcond=None)[0]
            self.alpha, self.beta = float(coef[0]), float(coef[1])
        self.riv = {}
        for k in CATS:
            if n < min_rows:
                self.riv[k] = (None, None)
                continue
            lam = np.array([max(r["lam"][k], 1e-9) for r in rows])
            y = np.array([r["acert"][k] for r in rows], float)
            self.riv[k] = _binned_log_ratio(np.log(lam), y, lam)

    def rivals(self, k, lam):
        lam = np.maximum(np.asarray(lam, np.float32), np.float32(1e-30))
        return lam * _interp_ratio(self.riv[k], np.log(lam))

    def rec_hat(self, base_i, feat_i):
        if base_i is None:
            return 2.5e6
        return float(math.exp(base_i + self.alpha + self.beta * feat_i))

    def prize1(self, k, lam_raw, rec, th):
        """Premio neto (etapa 1) de un acertante adicional dada la lambda bruta."""
        lam = self.rivals(k, lam_raw)
        g = rec * PRIZE_PCT[k] * _h(lam)
        return net_prize(g, th), g, lam


class HistoryModel:
    """Estimaciones a partir SOLO de jornadas anteriores.

    * recaudacion esperada: media log de las 6 ultimas jornadas de la misma clase (fin de semana
      o entre semana) + regresion sobre log(1 + reserva de bote) en fin de semana;
    * bote esperado: reserva acumulada (fondos de 15 y 14 no repartidos) x proporcion historica;
    * etapa 1: correccion de rivales (acertantes reales / predichos, por tramos de lambda);
    * etapa 2: correccion del premio (premio real / predicho, por tramos de premio predicho),
      con predicciones de etapa 1 hechas para cada jornada pasada con SU propia historia previa.
    """

    def __init__(self, history, min_rows: int = 40, stage2: bool = True):
        rows = [_hist_row(j) for j in history if not math.isnan(j.recaudacion)]
        self.rows = rows
        res, rs = 0.0, []
        for r in rows:
            rs.append(res)
            if r["bote"] > 0:
                res = 0.0
            if r["we"] or r["bote"] > 0:
                if r["a15"] == 0:
                    res += r["bote"] + PRIZE_PCT[15] * r["rec"]
                if r["a14"] == 0:
                    res += PRIZE_PCT[14] * r["rec"]
        self.reserve = res
        num = sum(r["bote"] for r, rv in zip(rows, rs) if r["we"] and rv > 0)
        den = sum(rv for r, rv in zip(rows, rs) if r["we"] and rv > 0)
        self.bote_ratio = num / den if den > 0 else 0.8
        lr = np.log([max(r["rec"], 1.0) for r in rows]) if rows else np.zeros(0)
        we = np.array([r["we"] for r in rows], bool)
        for i, r in enumerate(rows):            # depende solo de filas previas -> memo
            if "base" not in r:
                r["base"] = self._mean_same(lr[:i], we[:i], we[i])
                r["feat"] = float(we[i]) * math.log1p(rs[i] / 1e6)
        base = [r["base"] for r in rows]
        feat = [r["feat"] for r in rows]
        self._lr, self._we = lr, we
        self.fit = _Fit(rows, base, feat, min_rows)
        self.calib = self.fit.riv
        self.cal2 = {k: (None, None) for k in CATS}
        if stage2:
            for i, r in enumerate(rows):
                if "pred" in r or i < min_rows:
                    continue
                f = _Fit(rows[:i], base[:i], feat[:i], min_rows)
                rh = f.rec_hat(base[i], feat[i])
                r["rec_hat"] = rh
                r["pred"] = {}
                for k in CATS:
                    p1, _, _ = f.prize1(k, np.array([rh / PRICE * r["qe"][k]], np.float32), rh, r["th"])
                    r["pred"][k] = float(p1[0])
            pr = [r for r in rows if "pred" in r]
            if len(pr) >= min_rows:
                for k in CATS:
                    x = np.array([max(r["pred"][k], 0.01) for r in pr])
                    y = np.array([r["real"][k] for r in pr])
                    self.cal2[k] = _binned_log_ratio(np.log(x), y, x)

    @staticmethod
    def _mean_same(lr, we, cls, n=6):
        idx = np.flatnonzero(we == cls)[-n:]
        if len(idx) == 0:
            if len(lr) == 0:
                return None
            return float(lr[-n:].mean())
        return float(lr[idx].mean())

    def expected_rec(self, fecha: str) -> float:
        cls = is_weekend(fecha)
        m = self._mean_same(self._lr, self._we, cls)
        return self.fit.rec_hat(m, float(cls) * math.log1p(self.reserve / 1e6))

    def expected_bote(self, fecha: str) -> float:
        return self.bote_ratio * self.reserve if is_weekend(fecha) else 0.0

    def rivals(self, k, lam):
        return self.fit.rivals(k, lam)

    def prize(self, k, lam_raw, rec, th, stage2: bool = True):
        """Premio neto final por acertante adicional (array) y lambda corregida."""
        p1, g, lam = self.fit.prize1(k, lam_raw, rec, th)
        p = np.asarray(p1, np.float32)
        if stage2:
            p = p * _interp_ratio(self.cal2[k], np.log(np.maximum(p, np.float32(0.01))))
        if k == 10:
            p = np.where(g < 1.5, np.float32(0.0), p)
        return p, lam


def _h(lam):
    """E[1/(1+X)], X ~ Poisson(lam) = (1 - e^-lam) / lam."""
    lam = np.maximum(lam, np.float32(1e-7))
    return -np.expm1(-lam) / lam


# --------------------------------------------------------------------------- modelo de jornada
class JornadaModel:
    """Arrays sobre las 3^14 combinaciones: w (prob real), V[k] (premio neto esperado por
    acertante de la categoria k si ese es el resultado), EV (valor esperado de jugar cada
    columna)."""

    def __init__(self, info, history, need_ev: bool = True, alpha: float = ALPHA):
        self.info = info
        hm = HistoryModel(history)
        self.hm = hm
        self.P = prob_matrix(info, "prob", "lae")
        self.L = prob_matrix(info, "lae", "prob")
        # probabilidad "real" usada para el valor esperado: mezcla geometrica prob^alpha * lae^(1-alpha)
        Pt = self.P ** alpha * self.L ** (1 - alpha)
        self.Pt = Pt / Pt.sum(1, keepdims=True)
        self.rec = hm.expected_rec(info.fecha)
        self.bote = hm.expected_bote(info.fecha)
        self.ncols = self.rec / PRICE
        self.th = tax_threshold(info.fecha)
        self.pleno, self.p_pleno, self.l_pleno = pleno_choice(info)

        from engine.reduce import space_weights
        self.w = space_weights(self.Pt)                      # float64
        q, E = space_esym(self.L, 4)
        q *= np.float32(self.ncols)
        V = {}
        for d, k in enumerate(CATS):
            v, lam = self.hm.prize(k, q if d == 0 else q * E[d], self.rec, self.th)
            E[d] = None
            if k == 14:
                # categoria 15 (14 + pleno): fondo 7,5 % + bote esperado; el engine paga solo la
                # categoria maxima, asi que con pleno acertado se cobra la de 15 en vez de la de 14
                lam15 = lam * self.l_pleno
                g15 = (self.rec * PRIZE_PCT[15] + self.bote) * _h(lam15)
                v = self.p_pleno * net_prize(g15, self.th) + (1 - self.p_pleno) * v
            V[k] = v.astype(np.float32)
            del lam, v
        del q, E
        self.V = V
        self.EV = None
        self.w32 = self.w.astype(np.float32)
        if need_ev:
            self.EV = shell_combine([self.w32 * V[k] for k in CATS])   # float32 (3^14,)

    # ---- valor de un conjunto de columnas
    def ev_cols(self, idx) -> np.ndarray:
        return self.EV[np.asarray(idx, np.int64)]

    def summary(self, idx) -> dict:
        idx = np.asarray(idx, np.int64)
        ev = float(self.ev_cols(idx).sum()) if self.EV is not None else math.nan
        cost = len(idx) * PRICE
        return {"ev": ev, "ev_euro": ev / cost if cost else 0.0, "rec_est": self.rec, "bote_est": self.bote}


# --------------------------------------------------------------------------- seleccion
def select_ev(model: "JornadaModel", K: int, delta: float = 0.5, n_cand: int = 3000) -> np.ndarray:
    """Greedy de valor esperado con diversificacion.

    Ganancia de anadir c:  EV(c) - delta * sum_{r a distancia <= 2 de c} p(r) * min(V(c,r), best(r))
    donde best(r) es el mejor premio que ya nos daria alguna columna elegida si el resultado
    fuese r (categorias 14/15, 13 y 12). delta = 0 -> las K columnas de mayor EV (sin
    diversificar); delta = 1 -> en cada resultado solo cuenta el mejor premio (maxima
    diversificacion). La ganancia es decreciente (submodular) -> lazy greedy exacto.
    Candidatos: las n_cand columnas de mayor EV.
    """
    import heapq
    from engine.reduce import neighbors
    EV = model.EV
    n_cand = int(max(n_cand, K))
    cand = np.argpartition(-EV, n_cand)[:n_cand]
    cand = cand[np.argsort(-EV[cand], kind="stable")]
    if delta <= 0:
        return cand[:K].astype(np.int64)
    w = model.w32
    Vs = (model.V[14], model.V[13], model.V[12])
    best: dict = {}
    heap = [(-float(EV[c]), int(c), 0) for c in cand]
    heapq.heapify(heap)
    chosen = []
    step = 0
    while heap and len(chosen) < K:
        g, c, st = heapq.heappop(heap)
        if st == step:
            chosen.append(c)
            nb = neighbors([c], 2)[0]
            for pos, r in enumerate(nb.tolist()):
                v = float(Vs[0 if pos == 0 else (1 if pos <= 28 else 2)][r])
                if v > best.get(r, 0.0):
                    best[r] = v
            step += 1
            continue
        nb = neighbors([c], 2)[0]
        if best:
            b = np.fromiter((best.get(r, 0.0) for r in nb.tolist()), np.float64, len(nb))
            v = np.concatenate([Vs[0][nb[:1]], Vs[1][nb[1:29]], Vs[2][nb[29:]]]).astype(np.float64)
            pen = float((w[nb] * np.minimum(v, b)).sum())
        else:
            pen = 0.0
        heapq.heappush(heap, (-(float(EV[c]) - delta * pen), c, step))
    return np.array(chosen, np.int64)


def mix_matrix(P, L, a: float = 1.0, b: float = 0.0) -> np.ndarray:
    """Pesos por partido p^a * (p/lae)^b normalizados. El peso de una columna (producto por
    partido) es entonces prob(c)^a * (prob(c)/lae(c))^b, normalizado."""
    P = normalize(P)
    L = normalize(L)
    M = P ** (a + b) / L ** b
    return M / M.sum(1, keepdims=True)


def select_mix(P, L, K: int, a: float = 1.0, b: float = 0.0, radius: int = 1) -> np.ndarray:
    from engine.reduce import greedy_cover
    return greedy_cover(mix_matrix(P, L, a, b), K, radius=radius)
