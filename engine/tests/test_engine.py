"""Tests del motor. Ejecutar desde quiniela\\:
    python -m unittest discover -s engine/tests -t . -v
"""
import copy
import io
import math
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import reduce as R  # noqa: E402
from engine.backtest import BacktestConfig, BudgetExceeded, risk_metrics, run_backtest  # noqa: E402
from engine.data import _build, load  # noqa: E402
from engine.rules import categories, count_hits, estimate_prize, evaluate  # noqa: E402
from engine.strategy import Column, ColumnSet, prob_matrix  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RESULT = "1X21X21X21X21X"          # resultado de la jornada manual
PREMIOS = {15: 1_000_000.0, 14: 50_000.0, 13: 1_000.0, 12: 100.0, 11: 10.0, 10: 2.0}


def make_jornada(temporada="2020-2021", jornada=1, result=RESULT, pleno="21", premios=None, acert=None,
                 recaudacion=5_000_000.0, precio="0.75"):
    premios = PREMIOS if premios is None else premios
    acert = acert or {c: 1 for c in premios}
    rows = {}
    for n in range(1, 16):
        rows[n] = {"local": f"L{n}", "visitante": f"V{n}", "division": "1",
                   "signo": result[n - 1] if n <= 14 else pleno, "resultado": "",
                   "lae1": "50", "laeX": "30", "lae2": "20", "prob1": "45", "probX": "30", "prob2": "25",
                   "quin1": "", "quinX": "", "quin2": ""}
    jr = {"fecha": "2020-10-01", "recaudacion": str(recaudacion), "bote": "0", "precio_apuesta": precio}
    for c in (15, 14, 13, 12, 11, 10):
        jr[f"premio{c}"] = str(premios.get(c, ""))
        jr[f"acert{c}"] = "" if acert.get(c) is None else str(acert[c])
    return _build(temporada, jornada, rows, jr)


def flip(s, k):
    """Cambia los k primeros signos de la cadena (fallos)."""
    nxt = {"1": "X", "X": "2", "2": "1"}
    return "".join(nxt[c] if i < k else c for i, c in enumerate(s))


class TestHits(unittest.TestCase):
    def test_count_hits(self):
        j = make_jornada()
        cs = ColumnSet.from_columns([Column.parse(flip(RESULT, k)) for k in range(15)])
        np.testing.assert_array_equal(count_hits(cs.signs, j.signos), 14 - np.arange(15))

    def test_categories(self):
        hits = np.array([14, 14, 13, 13, 12, 11, 10, 9, 0])
        ph = np.array([1, 0, 1, 0, 0, 0, 0, 1, 1], bool)
        np.testing.assert_array_equal(categories(hits, ph), [15, 14, 13, 13, 12, 11, 10, 0, 0])

    def test_pleno_only_counts_with_14(self):
        j = make_jornada()
        ev = evaluate(ColumnSet.from_columns([Column.parse(flip(RESULT, 1), "2-1")]), j)
        self.assertEqual(ev["n_cat"][15], 0)
        self.assertEqual(ev["n_cat"][13], 1)
        self.assertEqual(ev["cobrado"], PREMIOS[13])


