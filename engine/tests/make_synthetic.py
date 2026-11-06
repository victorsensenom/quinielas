"""Genera un dataset sintetico (deterministico) en engine/tests/data/ con el esquema real.

3 temporadas x 6 jornadas. Casos especiales:
  * 2018-2019: precio_apuesta vacio (prueba el precio por defecto 0,50).
  * 2019-2020 J3: nadie acerto 15 (acert15=0, premio15=0) -> estimacion.
  * 2019-2020 J5: sin datos de premios.
  * 2020-2021 J2: sin % (lae/prob/quin vacios).
  * 2020-2021 J6: un partido sin resultado (jornada incompleta).
"""
import csv
import os

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SEASONS = ["2018-2019", "2019-2020", "2020-2021"]
TEAMS = [f"Equipo{i:02d}" for i in range(40)]
GOALS = "012M"


def goals_to_sign(gl, gv):
    return "1" if gl > gv else ("X" if gl == gv else "2")


def main():
    rng = np.random.default_rng(2024)
    os.makedirs(OUT, exist_ok=True)
    prows, jrows = [], []
    for t in SEASONS:
        for j in range(1, 7):
            fmt = lambda a: [f"{x:.1f}" for x in a]
            no_pct = (t, j) == ("2020-2021", 2)
            for num in range(1, 16):
                p = rng.dirichlet([3, 2, 2])
                lae = np.clip(p + rng.normal(0, 0.05, 3), 0.01, None)
                lae = lae / lae.sum() * 100
                quin = np.clip(p + rng.normal(0, 0.03, 3), 0.01, None)
                quin = quin / quin.sum() * 100
                s = rng.choice(3, p=p)
                # goles coherentes con el signo
                while True:
                    gl, gv = rng.integers(0, 5, 2)
                    if "1X2"[s] == goals_to_sign(gl, gv):
                        break
                res = f"{gl}-{gv}"
                if num <= 14:
                    signo = "1X2"[s]
                else:
                    signo = GOALS[min(gl, 3)] + GOALS[min(gv, 3)]
                if (t, j) == ("2020-2021", 6) and num == 7:
                    res, signo = "", ""
                a, b = rng.choice(len(TEAMS), 2, replace=False)
                prows.append({
                    "temporada": t, "jornada": j, "num": num, "local": TEAMS[a], "visitante": TEAMS[b],
                    "division": "1" if num <= 10 else "2", "resultado": res, "signo": signo,
                    **{k: ("" if no_pct else v) for k, v in zip(["lae1", "laeX", "lae2"], fmt(lae))},
                    **{k: ("" if no_pct else v) for k, v in zip(["prob1", "probX", "prob2"], fmt(p * 100))},
                    **{k: ("" if no_pct else v) for k, v in zip(["quin1", "quinX", "quin2"], fmt(quin))},
                })
            precio = "" if t == "2018-2019" else "0.75"
            rec = float(rng.integers(3_000_000, 8_000_000))
            acert = {15: int(rng.integers(0, 3)), 14: int(rng.integers(1, 6)), 13: int(rng.integers(20, 200)),
                     12: int(rng.integers(500, 3000)), 11: int(rng.integers(5000, 30000)),
                     10: int(rng.integers(40000, 200000))}
            if (t, j) == ("2019-2020", 3):
                acert[15] = 0
            pct = {15: 0.075, 14: 0.16, 13: 0.075, 12: 0.075, 11: 0.075, 10: 0.09}
            row = {"temporada": t, "jornada": j, "fecha": f"{t[:4]}-09-{j * 7:02d}", "recaudacion": f"{rec:.2f}",
                   "bote": "0"}
            for c in (15, 14, 13, 12, 11, 10):
                prize = rec * pct[c] / acert[c] if acert[c] else 0.0
                row[f"acert{c}"] = acert[c]
                row[f"premio{c}"] = f"{prize:.2f}"
            if (t, j) == ("2019-2020", 5):
                for c in (15, 14, 13, 12, 11, 10):
                    row[f"acert{c}"] = ""
                    row[f"premio{c}"] = ""
            row["precio_apuesta"] = precio
            jrows.append(row)

    pf = ["temporada", "jornada", "num", "local", "visitante", "division", "resultado", "signo",
          "lae1", "laeX", "lae2", "prob1", "probX", "prob2", "quin1", "quinX", "quin2"]
    jf = ["temporada", "jornada", "fecha", "recaudacion", "bote"] + \
         [f"{k}{c}" for c in (15, 14, 13, 12, 11, 10) for k in ("acert", "premio")] + ["precio_apuesta"]
    with open(os.path.join(OUT, "partidos.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=pf)
        w.writeheader()
        w.writerows(prows)
    with open(os.path.join(OUT, "jornadas.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=jf)
        w.writeheader()
        w.writerows(jrows)
    print("escrito", OUT, len(prows), "partidos", len(jrows), "jornadas")


if __name__ == "__main__":
    main()
