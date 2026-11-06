"""Sistema de puntos: ninguna variable mira el futuro; modelos y formas de boleto correctos."""
import datetime as dt
import os
import random
import unittest

import numpy as np

import ligas
import puntos_features as pf
import puntos_modelo as pm
from strategies import puntos_comun as pc


def partido(fecha, t, loc, vis, gl, gv, div="SP1"):
    return {"fecha": fecha, "div": div, "temporada": t, "local": loc, "visitante": vis, "gl": gl, "gv": gv}


def liga_sintetica(seed=3, n=600):
    rng = random.Random(seed)
    eq = [f"E{i}" for i in range(12)]
    d0 = dt.date(2020, 8, 15)
    out = []
    for k in range(n):
        a, b = rng.sample(eq, 2)
        out.append(partido(d0 + dt.timedelta(days=k // 3), 2021 + k // 300, a, b, rng.randint(0, 3), rng.randint(0, 3)))
    return out


class TestSinFuturo(unittest.TestCase):
    def _compara(self, partidos, muestras, seed=1):
        """Las variables en ``corte`` no cambian al borrar o alterar todo lo jugado desde ``corte``."""
        h = pf.Historial(partidos)
        rng = random.Random(seed)
        for m in rng.sample(partidos, muestras):
            corte = m["fecha"]
            v = pf.variables(h, m["local"], m["visitante"], m["temporada"], m["div"], corte)
            pasado = [x for x in partidos if x["fecha"] < corte]
            self.assertEqual(v, pf.variables(pf.Historial(pasado), m["local"], m["visitante"], m["temporada"],
                                             m["div"], corte))
            revuelto = pasado + [dict(x, gl=9, gv=0) for x in partidos if x["fecha"] >= corte]
            self.assertEqual(v, pf.variables(pf.Historial(revuelto), m["local"], m["visitante"], m["temporada"],
                                             m["div"], corte))

    def test_sintetico(self):
        self._compara(liga_sintetica(), 60)

    @unittest.skipUnless(os.path.exists(ligas.ruta("SP1", 2026)), "sin datos de liga")
    def test_datos_reales(self):
        self._compara(ligas.partidos_liga(), 40)

    def test_mismo_dia_no_cuenta(self):
        d = dt.date(2021, 1, 10)
        a = [partido(d - dt.timedelta(days=7), 2021, "A", "B", 3, 0)]
        b = a + [partido(d, 2021, "A", "C", 5, 0)]
        self.assertEqual(pf.variables(pf.Historial(a), "A", "B", 2021, "SP1", d),
                         pf.variables(pf.Historial(b), "A", "B", 2021, "SP1", d))

    @unittest.skipUnless(os.path.exists(pf.F_QUINIELA), "sin tabla de variables")
    def test_tabla_quiniela(self):
        """Cada fila cubierta de la tabla se reproduce con solo partidos anteriores al corte de su jornada,
        y el corte nunca es posterior al partido."""
        filas = [r for r in pf.leer_tabla() if r["cubierto"] == "1"]
        partidos = ligas.partidos_liga()
        idx = pf.indice_liga(partidos)
        self.assertGreater(len(filas), 5000)
        for r in filas:
            self.assertLessEqual(r["corte"], r["fecha_liga"])
        for r in random.Random(5).sample(filas, 40):
            t = int(r["temporada"])
            corte = min(dt.date.fromisoformat(r["corte"]), dt.date.fromisoformat(r["fecha_liga"]))
            loc, vis = ligas.nombre_q(r["local"]), ligas.nombre_q(r["visitante"])
            self.assertIn((t, loc, vis), idx)
            h = pf.Historial([m for m in partidos if m["fecha"] < corte])
            v = pf.variables(h, loc, vis, t, r["div"], corte)
            for k in pf.VARS:
                self.assertAlmostEqual(float(r[k]), float(v[k]), places=3, msg=f"{r} {k}")


class TestVariables(unittest.TestCase):
    def test_calculos(self):
        d = dt.date(2021, 1, 1)
        ms = [partido(d, 2021, "A", "B", 2, 0), partido(d + dt.timedelta(days=7), 2021, "C", "A", 0, 1),
              partido(d + dt.timedelta(days=14), 2021, "A", "C", 1, 1)]
        h = pf.Historial(ms)
        r = pf.resumen_equipo(h.antes("A", d + dt.timedelta(days=21)), 2021, "SP1", d + dt.timedelta(days=21))
        self.assertEqual((r["n"], r["pts"], r["racha"], r["descanso"]), (3, 7, 0, 7))
        r = pf.resumen_equipo(h.antes("A", d + dt.timedelta(days=14)), 2021, "SP1", d + dt.timedelta(days=14))
        self.assertEqual(r["racha"], 2)
        self.assertEqual(pf.es_derbi("SEVILLA", "BETIS"), 1)
        self.assertEqual(pf.es_derbi("SEVILLA", "OSASUNA"), 0)

    def test_nombres(self):
        self.assertEqual(ligas.nombre_fd("Ath Bilbao"), ligas.nombre_q("ATH.CLUB"))
        self.assertEqual(ligas.nombre_fd("Sp Gijon"), ligas.nombre_q("SPORTING"))
        self.assertEqual(ligas.nombre_fd("Alaves"), ligas.nombre_q("ALAVÉS"))


class TestModelos(unittest.TestCase):
    def test_ajuste_a_recupera(self):
        rng = np.random.default_rng(1)
        X = rng.normal(0, 1, (6000, 2))
        P = pm.prob_a(0.4, 0.6, [0.8, -0.3], X)
        y = np.array([rng.choice(3, p=p) for p in P])
        r = pm.ajustar_a(X, y)
        self.assertAlmostEqual(r["casa"], 0.4, delta=0.06)
        self.assertAlmostEqual(r["h"], 0.6, delta=0.06)
        self.assertAlmostEqual(r["w"][0], 0.8, delta=0.08)

    def test_ajuste_b_recupera(self):
        rng = np.random.default_rng(2)
        p = rng.dirichlet((4, 3, 3), 8000)
        lp = np.log(p)
        X = rng.normal(0, 1, (8000, 1))
        par = {"T": 1.2, "c": 0.1, "d": -0.1, "w": [0.3], "g": []}
        Q = pm.prob_b(par, lp, X, np.ones(8000))
        y = np.array([rng.choice(3, p=q) for q in Q])
        r = pm.ajustar_b(lp, X, np.ones(8000), y)
        self.assertAlmostEqual(r["T"], 1.2, delta=0.1)
        self.assertAlmostEqual(r["w"][0], 0.3, delta=0.05)

    def test_formas(self):
        P = np.tile([0.7, 0.2, 0.1], (14, 1))
        P[:6] = [[0.40 + 0.01 * i, 0.32, 0.28 - 0.01 * i] for i in range(6)]
        for forma, cols in (("6D", 64), ("3T1D", 54), ("2T2D", 36), ("1T4D", 48)):
            base = pc.base_boleto(P, forma)
            self.assertEqual(int(np.prod([len(b) for b in base])), cols)
            self.assertEqual(max(len(b) for b in base[6:]), 1)
            self.assertEqual(base[-1], [0])
        self.assertLessEqual(int(np.prod([len(b) for b in pc.base_boleto(P, "auto45")])), 64)
        self.assertEqual(len(pc.base_boleto(P, "3T1D")[0]), 3)         # triple en el mas dudoso


if __name__ == "__main__":
    unittest.main()
