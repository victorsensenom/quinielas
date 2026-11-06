"""Reglas de acierto, categorias y premios.

Reglas implementadas (segun especificacion del proyecto):
  * Una columna = 14 signos + pronostico del pleno (goles local / visitante en 0,1,2,M).
  * Categorias: 15 (14 aciertos + pleno correcto), 14, 13, 12, 11, 10.
  * El pleno SOLO cuenta si la columna tiene 14 aciertos.
  * Una columna cobra UNICAMENTE su categoria maxima: 14+pleno cobra la de 15 y no la de 14.
    (En la Quiniela real el acertante del Pleno al 15 suele cobrar tambien la de 14; si se quiere
    ese comportamiento, ``pleno_also_pays_14=True``.)
  * Pleno en formato antiguo (signo 1/X/2 en vez de goles): se compara el signo derivado de los
    goles pronosticados (M=3 goles) con el signo real.

Estimacion de premios (``estimate_prize``) - SOLO cuando la categoria quedo sin acertantes reales
y nuestra columna la habria ganado. Reparto oficial vigente de La Quiniela (normas SELAE, 55% de la
recaudacion integra a premios):
    Especial (Pleno al 15) 7,5% | 1a (14) 16% | 2a (13) 7,5% | 3a (12) 7,5% | 4a (11) 7,5% | 5a (10) 9%
  Fuentes: normas de La Quiniela (SELAE, temporadas 2015-16 y 2019-20) y es.wikipedia.org/wiki/La_Quiniela_(España).
  Simplificaciones: el fondo de la categoria especial se incrementa con el bote solo si se pasa
  ``use_bote=True`` (por defecto NO, porque no esta claro si la columna ``bote`` del CSV es el bote
  recibido o el generado); se ignoran los arrastres entre categorias (13->12->11->10) y la regla de que un premio
  inferior no supere a uno superior; en 5a categoria, si el premio unitario < 1,50 EUR no se paga.
  Es una ESTIMACION.

Supuesto general: nuestro boleto no altera el reparto (no se recalcula el premio por acertante
anadiendonos como acertante adicional en categorias que ya tienen acertantes reales).
"""
from __future__ import annotations

import math

import numpy as np

from .data import CATEGORIES, N_MATCHES

PRIZE_POOL_PCT = 0.55
PRIZE_PCT = {15: 0.075, 14: 0.16, 13: 0.075, 12: 0.075, 11: 0.075, 10: 0.09}
MIN_PRIZE_10 = 1.50


def estimate_prize(recaudacion: float, categoria: int, acertantes: int = 1, bote: float = 0.0) -> float:
    """Premio estimado POR ACERTANTE de una categoria segun el reparto oficial de LAE/SELAE.

    ``acertantes`` = numero total de acertantes que se repartirian el fondo (>=1). Para
    categoria 15 se suma ``bote`` al fondo. Devuelve NaN si no hay recaudacion. ESTIMACION.
    """
    if categoria not in PRIZE_PCT:
        raise ValueError(f"categoria invalida: {categoria}")
    if recaudacion is None or (isinstance(recaudacion, float) and math.isnan(recaudacion)):
        return math.nan
    fondo = recaudacion * PRIZE_PCT[categoria]
    if categoria == 15 and bote and not math.isnan(bote):
        fondo += bote
    p = fondo / max(int(acertantes), 1)
    if categoria == 10 and p < MIN_PRIZE_10:
        return 0.0
    return p


def count_hits(signs: np.ndarray, result: np.ndarray) -> np.ndarray:
    """Aciertos de cada columna. signs (K,14) int8, result (14,) int8 -> (K,) int."""
    signs = np.asarray(signs).reshape(-1, N_MATCHES)
    return (signs == np.asarray(result, np.int8)[None, :]).sum(1)


def pleno_ok(plenos: np.ndarray, pleno_tipo, pleno_res) -> np.ndarray:
    plenos = np.asarray(plenos).reshape(-1, 2)
    if pleno_tipo == "goals":
        return (plenos[:, 0] == pleno_res[0]) & (plenos[:, 1] == pleno_res[1])
    if pleno_tipo == "sign":
        gl, gv = plenos[:, 0].astype(int), plenos[:, 1].astype(int)
        sign = np.where(gl > gv, 0, np.where(gl == gv, 1, 2))
        return sign == pleno_res
    return np.zeros(len(plenos), bool)


def categories(hits: np.ndarray, pleno_hit: np.ndarray) -> np.ndarray:
    """Categoria maxima de cada columna: 15, 14..10, o 0 si no hay premio."""
    hits = np.asarray(hits)
    cat = np.where(hits >= 10, hits, 0)
    return np.where((hits == 14) & np.asarray(pleno_hit, bool), 15, cat)


def evaluate(cs, jornada, estimate_missing: bool = True, use_bote: bool = False,
             pleno_also_pays_14: bool = False) -> dict:
    """Evalua un ColumnSet contra una Jornada completa.

    Devuelve dict con: hits (K,), cat (K,), n_cat {cat: n}, cobrado, cobrado_estimado,
    mejor_premio, max_hits, premio_unit {cat: premio usado}.
    """
    hits = count_hits(cs.signs, jornada.signos)
    ph = pleno_ok(cs.plenos, jornada.pleno_tipo, jornada.pleno_res)
    cat = categories(hits, ph)
    n_cat = {c: int((cat == c).sum()) for c in CATEGORIES}
    pays = {c: n_cat[c] for c in CATEGORIES}
    if pleno_also_pays_14:
        pays[14] += n_cat[15]

    unit, estimated, total, est_total = {}, set(), 0.0, 0.0
    for c in CATEGORIES:
        if pays[c] == 0:
            continue
        real = jornada.premios.get(c, math.nan)
        acert = jornada.acertantes.get(c)
        if not math.isnan(real) and (real > 0 or (acert is not None and acert > 0)):
            # premio real publicado (0 legitimo si hubo acertantes, p.ej. 10 aciertos < 1,50 EUR)
            p = real
        elif estimate_missing:
            # nadie acerto (premio 0 / acertantes 0) o falta el dato: estimar con el reparto oficial,
            # repartiendo entre acertantes reales conocidos + nuestras columnas
            n = (acert or 0) + pays[c]
            p = estimate_prize(jornada.recaudacion, c, n, jornada.bote if use_bote else 0.0)
            p = 0.0 if math.isnan(p) else p
            estimated.add(c)
            est_total += p * pays[c]
        else:
            p = 0.0
        unit[c] = p
        total += p * pays[c]

    paid_units = [unit[c] for c in CATEGORIES if n_cat[c] > 0 and c in unit]
    if pleno_also_pays_14 and n_cat[15] > 0:
        best = unit.get(15, 0.0) + unit.get(14, 0.0)
        paid_units.append(best)
    return {
        "hits": hits, "cat": cat, "n_cat": n_cat, "cobrado": total, "cobrado_estimado": est_total,
        "categorias_estimadas": sorted(estimated, reverse=True),
        "mejor_premio": max(paid_units) if paid_units else 0.0,
        "max_hits": int(hits.max()) if len(hits) else 0, "premio_unit": unit,
    }
