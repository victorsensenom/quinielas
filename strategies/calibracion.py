"""Recalibracion de los % probables (prob1/X/2, sacados de cuotas).

Modelo (logit condicional, "temperatura + sesgo por signo", opcionalmente por grupo):

    q_k  proporcional a  exp( T_g * log p_k  +  c_{g,k} )        k in {1, X, 2},  c_{g,1} = 0
    [variante "lae":  + gamma_g * log lae_k ]

p = % probables normalizados, g = grupo del partido (ver ``grupo``). T < 1 aplana las
probabilidades (el mercado es demasiado seguro), T > 1 las afila; c_X > 0 sube los empates.
Los parametros de grupo se estiman como desviaciones del global con penalizacion L2
(se encogen hacia el global si hay pocos datos).

Uso en estrategias:
    from strategies.calibracion import corregir
    P = corregir(info, history)          # (14, 3) en %, filas suman 100

``corregir`` solo usa datos pre-partido de la jornada (% probables, % LAE, nombres, codigo de
division y fecha) y parametros guardados en data/calibracion.json, elegidos de forma que se
hayan estimado SOLO con temporadas anteriores a la de ``info`` (y, si se pide, no posteriores a
``hasta``). Sin parametros validos devuelve los % originales.

Ajuste: ``python -m strategies.calibracion`` (lo hace calib_lab.py; ver results/INFORME_calibracion.md).
"""
from __future__ import annotations

import json
import math
import os
import unicodedata

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "data")
PARAMS_PATH = os.path.join(DATA_DIR, "calibracion.json")
EPS = 1e-4

# --------------------------------------------------------------------------- grupos
_PAISES = """ALEMANIA ALBANIA ANDORRA ARABIA SAUDI ARGELIA ARGENTINA ARMENIA AUSTRALIA AUSTRIA AZERBAIYAN
BELGICA BIELORRUSIA BOLIVIA BOSNIA BRASIL BULGARIA CAMERUN CANADA CHILE CHIPRE COLOMBIA COREA SUR
REP. COREA COSTA MARFIL COSTA RICA CROACIA CURAZAO DINAMARCA ECUADOR EGIPTO ESCOCIA ESLOVAQUIA
ESLOVENIA ESPANA ESTADOS UNIDOS ESTONIA FINLANDIA FRANCIA GALES GEORGIA GHANA GRECIA GUINEA HUNGRIA
INGLATERRA IRAK IRAN IRLANDA N. ISLANDIA ISLAS FEROE ISRAEL ITALIA JAMAICA JAPON KAZAJISTAN KOSOVO
LETONIA LIECHTENSTEIN LITUANIA LUXEMBURGO MACEDONIA MALI MALTA MARRUECOS MEXICO MOLDAVIA MONTENEGRO
NIGERIA NORUEGA NUEVA ZELANDA PAISES BAJOS PANAMA PARAGUAY PERU POLONIA PORTUGAL QATAR REP.CHECA
REP.IRLANDA REP. DOMINICANA RUMANIA RUSIA SAN MARINO SENEGAL SERBIA SUDAFRICA SUECIA SUIZA TUNEZ
TURQUIA UCRANIA URUGUAY UZBEKISTAN VENEZUELA HOLANDA IRLANDA ZAMBIA HAITI HONDURAS EL SALVADOR
CABO VERDE ARABIA SAUDI JORDANIA AUSTRALIA CHINA INDIA"""
# nombres de varias palabras: se reconstruyen a partir de esta lista de frases
_PAISES_SET = None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("_", " ").split())


def _paises():
    global _PAISES_SET
    if _PAISES_SET is None:
        multi = ["ARABIA SAUDI", "COREA SUR", "REP. COREA", "COSTA MARFIL", "COSTA RICA", "ESTADOS UNIDOS",
                 "IRLANDA N.", "ISLAS FEROE", "NUEVA ZELANDA", "PAISES BAJOS", "REP. DOMINICANA",
                 "SAN MARINO", "EL SALVADOR", "CABO VERDE"]
        txt = " " + " ".join(_PAISES.split()) + " "
        out = set(multi)
        for m in multi:
            txt = txt.replace(" " + m + " ", " ")
        out.update(txt.split())
        _PAISES_SET = out
    return _PAISES_SET