class TestPrizes(unittest.TestCase):
    def test_15_vs_14(self):
        j = make_jornada()
        ev = evaluate(ColumnSet.from_columns([Column.parse(RESULT, "2-1")]), j)
        self.assertEqual(ev["n_cat"][15], 1)
        self.assertEqual(ev["n_cat"][14], 0)
        self.assertEqual(ev["cobrado"], PREMIOS[15])      # solo la de 15, no 15+14
        ev = evaluate(ColumnSet.from_columns([Column.parse(RESULT, "1-1")]), j)
        self.assertEqual((ev["n_cat"][15], ev["n_cat"][14]), (0, 1))
        self.assertEqual(ev["cobrado"], PREMIOS[14])
        # opcion regla real: 15 cobra tambien 14
        ev = evaluate(ColumnSet.from_columns([Column.parse(RESULT, "2-1")]), j, pleno_also_pays_14=True)
        self.assertEqual(ev["cobrado"], PREMIOS[15] + PREMIOS[14])

    def test_pleno_M(self):
        j = make_jornada(pleno="M0")
        self.assertEqual(evaluate(ColumnSet.from_columns([Column.parse(RESULT, "M-0")]), j)["n_cat"][15], 1)
        self.assertEqual(evaluate(ColumnSet.from_columns([Column.parse(RESULT, "2-0")]), j)["n_cat"][15], 0)

    def test_only_max_category(self):
        j = make_jornada()
        cols = [Column.parse(RESULT, "0-0"),            # 14
                Column.parse(flip(RESULT, 2)),          # 12
                Column.parse(flip(RESULT, 4)),          # 10
                Column.parse(flip(RESULT, 5))]          # 9 -> nada
        ev = evaluate(ColumnSet.from_columns(cols), j)
        self.assertEqual([ev["n_cat"][c] for c in (15, 14, 13, 12, 11, 10)], [0, 1, 0, 1, 0, 1])
        self.assertAlmostEqual(ev["cobrado"], PREMIOS[14] + PREMIOS[12] + PREMIOS[10])
        self.assertEqual(ev["mejor_premio"], PREMIOS[14])

    def test_estimate_prize(self):
        self.assertAlmostEqual(estimate_prize(1_000_000, 15), 75_000)
        self.assertAlmostEqual(estimate_prize(1_000_000, 14, 2), 80_000)
        self.assertAlmostEqual(estimate_prize(1_000_000, 10, 1_000_000), 0.0)   # < 1,50 -> 0
        self.assertTrue(math.isnan(estimate_prize(float("nan"), 13)))

    def test_estimate_when_nobody_won(self):
        prem = dict(PREMIOS)
        prem[15] = 0.0
        j = make_jornada(premios=prem, acert={15: 0, 14: 1, 13: 1, 12: 1, 11: 1, 10: 1}, recaudacion=2_000_000)
        ev = evaluate(ColumnSet.from_columns([Column.parse(RESULT, "2-1")] * 2), j)
        self.assertAlmostEqual(ev["cobrado"], 2_000_000 * 0.075)   # 2 columnas se reparten el fondo
        self.assertEqual(ev["categorias_estimadas"], [15])
        ev = evaluate(ColumnSet.from_columns([Column.parse(RESULT, "2-1")]), j, estimate_missing=False)
        self.assertEqual(ev["cobrado"], 0.0)

    def test_zero_prize_with_winners_is_real_zero(self):
        prem = dict(PREMIOS)
        prem[10] = 0.0
        j = make_jornada(premios=prem, acert={15: 1, 14: 1, 13: 1, 12: 1, 11: 1, 10: 500000})
        ev = evaluate(ColumnSet.from_columns([Column.parse(flip(RESULT, 4))]), j)
        self.assertEqual(ev["cobrado"], 0.0)
        self.assertEqual(ev["categorias_estimadas"], [])


class OneShot:
    def __init__(self, n):
        self.n = n

    def generate(self, info, history, budget):
        return ColumnSet(np.zeros((self.n, 14), np.int8))


class TestBudget(unittest.TestCase):
    def setUp(self):
        self.js = [make_jornada()]

    def test_within_budget(self):
        r = run_backtest(self.js, OneShot(64), BacktestConfig(budget=48))
        self.assertEqual(r.rows[0]["gasto"], 48.0)

    def test_over_budget_raises(self):
        with self.assertRaises(BudgetExceeded):
            run_backtest(self.js, OneShot(65), BacktestConfig(budget=48))

    def test_truncate(self):
        r = run_backtest(self.js, OneShot(100), BacktestConfig(budget=48, on_over_budget="truncate"))
        self.assertEqual(r.rows[0]["columnas"], 64)

    def test_price_from_csv_and_default(self):
        js = load(DATA)
        self.assertEqual({j.info.precio_apuesta for j in js if j.temporada == "2018-2019"}, {0.5})
        self.assertEqual({j.info.precio_apuesta for j in js if j.temporada == "2020-2021"}, {0.75})
        r = run_backtest(js, OneShot(96), BacktestConfig(budget=48, season_to=2018))
        self.assertTrue(all(row["gasto"] == 48.0 for row in r.rows if not row["excluida"]))


