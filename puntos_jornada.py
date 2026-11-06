"""Tabla de puntos y signo propuesto de cada partido de una jornada.

Uso (desde quiniela\\):
    python puntos_jornada.py                         # proxima jornada ABIERTA de la temporada en curso
    python puntos_jornada.py --jornada 20            # una jornada concreta
    python puntos_jornada.py --temporada 2027 --jornada 17 --forma 3T1D
    python puntos_jornada.py --sin-actualizar        # no vuelve a bajar las ligas

Muestra, para cada partido: que suma cada variable (modelo A, puntos propios), la probabilidad de
los dos modelos y de las cuotas, y que poner segun la forma de boleto elegida. No juega nada: es
una propuesta para que la revises. Los pesos estan en data/ligas/puntos_pesos.json y salen SOLO de
2017-2022 (ver results/INFORME_puntos.md).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

import rutas  # noqa: E402

BASE = rutas.CARPETA
sys.path.insert(0, BASE)

import generar_jornada as gj  # noqa: E402  (solo se reutilizan sus funciones de descarga)
import ligas  # noqa: E402
import puntos_features as pf  # noqa: E402
from engine.data import SIGN_CHARS  # noqa: E402
from engine.strategy import prob_matrix  # noqa: E402
from strategies import puntos_comun as pc  # noqa: E402

ETIQ = {"dg": "Goles", "forma5": "Forma", "h2h": "CaraCara", "ppg": "PPP", "derbi": "Derbi"}
TOPE_NOMBRE = 24


def division_liga(h, t, a, b):
    """'SP1'/'SP2' si los dos equipos juegan esta temporada esa misma liga, si no None."""
    def div(x):
        d = {p[2] for p in h.eq.get(x, []) if p[1] == t}
        return d.pop() if len(d) == 1 else None
    da, db = div(a), div(b)
    return da if da and da == db else None


def filas_para(info, esc, partidos):
    """Filas tipo variables_quiniela para una jornada (jugada o por jugar), solo con datos < corte."""
    t = int(info.temporada)
    h, idx = pf.Historial(partidos), pf.indice_liga(partidos)
    base, corte = pf.fecha_base(esc), pf.corte_jornada(esc)
    jugados = {(m["local"], m["visitante"]) for m in partidos if m["temporada"] == t and m["fecha"] < corte}
    filas = []
    for m in info.partidos:
        fila = {"cubierto": "0"}
        a, b = ligas.nombre_q(m.local), ligas.nombre_q(m.visitante)
        liga = pf.buscar_liga(idx, t, m.local, m.visitante, base)
        div = liga["div"] if liga else None
        if div is None and (a, b) not in jugados:          # jornada por jugar: aun no esta en la liga
            div = division_liga(h, t, a, b)
            if div is None and str(m.division) in ("1", "2") and h.conocido(a) and h.conocido(b):
                # primera jornada de la temporada: se usa la division que indica la quiniela
                div = "SP1" if str(m.division) == "1" else "SP2"
        if div:
            c = min(corte, liga["fecha"]) if liga else corte
            fila.update({k: str(v) for k, v in pf.variables(h, a, b, t, div, c).items()})
            fila["cubierto"] = "1"
        filas.append(fila)
    return filas, corte


def calcular(info, esc, modelo="B", forma=None):
    """Puntos y propuesta de una jornada: lo usan este script y la ventana del generador."""
    t = int(info.temporada)
    P0 = prob_matrix(info, "prob", "lae")
    partidos = ligas.partidos_liga()
    filas, corte = filas_para(info, esc, partidos)
    PA = pc.prob_modelo("A", P0, filas)
    PB = pc.prob_modelo("B", P0, filas)
    sin_pct = np.isnan(info.prob).any(1) & np.isnan(info.lae).any(1)      # aun no publicados
    PB = np.where(sin_pct[:, None], PA, PB)                               # sin % el modelo B no tiene base
    decide = {"A": PA, "B": PB, "prob": P0}[modelo]
    if forma is None:
        forma = "6D"
        conf_path = os.path.join(BASE, "data", "ligas", "puntos_config.json")
        if os.path.exists(conf_path):
            b = json.load(open(conf_path, encoding="utf-8")).get(modelo, {})
            forma = b.get("boleto", "x_6D").split("_", 1)[1]
    base = pc.base_boleto(decide, forma)
    pes = pc.pesos()["A"]
    filas_ui = []
    for i, f in enumerate(filas):
        trozos = None
        if f["cubierto"] == "1":
            trozos = [pes["casa"]] + [w * float(f[v]) for v, w in zip(pes["vars"], pes["w"])]
        filas_ui.append(dict(trozos=trozos, total=sum(trozos) if trozos else None,
                             signo="".join(SIGN_CHARS[s] for s in sorted(base[i]))))
    return dict(temporada=t, P0=P0, PA=PA, PB=PB, filas=filas, corte=corte, forma=forma, base=base, pesos=pes,
                ncol=int(np.prod([len(x) for x in base])), ultima=max(m["fecha"] for m in partidos), ui=filas_ui)


def pct(x):
    return f"{x * 100:3.0f}"


def num2(x):
    return f"{x:.2f}".replace(".", ",")


def num(x):
    return f"{x:+5.1f}".replace(".", ",")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--temporada", type=int, default=gj.temporada_actual())
    ap.add_argument("--jornada", type=int)
    ap.add_argument("--forma", default=None, help="6D, 3T1D, 2T2D, 1T4D, auto50 (por defecto, la elegida en el ajuste)")
    ap.add_argument("--modelo", default="B", choices=("A", "B", "prob"), help="modelo que decide los signos")
    ap.add_argument("--sin-actualizar", action="store_true", help="no refrescar las ligas")
    a = ap.parse_args()
    t = a.temporada

    if not a.sin_actualizar:
        ligas.descargar(max_horas=1.0)
    if a.jornada:
        j, esc = a.jornada, gj.get_json("escrutinios", t, a.jornada)
    else:
        j, esc = gj.buscar_abierta(t)
    if not esc or not esc.get("partidos"):
        sys.exit(f"No encuentro la jornada (temporada {t}).")
    prob = gj.get_json("probabilidades", t, j) or {}
    info, _, _ = gj.construir_info(t, j, esc, prob)
    faltan = np.isnan(info.prob).any(1)
    c = calcular(info, esc, a.modelo, a.forma)
    P0, PA, PB, filas, corte, forma, base, ncol, pes = (c["P0"], c["PA"], c["PB"], c["filas"], c["corte"], c["forma"],
                                                        c["base"], c["ncol"], c["pesos"])
    temp = f"{t - 2001:02d}/{t - 2000:02d}"
    print(f"\nQuiniela {temp}, jornada {j} ({esc.get('estado')}). Primer partido: {corte:%d/%m/%Y}; "
          f"datos de liga hasta el dia anterior.")
    print(f"Ligas actualizadas hasta el {c['ultima']:%d/%m/%Y}.")
    if faltan.any():
        print("AVISO: aun no estan publicados los % probables de " + ", ".join(str(i + 1) for i in np.flatnonzero(faltan))
              + ": ahi se usan los % jugados o, si tampoco hay, el modelo A. Vuelve a lanzarlo mas cerca del cierre.")
    print("\nFORMULA (modelo A, en puntos): "
          f"+{num2(pes['casa'])} por jugar en casa"
          + "".join(f", {'+' if w > 0 else '-'}{num2(abs(w))} x {ETIQ[v]}" for v, w in zip(pes["vars"], pes["w"]))
          + f". Por encima de +{num2(pes['h'])} tiende a 1, por debajo de -{num2(pes['h'])} a 2, y entre medias, partido abierto.")
    print("Goles = dif. de goles por partido (local - visitante); Forma = dif. de puntos por partido en los "
          "ultimos 5; CaraCara = lo que saca el local recibiendo a este rival.\n")
    cab = (f"{'#':>2} {'Partido':<{TOPE_NOMBRE}} {'Casa':>5} " + " ".join(f"{ETIQ[v]:>8}" for v in pes["vars"])
           + f" {'TOTAL':>6} | {'A 1  X  2':>11} | {'B 1  X  2':>11} | {'Cuotas':>11} | Signo")
    print(cab)
    print("-" * len(cab))
    for i, m in enumerate(info.partidos):
        nom = f"{m.local} - {m.visitante}"[:TOPE_NOMBRE]
        f = filas[i]
        if f["cubierto"] == "1":
            trozos = [pes["casa"]] + [w * float(f[v]) for v, w in zip(pes["vars"], pes["w"])]
            txt = f"{num(trozos[0])} " + " ".join(f"{num(x):>8}" for x in trozos[1:]) + f" {num(sum(trozos)):>6}"
        else:
            txt = f"{'sin datos de liga: usa % cuotas':<{6 + 9 * len(pes['vars']) + 6}}"
        sg = "".join(SIGN_CHARS[s] for s in sorted(base[i]))
        tipo = {1: "fijo", 2: "doble", 3: "TRIPLE"}[len(sg)]
        print(f"{m.num:>2} {nom:<{TOPE_NOMBRE}} {txt} | {' '.join(pct(x) for x in PA[i])} | "
              f"{' '.join(pct(x) for x in PB[i])} | {' '.join(pct(x) for x in P0[i])} | {sg:<3} {tipo}")
    cub = sum(f["cubierto"] == "1" for f in filas)
    print(f"\nPartidos con datos de liga: {cub} de 14 (el resto, Copa, Europa, femenino o ligas de fuera, "
          "se queda con las cuotas).")
    print(f"Decide el modelo {a.modelo} con la forma {forma}: {ncol} columnas = {ncol * info.precio_apuesta:.2f} EUR.")
    if info.pleno:
        pl = gj.elegir_pleno(*gj.construir_info(t, j, esc, prob)[1:])[0]
        print(f"Pleno al 15 ({info.pleno.local} - {info.pleno.visitante}): marcador mas probable "
              f"{'012M'[pl[0]]}-{'012M'[pl[1]]}.")
    if cub and str(esc.get("estado")) == "ABIERTA":
        print("Si alguno de los partidos con datos fuera de Copa, ignora sus puntos: en una jornada por jugar el "
              "programa no distingue Copa de Liga.")
    print("Ojo: es una propuesta para revisar. Ninguna formula ha demostrado ganar a la casa (ver INFORME_puntos.md).")


if __name__ == "__main__":
    main()
