"""Generador semanal: columnas de la estrategia valor_mix para la proxima jornada abierta.

Uso (desde quiniela\\):
    python generar_jornada.py                    # primera jornada ABIERTA de la temporada en curso
    python generar_jornada.py --jornada 15       # una jornada concreta
    python generar_jornada.py --presupuesto 48 --temporada 2027 --sin-actualizar

Descarga de api.eduardolosilla.es los equipos, % LAE (jugados) y % probables de la jornada,
elige las columnas con valor_mix (b=0.5, radius=1: la configuracion elegida en el backtest)
y escribe en jornadas_generadas\\:
    quiniela_<temporada>_j<jornada>.txt   una columna por linea (14 signos, sin pleno)
    quiniela_<temporada>_j<jornada>.md    resumen: partidos, reparto de signos y pleno sugerido
Antes, salvo --sin-actualizar, pone al dia el historico (fetch.py + build.py).
"""
import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from fetch import ENDPOINTS, http_get  # noqa: E402
from build import triple  # noqa: E402
from engine.data import JornadaInfo, MatchInfo, SIGN_CHARS, GOAL_CHARS  # noqa: E402
from strategies.valor_mix import Strategy  # noqa: E402

PRECIO = 0.75
OUT = os.path.join(BASE, "jornadas_generadas")


def temporada_actual(hoy=None):
    hoy = hoy or dt.date.today()
    return hoy.year + 1 if hoy.month >= 8 else hoy.year


def get_json(name, t, j):
    status, data = http_get(ENDPOINTS[name][0].format(t=t, j=j))
    if status != 200 or not data.strip():
        return None
    return json.loads(data.decode("utf-8"))


def buscar_abierta(t):
    for j in range(1, 101):
        esc = get_json("escrutinios", t, j)
        if esc is None:
            return None, None
        if esc.get("estado") == "ABIERTA":
            return j, esc
    return None, None


def pct_pleno(src, side):
    v = []
    for g in "012M":
        x = src.get(f"porc_15{side}_{g}_dec", src.get(f"porc_15{side}_{g}"))
        v.append(float(x) if x is not None else math.nan)
    return np.array(v)


def construir_info(t, j, esc, prob):
    by = {k: {int(x["numero"]): x for x in (prob.get("partidos", {}).get(k) or []) if x.get("numero") is not None}
          for k in ("lae", "real", "quinielista")}
    partidos = {int(p["num"]): p for p in esc.get("partidos", [])}
    mats, lae, pr, qu = [], [], [], []
    for n in range(1, 15):
        p = partidos[n]
        tl = triple(by["lae"].get(n))
        if tl[0] is None:
            tl = (p.get("porcentaje1"), p.get("porcentajeX"), p.get("porcentaje2"))
        tp, tq = triple(by["real"].get(n)), triple(by["quinielista"].get(n))
        tl, tp, tq = (tuple(math.nan if x is None else float(x) for x in tr) for tr in (tl, tp, tq))
        mats.append(MatchInfo(n, p["local"], p["visitante"], str(p.get("division", "")), tl, tp, tq))
        lae.append(tl); pr.append(tp); qu.append(tq)
    p15 = partidos.get(15)
    pleno = MatchInfo(15, p15["local"], p15["visitante"], str(p15.get("division", "")),
                      (math.nan,) * 3, (math.nan,) * 3, (math.nan,) * 3) if p15 else None
    ro = lambda a: np.array(a, float)
    info = JornadaInfo(str(t), j, "", PRECIO, tuple(mats), pleno, ro(lae), ro(pr), ro(qu))
    for arr in (info.lae, info.prob, info.quin):
        arr.flags.writeable = False
    return info, by["real"].get(15) or {}, by["lae"].get(15) or {}


