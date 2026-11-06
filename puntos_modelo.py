"""Modelos del sistema de puntos (solo numpy).

Modelo A (puntos propios, sin cuotas). Una unica puntuacion por partido:
    S = casa + w1*x1 + w2*x2 + ...           (x = variables local - visitante)
    P(1) = sig(S - h)    P(2) = sig(-S - h)    P(X) = 1 - P(1) - P(2)         sig = logistica
S grande: gana el local; S muy negativo: gana el visitante; S cerca de 0: partido abierto.

Modelo B (cuotas + correccion).  Sobre los % probables p:
    u1 = T*log p1 + d + C    uX = T*log pX + c    u2 = T*log p2 - C       q proporcional a exp(u)
con C = w1*x1 + ...  (0 si el partido no tiene datos de liga) mas, opcionalmente, terminos por signo
(``Z``, shape n,3,m), por ejemplo el % de tecnicos.
"""
from __future__ import annotations

import numpy as np


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def bfgs(f, x0, maxit=500, tol=1e-7):
    """Minimiza f(x) -> (valor, gradiente) con BFGS y busqueda hacia atras."""
    x = np.array(x0, float)
    n = len(x)
    H = np.eye(n)
    v, g = f(x)
    for _ in range(maxit):
        d = -H @ g
        if g @ d >= 0:
            H = np.eye(n)
            d = -g
        t, ok = 1.0, False
        for _ in range(40):
            v2, g2 = f(x + t * d)
            if np.isfinite(v2) and v2 <= v + 1e-4 * t * (g @ d):
                ok = True
                break
            t *= 0.5
        if not ok:
            break
        s, y = t * d, g2 - g
        x, v, g = x + s, v2, g2
        if np.abs(g).max() < tol:
            break
        sy = s @ y
        if sy > 1e-12:
            I = np.eye(n)
            r = 1.0 / sy
            H = (I - r * np.outer(s, y)) @ H @ (I - r * np.outer(y, s)) + r * np.outer(s, s)
    return x


# --------------------------------------------------------------------------- modelo A
def prob_a(casa, h, w, X):
    S = casa + X @ np.asarray(w, float) if X.shape[1] else np.full(len(X), casa)
    p1, p2 = sig(S - h), sig(-S - h)
    px = np.maximum(1 - p1 - p2, 1e-6)
    P = np.stack([p1, px, p2], 1)
    return P / P.sum(1, keepdims=True)


def ajustar_a(X, y, lam=0.0):
    """Maxima verosimilitud con penalizacion ridge ``lam`` (por partido) sobre X estandarizada."""
    X = np.asarray(X, float)
    y = np.asarray(y)
    n, m = X.shape
    sd = X.std(0) if m else np.zeros(0)
    sd = np.where(sd > 0, sd, 1.0)
    Z = X / sd if m else X
    Y = np.eye(3)[y]

    def f(t):
        casa, lh, w = t[0], t[1], t[2:]
        h = np.exp(lh)
        S = casa + (Z @ w if m else 0.0)
        s1, s2 = sig(S - h), sig(-S - h)
        px = np.maximum(1 - s1 - s2, 1e-9)
        ll = Y[:, 0] * np.log(s1) + Y[:, 1] * np.log(px) + Y[:, 2] * np.log(s2)
        # derivadas de P respecto a S y h
        d1, d2 = s1 * (1 - s1), s2 * (1 - s2)
        dS = Y[:, 0] * (1 - s1) - Y[:, 2] * (1 - s2) + Y[:, 1] * (-d1 + d2) / px
        dh = -Y[:, 0] * (1 - s1) - Y[:, 2] * (1 - s2) + Y[:, 1] * (d1 + d2) / px
        g = np.concatenate([[-dS.sum()], [-(dh * h).sum()], -(Z.T @ dS) if m else np.zeros(0)]) / n
        if m:
            g[2:] += 2 * lam * w
        return -ll.mean() + lam * float(w @ w), g

    t = bfgs(f, np.concatenate([[0.25, np.log(0.4)], np.zeros(m)]))
    return {"casa": float(t[0]), "h": float(np.exp(t[1])), "w": (t[2:] / sd).tolist()}


# --------------------------------------------------------------------------- modelo B
def prob_b(par, logp, X, cubierto, Z=None):
    n = len(logp)
    T, c, d = par["T"], par["c"], par["d"]
    C = (X @ np.asarray(par["w"], float)) * cubierto if X.shape[1] else np.zeros(n)
    U = T * logp
    U = U + np.stack([d + C, np.full(n, c), -C], 1)
    if Z is not None and len(par.get("g", [])):
        U = U + Z @ np.asarray(par["g"], float)
    U -= U.max(1, keepdims=True)
    P = np.exp(U)
    return P / P.sum(1, keepdims=True)


def ajustar_b(logp, X, cubierto, y, lam=0.0, Z=None):
    logp, X = np.asarray(logp, float), np.asarray(X, float)
    y = np.asarray(y)
    n, m = X.shape
    k = Z.shape[2] if Z is not None else 0
    sd = X.std(0) if m else np.zeros(0)
    sd = np.where(sd > 0, sd, 1.0)
    Xs = (X / sd if m else X) * cubierto[:, None]
    zs = np.ones(k)
    if k:
        zs = np.sqrt((Z ** 2).mean((0, 1)))
        zs = np.where(zs > 0, zs, 1.0)
    Zs = Z / zs if k else None
    rows = np.arange(n)

    def f(t):
        T, c, d, w, g = t[0], t[1], t[2], t[3:3 + m], t[3 + m:]
        C = Xs @ w if m else np.zeros(n)
        U = T * logp + np.stack([d + C, np.full(n, c), -C], 1)
        if k:
            U = U + Zs @ g
        U0 = U - U.max(1, keepdims=True)
        E = np.exp(U0)
        P = E / E.sum(1, keepdims=True)
        v = -np.log(P[rows, y]).mean()
        R = np.eye(3)[y] - P                       # d loglik / dU
        gr = np.zeros(len(t))
        gr[0] = -(R * logp).sum() / n
        gr[1] = -R[:, 1].sum() / n
        gr[2] = -R[:, 0].sum() / n
        if m:
            gr[3:3 + m] = -(Xs.T @ (R[:, 0] - R[:, 2])) / n + 2 * lam * w
        if k:
            gr[3 + m:] = -(R[:, :, None] * Zs).sum((0, 1)) / n + 2 * lam * g
        return v + lam * (float(w @ w) + float(g @ g)), gr

    t = bfgs(f, np.concatenate([[1.0, 0.0, 0.0], np.zeros(m + k)]))
    return {"T": float(t[0]), "c": float(t[1]), "d": float(t[2]), "w": (t[3:3 + m] / sd).tolist(),
            "g": (t[3 + m:] / zs).tolist()}


def log_loss(P, y):
    P = np.asarray(P, float)
    return -np.log(np.maximum(P[np.arange(len(P)), np.asarray(y)], 1e-9))