def es_femenino(local: str, visitante: str) -> bool:
    for t in (local, visitante):
        u = (t or "").strip().upper()
        if "(F)" in u or u.endswith(" F") or u.endswith("_F") or (u.startswith("_") and u.endswith(" F")):
            return True
    return False


def es_selecciones(local: str, visitante: str) -> bool:
    P = _paises()
    return _norm(local).rstrip() in P and _norm(visitante) in P


def categoria(local: str, visitante: str, division) -> str:
    """'esp' (division 1/2/3: ligas y copa espanolas), 'ext' (division 5, clubes: ligas
    extranjeras y competiciones europeas), 'sel' (selecciones), 'fem' (femenino), 'otro'."""
    d = str(division).strip()
    if es_femenino(local, visitante):
        return "fem"
    if es_selecciones(local, visitante):
        return "sel"
    if d in ("1", "2", "3"):
        return "esp"
    if d == "5":
        return "ext"
    return "otro"


def mes(fecha: str) -> int:
    try:
        return int(str(fecha)[5:7])
    except (ValueError, TypeError):
        return 0


def es_verano(fecha: str) -> bool:
    return mes(fecha) in (6, 7, 8)


def grupo(local, visitante, division, fecha, esquema: str) -> str:
    """Grupo del partido segun el esquema: 'global', 'cat', 'cat_verano' (ext separado
    en verano jun-ago / resto), 'cat_verano2' (ext y esp separados en verano / resto), 'div'."""
    if esquema == "global":
        return "all"
    c = categoria(local, visitante, division)
    if esquema == "cat":
        return c
    if esquema == "cat_verano":
        if c == "ext":
            return "ext_ver" if es_verano(fecha) else "ext_inv"
        return c
    if esquema == "cat_verano2":
        if c in ("ext", "esp"):
            return c + ("_ver" if es_verano(fecha) else "_inv")
        return c
    if esquema == "div":
        return "d" + str(division).strip()
    raise ValueError(esquema)


# --------------------------------------------------------------------------- modelo
def _features(logp, logl, use_lae: bool):
    """phi (n, 3, F): [log p_k, 1{k=X}, 1{k=2}, (log lae_k)]."""
    n = logp.shape[0]
    F = 4 if use_lae else 3
    phi = np.zeros((n, 3, F))
    phi[:, :, 0] = logp
    phi[:, 1, 1] = 1.0
    phi[:, 2, 2] = 1.0
    if use_lae:
        phi[:, :, 3] = logl
    return phi


def _probs(phi, theta):
    z = np.einsum("nkf,nf->nk", phi, theta)
    z -= z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit(logp, logl, y, groups, use_lae=False, lam=50.0, iters=50):
    """Ajuste por Newton del logit condicional con parametros globales + desviaciones por grupo
    penalizadas (lam * ||delta_g||^2). Devuelve dict de parametros (listas, serializable)."""
    phi = _features(logp, logl, use_lae)
    n, _, F = phi.shape
    gl = sorted(set(groups))
    gi = {g: i for i, g in enumerate(gl)}
    G = len(gl) if len(gl) > 1 else 0
    gidx = np.array([gi[g] for g in groups]) if G else np.zeros(n, int)
    # parametros: global (F) + G*F desviaciones
    D = F * (1 + G)
    th = np.zeros(D)
    th[0] = 1.0
    onehot_y = np.zeros((n, 3))
    onehot_y[np.arange(n), y] = 1.0
    pen = np.zeros(D)
    pen[F:] = lam

    def theta_rows(th):
        base = th[:F][None, :].repeat(n, 0)
        if G:
            dev = th[F:].reshape(G, F)
            base = base + dev[gidx]
        return base

    def big_phi():
        # (n,3,D) expandido: global + bloque del grupo
        if not G:
            return phi
        B = np.zeros((n, 3, D))
        B[:, :, :F] = phi
        for g in range(G):
            m = gidx == g
            B[m, :, F * (1 + g):F * (2 + g)] = phi[m]
        return B

    BP = big_phi()
    prev = math.inf
    for _ in range(iters):
        q = _probs(phi, theta_rows(th))
        Ephi = np.einsum("nk,nkd->nd", q, BP)
        grad = np.einsum("nk,nkd->d", onehot_y, BP) - Ephi.sum(0) - 2 * pen * th
        # Hessiana = -sum Cov(phi) - 2 pen
        H = -(np.einsum("nk,nkd,nke->de", q, BP, BP) - np.einsum("nd,ne->de", Ephi, Ephi)) - np.diag(2 * pen)
        step = np.linalg.solve(H - 1e-9 * np.eye(D), grad)
        th = th - step
        ll = float(np.log(np.maximum(q[np.arange(n), y], 1e-15)).sum())
        if abs(prev - ll) < 1e-7:
            break
        prev = ll
    out = {"use_lae": bool(use_lae), "global": th[:F].tolist(), "grupos": {}}
    if G:
        dev = th[F:].reshape(G, F)
        for g, i in gi.items():
            out["grupos"][g] = (th[:F] + dev[i]).tolist()
    return out