def elegir_pleno(real15, lae15):
    if not real15:
        return (1, 1), None, None
    L, V = pct_pleno(real15, "L"), pct_pleno(real15, "V")
    M = np.outer(L, V) / 1e4
    gl, gv = np.unravel_index(int(np.nanargmax(M)), M.shape)
    jug = None
    if lae15:
        jug = pct_pleno(lae15, "L")[gl] * pct_pleno(lae15, "V")[gv] / 1e4
    return (int(gl), int(gv)), float(M[gl, gv]), jug


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--temporada", type=int, default=temporada_actual())
    ap.add_argument("--jornada", type=int)
    ap.add_argument("--presupuesto", type=float, default=48.0)
    ap.add_argument("--sin-actualizar", action="store_true", help="no actualizar el historico")
    a = ap.parse_args()
    t = a.temporada

    if not a.sin_actualizar:
        print("Actualizando historico...")
        subprocess.run([sys.executable, "fetch.py", str(t), str(t)], cwd=BASE, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, "build.py"], cwd=BASE, check=True, stdout=subprocess.DEVNULL)

    if a.jornada:
        j, esc = a.jornada, get_json("escrutinios", t, a.jornada)
    else:
        j, esc = buscar_abierta(t)
    if not esc:
        sys.exit(f"No encuentro jornada abierta en la temporada {t}.")
    prob = get_json("probabilidades", t, j) or {}

    info, real15, lae15 = construir_info(t, j, esc, prob)
    if np.isnan(info.prob).any():
        print("AVISO: faltan % probables en algun partido; se usan los % LAE como respaldo.")
    cols = Strategy(a=1.0, b=0.5, radius=1).generate(info, [], a.presupuesto)
    S = np.asarray(cols.signs)
    pleno, p_pleno, jug_pleno = elegir_pleno(real15, lae15)
    pleno_txt = f"{GOAL_CHARS[pleno[0]]}-{GOAL_CHARS[pleno[1]]}"

    os.makedirs(OUT, exist_ok=True)
    stem = os.path.join(OUT, f"quiniela_{t}_j{j:02d}")
    with open(stem + ".txt", "w", encoding="utf-8") as f:
        for row in S:
            f.write("".join(SIGN_CHARS[s] for s in row) + "\n")

    temp = f"{t - 1 - 2000:02d}/{t - 2000:02d}"
    lines = [f"# Quiniela temporada {temp}, jornada {j}", "",
             f"Estrategia valor_mix (b=0,5). {len(S)} columnas x {PRECIO:.2f} EUR = **{len(S) * PRECIO:.2f} EUR**.", "",
             "| # | Partido | % probables 1/X/2 | % jugados 1/X/2 | Columnas con 1 / X / 2 |",
             "|---|---|---|---|---|"]
    for i, m in enumerate(info.partidos):
        c = [int((S[:, i] == k).sum()) for k in range(3)]
        fp = "/".join(f"{x:.0f}" for x in m.prob) if not any(map(math.isnan, m.prob)) else "-"
        fl = "/".join(f"{x:.0f}" for x in m.lae)
        lines.append(f"| {m.num} | {m.local} - {m.visitante} | {fp} | {fl} | {c[0]} / {c[1]} / {c[2]} |")
    if info.pleno:
        extra = f" (probabilidad {p_pleno * 100:.1f} %" + (f", jugado {jug_pleno * 100:.1f} %)" if jug_pleno else ")") if p_pleno else ""
        lines += ["", f"**Pleno al 15** ({info.pleno.local} - {info.pleno.visitante}): sugerido **{pleno_txt}**{extra}. "
                  "No va en el archivo: márcalo en la web."]
    cnt = [(S == k).sum(1) for k in range(3)]
    lines += ["", f"Cada columna tiene {cnt[0].min()}-{cnt[0].max()} unos, {cnt[1].min()}-{cnt[1].max()} equis "
              f"y {cnt[2].min()}-{cnt[2].max()} doses.", "",
              "Backtest 2017-2026: esta estrategia pierde bastante menos que jugar favoritos, pero sigue "
              "siendo negativa de media. No hay garantía de premio."]
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nArchivos: {stem}.txt / .md")


if __name__ == "__main__":
    main()