class Spy:
    """Estrategia que registra lo que ve e intenta leer el futuro."""
    def __init__(self):
        self.seen = []

    def generate(self, info, history, budget):
        forbidden = ("signos", "signo", "resultado", "resultados", "premios", "acertantes", "recaudacion",
                     "pleno_res", "bote")
        for name in forbidden:
            assert not hasattr(info, name), name
            for m in info.partidos:
                assert not hasattr(m, name), name
        assert not info.lae.flags.writeable and not info.prob.flags.writeable
        for h in history:
            assert h.key < info.key, "historia contiene jornada no anterior"
        self.seen.append((info.key, len(history)))
        P = prob_matrix(info)
        return [Column(tuple(int(x) for x in P.argmax(1)))]


class TestNoLeak(unittest.TestCase):
    def test_info_has_no_future(self):
        js = load(DATA)
        spy = Spy()
        r = run_backtest(js, spy, BacktestConfig(budget=1))
        self.assertTrue(len(spy.seen) > 10)
        # historia creciente y solo con jornadas completas anteriores
        self.assertEqual(spy.seen[0][1], 0)

    def test_frozen(self):
        j = make_jornada()
        with self.assertRaises(Exception):
            j.info.temporada = "x"
        with self.assertRaises(ValueError):
            j.info.prob[0, 0] = 99.0

    def test_result_change_does_not_change_columns(self):
        js = load(DATA)
        a, b = Spy(), Spy()
        ra = run_backtest(js, a, BacktestConfig(budget=1), keep_columns=True)
        # misma informacion pre-partido, resultados de la jornada en curso alterados
        mutated = []
        for j in js:
            new_s = np.where(j.signos >= 0, (j.signos + 1) % 3, j.signos).astype(np.int8)
            new_s.flags.writeable = False
            mutated.append(type(j)(**{**{f: getattr(j, f) for f in j.__dataclass_fields__}, "signos": new_s}))
        rb = run_backtest(mutated, b, BacktestConfig(budget=1), keep_columns=True)
        self.assertEqual(ra.columns.keys(), rb.columns.keys())
        for k in ra.columns:
            np.testing.assert_array_equal(ra.columns[k].signs, rb.columns[k].signs)


class TestData(unittest.TestCase):
    def test_load_and_exclusions(self):
        js = load(DATA)
        self.assertEqual(len(js), 18)
        self.assertEqual([j.key for j in js], sorted(j.key for j in js))
        inc = [j for j in js if not j.is_complete()]
        self.assertEqual([(j.temporada, j.jornada) for j in inc], [("2020-2021", 6)])
        r = run_backtest(js, Spy(), BacktestConfig(budget=1, require_prizes=True, require_pct=True))
        ex = {(row["temporada"], row["jornada"]): row["excluida"] for row in r.rows if row["excluida"]}
        self.assertEqual(ex, {("2019-2020", 5): "sin_premios", ("2020-2021", 2): "sin_pct",
                              ("2020-2021", 6): "sin_resultado"})


class TestMetrics(unittest.TestCase):
    def test_risk(self):
        m = risk_metrics([-1, -1, 5, -2, -2, -2, 1])
        self.assertEqual(m["max_racha_negativa"], 3)
        self.assertEqual(m["max_drawdown"], 6.0)    # pico 3 -> minimo -3

    def test_season_and_global(self):
        js = load(DATA)
        r = run_backtest(js, OneShot(2), BacktestConfig(budget=48))
        self.assertAlmostEqual(sum(s["gasto"] for s in r.seasons), r.summary["gasto"])
        self.assertAlmostEqual(r.rows[-1]["beneficio_acum"], r.summary["beneficio"], places=2)


