"""Tests de strategies/calibracion.py y de los filtros de valor_mix_forma.
    python -m unittest discover -s engine/tests -t . -v
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine.data import load  # noqa: E402
from engine.reduce import idx_to_cols  # noqa: E402
from strategies import calibracion as cal  # noqa: E402
from strategies.valor_mix_forma import candidatos, forma_counts  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class TestCalibracion(unittest.TestCase):
    def test_fit_recupera_temperatura(self):
        rng = np.random.default_rng(0)
        n = 6000
        p = rng.dirichlet([3, 2, 2], n)
        T, cx = 1.3, 0.2
        z = T * np.log(p)
        z[:, 1] += cx
        q = np.exp(z) / np.exp(z).sum(1, keepdims=True)
        y = np.array([rng.choice(3, p=r) for r in q])
        prm = cal.fit(np.log(p), np.log(p), y, ["all"] * n)
        self.assertAlmostEqual(prm["global"][0], T, delta=0.12)
        self.assertAlmostEqual(prm["global"][1], cx, delta=0.12)

    def test_sin_fuga_temporal(self):
        """corregir() solo usa ajustes con 'hasta' < temporada (y <= hasta pedido)."""
        prm = {"use_lae": False, "global": [2.0, 0.5, 0.0], "grupos": {}}
        data = {"ajustes": [{"desde": 2017, "hasta": h, "esquema": "global", "params": prm} for h in (2019, 2020)]}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.json")
            with open(path, "w") as fh:
                json.dump(data, fh)
            self.assertIsNone(cal.params_for(2019, path=path))
            self.assertEqual(cal.params_for(2020, path=path)["hasta"], 2019)
            self.assertEqual(cal.params_for(2021, path=path)["hasta"], 2020)
            self.assertEqual(cal.params_for(2021, hasta=2019, path=path)["hasta"], 2019)
            info = load(DATA)[0].info
            Q = cal.corregir(info, None, path=path)
            self.assertEqual(Q.shape, (14, 3))
            np.testing.assert_allclose(Q.sum(1), 100.0, atol=1e-6)

    def test_categorias(self):
        self.assertEqual(cal.categoria("BARCELONA (F)", "R.MADRID (F)", "10"), "fem")
        self.assertEqual(cal.categoria("ESTADOS UNIDOS F", "ALEMANIA F", "6"), "fem")
        self.assertEqual(cal.categoria("ESPAÑA", "PAÍSES BAJOS", "5"), "sel")
        self.assertEqual(cal.categoria("PSG", "R.SOCIEDAD", "5"), "ext")
        self.assertEqual(cal.categoria("SEVILLA", "BETIS", "1"), "esp")


class TestForma(unittest.TestCase):
    def test_counts(self):
        rng = np.random.default_rng(1)
        P = rng.dirichlet([2, 2, 2], 14)
        nf, ns = forma_counts(P)
        idx = rng.integers(0, 3 ** 14, 200)
        C = idx_to_cols(idx)
        np.testing.assert_array_equal(nf[idx], (C == P.argmax(1)).sum(1))
        np.testing.assert_array_equal(ns[idx], (C == P.argmin(1)).sum(1))
        cand = candidatos(P, (5, 10), (1, 5), (nf, ns))
        self.assertTrue(((nf[cand] >= 5) & (nf[cand] <= 10) & (ns[cand] >= 1) & (ns[cand] <= 5)).all())


if __name__ == "__main__":
    unittest.main()
