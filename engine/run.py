"""CLI del motor de backtesting.

Uso (desde la carpeta quiniela\\):
    python -m engine.run --strategy fijo_favoritos --budget 48 --from 2017 --to 2026 --out results\\favoritos
    python -m engine.run --strategy aleatoria --budget 48 --param seed=7 --out results\\aleatoria

--strategy acepta un nombre de modulo de strategies\\ ('aleatoria'), un modulo con puntos
('strategies.aleatoria') o una ruta a un .py.
--from / --to filtran por ANIO DE INICIO de temporada ('2019-2020' -> 2019), inclusive.
Escribe en --out: jornadas.csv, temporadas.csv y resumen.txt.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.backtest import BacktestConfig, run_backtest  # noqa: E402
from engine.data import load  # noqa: E402
from engine.rules import PRIZE_PCT  # noqa: E402
from engine.strategy import load_strategy  # noqa: E402


def _parse_value(v: str):
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def _write_csv(path, rows):
    if not rows:
        open(path, "w", encoding="utf-8").close()
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def format_summary(name, cfg, s, seasons, elapsed) -> str:
    L = [f"Estrategia: {name}",
         f"Presupuesto por jornada: {cfg.budget:.2f} EUR | temporadas {cfg.season_from or '-'}..{cfg.season_to or '-'}"
         f" | require_prizes={cfg.require_prizes} require_pct={cfg.require_pct}",
         f"Jornadas jugadas: {s['jornadas']} (excluidas: {s['excluidas']}) | columnas: {s['columnas']}",
         f"Gasto: {s['gasto']:.2f} EUR | Cobrado: {s['cobrado']:.2f} EUR (de ello estimado: {s['cobrado_estimado']:.2f})",
         f"Beneficio: {s['beneficio']:.2f} EUR | ROI: {s['roi'] * 100:.2f} %",
         f"Premios: 15={s['n15']} 14={s['n14']} 13={s['n13']} 12={s['n12']} 11={s['n11']} 10={s['n10']}"
         f" | jornadas con premio: {s['jornadas_con_premio']} | mejor premio: {s['mejor_premio']:.2f} EUR",
         f"Max racha negativa: {s['max_racha_negativa']} jornadas | Drawdown max: {s['max_drawdown']:.2f} EUR",
         "", "Por temporada:",
         f"{'temporada':>12} {'jorn':>5} {'gasto':>10} {'cobrado':>11} {'benef':>11} {'ROI%':>8} "
         f"{'15':>3} {'14':>3} {'13':>4} {'12':>5} {'11':>6} {'10':>6} {'mejor':>11}"]
    for t in seasons:
        L.append(f"{t['temporada']:>12} {t['jornadas']:>5} {t['gasto']:>10.2f} {t['cobrado']:>11.2f} "
                 f"{t['beneficio']:>11.2f} {t['roi'] * 100:>8.2f} {t['n15']:>3} {t['n14']:>3} {t['n13']:>4} "
                 f"{t['n12']:>5} {t['n11']:>6} {t['n10']:>6} {t['mejor_premio']:>11.2f}")
    L += ["", "Supuestos:",
          "- Premios reales de jornadas.csv; nuestro boleto no altera el reparto.",
          "- Si una categoria quedo desierta (o falta el premio) y la acertamos, premio ESTIMADO con el reparto "
          "oficial: " + ", ".join(f"{c}: {p * 100:.1f}%" for c, p in PRIZE_PCT.items()) + " de la recaudacion (55% total).",
          "- Una columna cobra solo su categoria maxima (15 no cobra ademas 14)"
          + (" [desactivado: --pleno-paga-14]" if cfg.pleno_also_pays_14 else "") + ".",
          "- Precio por columna: precio_apuesta de jornadas.csv; si falta, 0,75 EUR desde 2019-20 y 0,50 EUR antes.",
          f"Tiempo: {elapsed:.1f} s"]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest de estrategias de La Quiniela")
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--budget", type=float, default=48.0)
    ap.add_argument("--from", dest="season_from", type=int, default=None)
    ap.add_argument("--to", dest="season_to", type=int, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--param", action="append", default=[], help="k=v para la estrategia (repetible)")
    ap.add_argument("--require-prizes", action="store_true", help="excluir jornadas sin datos de premios")
    ap.add_argument("--require-pct", action="store_true", help="excluir jornadas sin %% prob/lae")
    ap.add_argument("--truncate", action="store_true", help="recortar columnas que excedan el presupuesto en vez de abortar")
    ap.add_argument("--no-estimate", action="store_true", help="no estimar premios de categorias desiertas")
    ap.add_argument("--use-bote", action="store_true", help="sumar el bote al fondo estimado de la categoria 15")
    ap.add_argument("--pleno-paga-14", action="store_true", help="el acertante de 15 cobra tambien la de 14")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    params = {}
    for p in a.param:
        k, _, v = p.partition("=")
        params[k.strip()] = _parse_value(v.strip())
    strat = load_strategy(a.strategy, params, search_dirs=[os.path.join(ROOT, "strategies")])
    cfg = BacktestConfig(budget=a.budget, season_from=a.season_from, season_to=a.season_to,
                         require_prizes=a.require_prizes, require_pct=a.require_pct,
                         on_over_budget="truncate" if a.truncate else "raise",
                         estimate_missing=not a.no_estimate, use_bote=a.use_bote,
                         pleno_also_pays_14=a.pleno_paga_14)
    jornadas = load(a.data)
    t0 = time.time()

    def prog(i, n, j):
        if not a.quiet and (i % 25 == 0 or i == n):
            print(f"\r{i}/{n} {j.temporada} J{j.jornada}   ", end="", file=sys.stderr, flush=True)

    res = run_backtest(jornadas, strat, cfg, progress=prog)
    if not a.quiet:
        print(file=sys.stderr)
    os.makedirs(a.out, exist_ok=True)
    _write_csv(os.path.join(a.out, "jornadas.csv"), res.rows)
    _write_csv(os.path.join(a.out, "temporadas.csv"), res.seasons)
    txt = format_summary(a.strategy + (f" {params}" if params else ""), cfg, res.summary, res.seasons,
                         time.time() - t0)
    with open(os.path.join(a.out, "resumen.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    print(txt)
    return res


if __name__ == "__main__":
    main()