class TestReduce(unittest.TestCase):
    P = np.array([[20, 25, 55], [65, 20, 15], [16, 17, 67], [30, 28, 42], [44, 29, 27], [29, 27, 44],
                  [76, 15, 9], [37, 30, 33], [27, 26, 47], [37, 31, 32], [62, 23, 15], [77, 15, 8],
                  [34, 30, 36], [62, 21, 17]], float)

    def test_index_roundtrip_and_base(self):
        base = ["1X2", "1X", "X2"] + ["1"] * 11
        idx = R.expand_base(base)
        self.assertEqual(len(idx), 12)
        cols = R.idx_to_cols(idx)
        np.testing.assert_array_equal(R.cols_to_idx(cols), idx)
        self.assertTrue((cols[:, 3:] == 0).all())

    def test_neighbors_and_coverage(self):
        w = R.space_weights(self.P)
        self.assertAlmostEqual(w.sum(), 1.0)
        nb = R.neighbors([123456], 2)[0]
        self.assertEqual(len(np.unique(nb)), 393)
        d = (R.idx_to_cols(nb) != R.idx_to_cols([123456])).sum(1)
        self.assertEqual(d.max(), 2)

    def test_greedy_matches_bruteforce_coverage(self):
        P = self.P / self.P.sum(1, keepdims=True)
        sel, info = R.greedy_cover(P, 16, radius=1, return_info=True)
        self.assertEqual(len(set(sel.tolist())), 16)
        # cobertura por fuerza bruta: aciertos >= 13 contra todo el espacio (muestra completa)
        w = R.space_weights(P)
        grid = R.idx_to_cols(np.arange(R.TOTAL))
        grid_best = np.full(R.TOTAL, 99, np.int8)
        for c in R.idx_to_cols(sel):
            grid_best = np.minimum(grid_best, (grid != c).sum(1, dtype=np.int8))
        self.assertAlmostEqual(float(w[grid_best <= 1].sum()), info["coverage"], places=10)
        # el primer elegido es la columna de maxima masa en su bola
        self.assertGreaterEqual(info["gains"][0], info["gains"][-1])

    def test_filters(self):
        P = self.P / self.P.sum(1, keepdims=True)
        idx = R.filter_counts(None, n1=(4, 9), nx=(1, 6), n2=(2, 6))
        c1, cx, c2 = R.count_signs(idx[:1000])
        self.assertTrue(((c1 >= 4) & (c1 <= 9) & (cx >= 1) & (cx <= 6) & (c2 >= 2) & (c2 <= 6)).all())
        sub = R.filter_surprises(idx[:5000], P, 0.2, 2)
        self.assertTrue((R.surprises(P, 0.2, sub) <= 2).all())
        sel = R.greedy_cover(P, 8, candidates=sub)
        self.assertTrue(np.isin(sel, sub).all())


class TestCLI(unittest.TestCase):
    def test_run_both_strategies(self):
        from engine import run
        out = tempfile.mkdtemp()
        try:
            for name in ("fijo_favoritos", "aleatoria"):
                d = os.path.join(out, name)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    res = run.main(["--strategy", name, "--budget", "48", "--from", "2018", "--to", "2026",
                                    "--out", d, "--data", DATA, "--quiet"])
                for f in ("jornadas.csv", "temporadas.csv", "resumen.txt"):
                    self.assertTrue(os.path.exists(os.path.join(d, f)))
                self.assertGreater(res.summary["jornadas"], 0)
            # aleatoria gasta todo el presupuesto; favoritos 1 columna
            self.assertEqual(res.rows[0]["gasto"], 48.0)
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