def apply(params, logp, logl, groups):
    """Probabilidades corregidas (n, 3) para filas con log p, log lae y grupo."""
    use_lae = params.get("use_lae", False)
    phi = _features(logp, logl, use_lae)
    gl = params.get("grupos", {})
    th = np.array([gl.get(g, params["global"]) for g in groups], float)
    return _probs(phi, th)


def _norm_rows(M, fallback=None):
    M = np.array(M, float)
    if fallback is not None:
        bad = np.isnan(M).any(1) | (np.nan_to_num(M).sum(1) <= 0)
        M[bad] = np.array(fallback, float)[bad]
    bad = np.isnan(M).any(1) | (np.nan_to_num(M).sum(1) <= 0)
    M[bad] = 1.0
    M = np.maximum(np.clip(M, 0, None) / M.sum(1, keepdims=True), EPS)
    return M / M.sum(1, keepdims=True)


# --------------------------------------------------------------------------- uso en estrategias
_CACHE = {}


def load_params(path: str = PARAMS_PATH):
    if path not in _CACHE:
        if not os.path.exists(path):
            _CACHE[path] = None
        else:
            with open(path, encoding="utf-8") as fh:
                _CACHE[path] = json.load(fh)
    return _CACHE[path]


def _season(t) -> int:
    try:
        return int(str(t)[:4])
    except ValueError:
        return 0


def params_for(season: int, hasta: int | None = None, path: str = PARAMS_PATH):
    """Ajuste mas reciente cuyos datos son todos de temporadas < season (y <= hasta)."""
    data = load_params(path)
    if not data:
        return None
    best, best_end = None, -1
    for f in data.get("ajustes", []):
        end = int(f["hasta"])
        if end < season and (hasta is None or end <= hasta) and end > best_end:
            best, best_end = f, end
    return best


def corregir(info, history=None, hasta: int | None = None, path: str = PARAMS_PATH) -> np.ndarray:
    """Matriz 14x3 de % probables corregidos (filas suman 100).

    ``history`` no se usa (los parametros vienen ya estimados por temporadas en el JSON), pero se
    acepta por compatibilidad con la interfaz de estrategias. ``hasta`` limita la ultima temporada
    de ajuste (p. ej. 2022 = parametros fijos ajustados con 2017-2022)."""
    P = _norm_rows(info.prob, info.lae)
    L = _norm_rows(info.lae, info.prob)
    f = params_for(_season(info.temporada), hasta, path)
    if f is None:
        return P * 100.0
    gs = [grupo(m.local, m.visitante, m.division, info.fecha, f["esquema"]) for m in info.partidos]
    Q = apply(f["params"], np.log(P), np.log(L), gs)
    Q = np.maximum(Q, EPS)
    return 100.0 * Q / Q.sum(1, keepdims=True)
