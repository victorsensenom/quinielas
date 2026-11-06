"""Backtest walk-forward de estrategias de La Quiniela.

Para cada jornada (en orden temporada/jornada):
  1. la estrategia recibe ``jornada.info`` (solo pre-partido), ``history`` (tupla de jornadas
     completas ESTRICTAMENTE anteriores) y el presupuesto;
  2. se comprueba coste = n_columnas * precio_apuesta <= presupuesto;
  3. se cuentan aciertos (numpy) y se pagan los premios reales de jornadas.csv
     (estimados con el reparto oficial si la categoria quedo desierta, ver ``engine.rules``).

SUPUESTO: nuestro boleto no altera el reparto de premios (no nos anadimos como acertante
en categorias con acertantes reales). Es una aproximacion aceptable salvo en categorias con muy
pocos acertantes, donde el premio real que cobrariamos seria menor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .data import CATEGORIES, Jornada, season_year
from .rules import evaluate
from .strategy import as_columnset, call_strategy


class BudgetExceeded(Exception):
    pass


@dataclass
class BacktestConfig:
    budget: float = 48.0
    season_from: int | None = None       # anio de inicio de temporada (inclusive)
    season_to: int | None = None
    require_prizes: bool = False         # excluir jornadas sin datos de premios
    require_pct: bool = False            # excluir jornadas sin % (prob o lae) en los 14 partidos
    on_over_budget: str = "raise"        # 'raise' | 'truncate'
    estimate_missing: bool = True        # estimar premio si la categoria quedo desierta
    use_bote: bool = False               # sumar bote al fondo estimado de la categoria 15
    pleno_also_pays_14: bool = False     # True = regla real (15 cobra tambien 14); False = solo la maxima
    history_window: int | None = None    # limitar historia a las ultimas N jornadas (None = toda)


@dataclass
class BacktestResult:
    rows: list = field(default_factory=list)          # dict por jornada
    seasons: list = field(default_factory=list)       # dict por temporada
    summary: dict = field(default_factory=dict)
    columns: dict = field(default_factory=dict)       # (temporada, jornada) -> ColumnSet


def _in_range(j: Jornada, cfg: BacktestConfig) -> bool:
    y = season_year(j.temporada)
    if cfg.season_from is not None and y < cfg.season_from:
        return False
    if cfg.season_to is not None and y > cfg.season_to:
        return False
    return True


def run_backtest(jornadas: list[Jornada], strategy, cfg: BacktestConfig | None = None,
                 keep_columns: bool = False, progress=None) -> BacktestResult:
    cfg = cfg or BacktestConfig()
    jornadas = sorted(jornadas, key=lambda x: x.key)
    res = BacktestResult()
    history: list[Jornada] = []
    for i, j in enumerate(jornadas):
        complete = j.is_complete()
        reason = ""
        if not _in_range(j, cfg):
            reason = "fuera_rango"
        elif not complete:
            reason = "sin_resultado"
        elif cfg.require_prizes and not j.has_prizes():
            reason = "sin_premios"
        elif cfg.require_pct and not j.info.has_pct():
            reason = "sin_pct"

        if reason:
            if reason != "fuera_rango":
                res.rows.append(_empty_row(j, reason))
        else:
            hist = tuple(history if cfg.history_window is None else history[-cfg.history_window:])
            cs = as_columnset(call_strategy(strategy, j.info, hist, cfg.budget))
            precio = j.info.precio_apuesta
            cost = len(cs) * precio
            if cost > cfg.budget + 1e-9:
                if cfg.on_over_budget == "truncate":
                    k = int(math.floor(cfg.budget / precio + 1e-9))
                    cs = type(cs)(cs.signs[:k], cs.plenos[:k])
                    cost = len(cs) * precio
                else:
                    raise BudgetExceeded(
                        f"{j.temporada} J{j.jornada}: {len(cs)} columnas x {precio:.2f} = {cost:.2f} EUR "
                        f"> presupuesto {cfg.budget:.2f} EUR")
            ev = evaluate(cs, j, estimate_missing=cfg.estimate_missing, use_bote=cfg.use_bote,
                          pleno_also_pays_14=cfg.pleno_also_pays_14)
            row = {
                "temporada": j.temporada, "jornada": j.jornada, "fecha": j.info.fecha,
                "excluida": "", "columnas": len(cs), "precio": precio,
                "gasto": round(cost, 2), "cobrado": round(ev["cobrado"], 2),
                "beneficio": round(ev["cobrado"] - cost, 2),
                "roi": round((ev["cobrado"] - cost) / cost, 4) if cost > 0 else 0.0,
                "max_aciertos": ev["max_hits"], "mejor_premio": round(ev["mejor_premio"], 2),
                "cobrado_estimado": round(ev["cobrado_estimado"], 2),
                "cat_estimadas": " ".join(str(c) for c in ev["categorias_estimadas"]),
            }
            for c in CATEGORIES:
                row[f"n{c}"] = ev["n_cat"][c]
            res.rows.append(row)
            if keep_columns:
                res.columns[(j.temporada, j.jornada)] = cs
        if complete:
            history.append(j)
        if progress:
            progress(i + 1, len(jornadas), j)

    _add_cumulative(res.rows)
    res.seasons = season_summary(res.rows)
    res.summary = global_summary(res.rows)
    return res


def _empty_row(j: Jornada, reason: str) -> dict:
    row = {"temporada": j.temporada, "jornada": j.jornada, "fecha": j.info.fecha, "excluida": reason,
           "columnas": 0, "precio": j.info.precio_apuesta, "gasto": 0.0, "cobrado": 0.0, "beneficio": 0.0,
           "roi": 0.0, "max_aciertos": "", "mejor_premio": 0.0, "cobrado_estimado": 0.0, "cat_estimadas": ""}
    for c in CATEGORIES:
        row[f"n{c}"] = 0
    return row


def _add_cumulative(rows):
    g = c = 0.0
    for r in rows:
        g += r["gasto"]
        c += r["cobrado"]
        r["gasto_acum"] = round(g, 2)
        r["cobrado_acum"] = round(c, 2)
        r["beneficio_acum"] = round(c - g, 2)
        r["roi_acum"] = round((c - g) / g, 4) if g > 0 else 0.0


def _aggregate(rows) -> dict:
    played = [r for r in rows if not r["excluida"]]
    gasto = sum(r["gasto"] for r in played)
    cobrado = sum(r["cobrado"] for r in played)
    d = {
        "jornadas": len(played), "excluidas": len(rows) - len(played),
        "columnas": sum(r["columnas"] for r in played),
        "gasto": round(gasto, 2), "cobrado": round(cobrado, 2), "beneficio": round(cobrado - gasto, 2),
        "roi": round((cobrado - gasto) / gasto, 4) if gasto > 0 else 0.0,
        "mejor_premio": round(max([r["mejor_premio"] for r in played], default=0.0), 2),
        "cobrado_estimado": round(sum(r["cobrado_estimado"] for r in played), 2),
        "jornadas_con_premio": sum(1 for r in played if r["cobrado"] > 0),
    }
    for c in CATEGORIES:
        d[f"n{c}"] = sum(r[f"n{c}"] for r in played)
    d.update(risk_metrics([r["beneficio"] for r in played if r["gasto"] > 0 or r["cobrado"] > 0]))
    return d


def risk_metrics(profits) -> dict:
    """Maxima racha de jornadas con beneficio < 0 y drawdown maximo (EUR) del beneficio acumulado."""
    streak = best = 0
    for p in profits:
        streak = streak + 1 if p < 0 else 0
        best = max(best, streak)
    cum = np.cumsum(np.asarray(profits, float)) if len(profits) else np.zeros(0)
    if len(cum):
        peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
        dd = float((peak - cum).max())
    else:
        dd = 0.0
    return {"max_racha_negativa": best, "max_drawdown": round(dd, 2)}


def season_summary(rows) -> list[dict]:
    seasons: dict = {}
    for r in rows:
        seasons.setdefault(r["temporada"], []).append(r)
    out = []
    for t in sorted(seasons, key=lambda s: (season_year(s), s)):
        d = {"temporada": t}
        d.update(_aggregate(seasons[t]))
        out.append(d)
    return out


def global_summary(rows) -> dict:
    return _aggregate(rows)
