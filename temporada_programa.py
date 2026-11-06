"""Juega una temporada entera con el mismo codigo que el programa (cargar -> generar -> escrutar).

Uso: python temporada_programa.py 2026 48     (temporada 25/26, 48 EUR por jornada)
"""
import csv
import sys

import numpy as np

import generar_jornada as gj
from engine.data import SIGN_CHARS, GOAL_CHARS
from strategies.valor_mix import Strategy
import quiniela_app as qa

t = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
gasto = float(sys.argv[2]) if len(sys.argv) > 2 else 48.0
rows, acc = [], 0.0
for j in range(1, 101):
    esc = gj.get_json("escrutinios", t, j)
    if not esc or not esc.get("partidos"):
        break
    if esc.get("estado") != "ESCRUTADA":
        continue
    prob = gj.get_json("probabilidades", t, j) or {}
    info, real15, lae15 = gj.construir_info(t, j, esc, prob)
    S = np.asarray(Strategy(a=1.0, b=0.5, radius=1).generate(info, [], gasto).signs)
    pleno = gj.elegir_pleno(real15, lae15)[0]
    cols = ["".join(SIGN_CHARS[s] for s in r) for r in S]
    pl = GOAL_CHARS[pleno[0]] + GOAL_CHARS[pleno[1]]
    rep = qa.escrutinio(esc, cols, [pl] * len(cols), pl, f"j{j}")
    cobrado = float(rep.split("PREMIO TOTAL:")[1].split("€")[0].replace(",", ""))
    signos = [(p.get("signo") or "") for p in sorted(esc["partidos"], key=lambda p: int(p["num"]))[:14]]
    aciertos = max(sum(c[i] == signos[i] for i in range(14)) for c in cols)
    goles = next((p.get("signo_goles") or "") for p in esc["partidos"] if int(p["num"]) == 15)
    pleno_ok = aciertos == 14 and goles == pl
    acc += cobrado - len(cols) * gj.PRECIO
    rows.append(dict(jornada=j, fecha=gj.dt.datetime.fromtimestamp(int(esc.get("fecha_jornada") or 0)).strftime("%d/%m"),
                     columnas=len(cols), aciertos=aciertos, pleno=pl, pleno_acertado=pleno_ok,
                     cobrado=round(cobrado, 2), acumulado=round(acc, 2)))
    print(rows[-1], flush=True)

with open(f"jornadas_generadas/temporada_{t}_{int(gasto)}eur.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, list(rows[0]))
    w.writeheader()
    w.writerows(rows)
