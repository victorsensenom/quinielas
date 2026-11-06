"""Variables de cada partido para el sistema de puntos, SIN mirar el futuro.

Regla antifuga: ``variables(hist, ..., corte)`` solo mira partidos de liga con fecha < corte.
En el backtest ``corte`` es el dia del PRIMER partido de la jornada de quiniela (cuando se cierra
el boleto), no la fecha de cada partido: asi un partido del domingo no usa lo jugado el sabado de
esa misma jornada, que no se conocen al rellenar el boleto.

Todas las variables son "local menos visitante" (positivo = favorece al local):
    ppg       puntos por partido de la temporada, mezclados con la temporada pasada al principio
    dg        diferencia de goles por partido (igual mezcla)
    forma5    puntos por partido en los ultimos 5 partidos de liga
    casafuera ppg del local en sus 5 ultimos en casa - ppg del visitante en sus 5 ultimos fuera
    h2h       puntos medios del local recibiendo a este rival (ultimas 5 visitas), respecto a 1,6
    racha     racha actual: +n victorias seguidas / -n derrotas seguidas (tope 5)
    descanso  dias desde el ultimo partido de LIGA (entre 3 y 10). No ve Copa ni Europa.
    derbi     1 si es un derbi (lista simple), si no 0

    python puntos_features.py        # (re)genera data/ligas/variables_*.csv
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import glob
import json
import os
import re

import ligas

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw", "escrutinios")
DIR = os.path.join(BASE, "data", "ligas")
F_QUINIELA = os.path.join(DIR, "variables_quiniela.csv")
F_LIGA = os.path.join(DIR, "variables_liga.csv")

VARS = ("ppg", "dg", "forma5", "casafuera", "h2h", "racha", "descanso", "derbi")
K_MEZCLA = 6.0            # peso (en partidos) de la temporada pasada en ppg/dg
TOPE = {"ppg": 1.5, "dg": 1.5, "forma5": 2.0, "casafuera": 2.0, "h2h": 1.0, "racha": 5.0, "descanso": 7.0}
PPG_MEDIO = 1.37
VENTANA = (-4, 4)         # dias de margen entre la jornada y la fecha real del partido

DERBIS = [
    {"R.MADRID", "AT.MADRID", "GETAFE", "RAYO", "LEGANES", "ALCORCON", "FUENLABRADA"},
    {"SEVILLA", "BETIS"},
    {"BARCELONA", "ESPANYOL", "GIRONA"},
    {"ATH.CLUB", "R.SOCIEDAD", "EIBAR", "ALAVES"},
    {"VALENCIA", "LEVANTE", "VILLARREAL", "ELCHE", "CASTELLON"},
    {"CELTA", "DEPORTIVO", "LUGO", "RACING FERROL"},
    {"SPORTING", "R.OVIEDO"},
    {"LAS PALMAS", "TENERIFE"},
    {"ZARAGOZA", "HUESCA"},
]


def es_derbi(a: str, b: str) -> int:
    return int(any(a in g and b in g for g in DERBIS))


class Historial:
    """Partidos de liga por equipo y por pareja local/visitante, ordenados por fecha."""

    def __init__(self, partidos):
        self.eq: dict = {}
        self.fechas: dict = {}
        self.pares: dict = {}
        for m in sorted(partidos, key=lambda x: x["fecha"]):
            for t, casa, gf, gc in ((m["local"], True, m["gl"], m["gv"]), (m["visitante"], False, m["gv"], m["gl"])):
                self.eq.setdefault(t, []).append((m["fecha"], m["temporada"], m["div"], casa, gf, gc))
                self.fechas.setdefault(t, []).append(m["fecha"])
            self.pares.setdefault((m["local"], m["visitante"]), []).append((m["fecha"], m["gl"], m["gv"]))

    def antes(self, team, corte):
        """Partidos del equipo con fecha ESTRICTAMENTE anterior a ``corte``."""
        f = self.fechas.get(team)
        if not f:
            return []
        return self.eq[team][:bisect.bisect_left(f, corte)]

    def conocido(self, team) -> bool:
        return team in self.eq


def _pts(gf, gc) -> int:
    return 3 if gf > gc else (1 if gf == gc else 0)


def _base_previa(prev, div):
    """Punto de partida (ppg, dg) para mezclar: temporada pasada, o valor tipico si cambio de division."""
    mismos = [p for p in prev if p[2] == div]
    if mismos:
        n = len(mismos)
        return (sum(_pts(p[4], p[5]) for p in mismos) / n, sum(p[4] - p[5] for p in mismos) / n)
    if prev:                       # viene de la otra division
        return (1.0, -0.35) if div == "SP1" else (1.55, 0.25)
    return (1.1, -0.2)             # sin datos (asciende de 1a RFEF)


def resumen_equipo(team_hist, temporada, div, corte):
    """Numeros de un equipo a partir de su historial previo a ``corte``."""
    temp = [p for p in team_hist if p[1] == temporada]
    prev = [p for p in team_hist if p[1] == temporada - 1]
    ppg0, dg0 = _base_previa(prev, div)
    n = len(temp)
    pts = sum(_pts(p[4], p[5]) for p in temp)
    dg = sum(p[4] - p[5] for p in temp)
    ult = team_hist[-5:]
    forma = (sum(_pts(p[4], p[5]) for p in ult) + (5 - len(ult)) * 1.2) / 5
    casa = [p for p in team_hist if p[3]][-5:]
    fuera = [p for p in team_hist if not p[3]][-5:]
    ppg_casa = (sum(_pts(p[4], p[5]) for p in casa) + (5 - len(casa)) * 1.6) / 5
    ppg_fuera = (sum(_pts(p[4], p[5]) for p in fuera) + (5 - len(fuera)) * 1.0) / 5
    racha = 0
    for p in reversed(team_hist):
        r = p[4] - p[5]
        if r == 0 or (racha > 0 and r < 0) or (racha < 0 and r > 0):
            break
        racha += 1 if r > 0 else -1
        if abs(racha) >= 5:
            break
    dias = (corte - team_hist[-1][0]).days if team_hist else 99
    return {"n": n, "pts": pts, "ppg": (pts + K_MEZCLA * ppg0) / (n + K_MEZCLA),
            "dg": (dg + K_MEZCLA * dg0) / (n + K_MEZCLA), "forma5": forma, "ppg_casa": ppg_casa,
            "ppg_fuera": ppg_fuera, "racha": racha, "descanso": min(max(dias, 3), 10)}


def _tope(x, t):
    return max(-t, min(t, x))


def variables(h: Historial, local: str, visitante: str, temporada: int, div: str, corte) -> dict:
    """Variables (local - visitante) usando SOLO partidos de liga con fecha < corte."""
    a = resumen_equipo(h.antes(local, corte), temporada, div, corte)
    b = resumen_equipo(h.antes(visitante, corte), temporada, div, corte)
    prev = [m for m in h.pares.get((local, visitante), []) if m[0] < corte][-5:]
    n = len(prev)
    hh = 0.0
    if n:
        hh = (sum(_pts(m[1], m[2]) for m in prev) / n - 1.6) * n / (n + 2)
    d = {"ppg": a["ppg"] - b["ppg"], "dg": a["dg"] - b["dg"], "forma5": a["forma5"] - b["forma5"],
         "casafuera": a["ppg_casa"] - b["ppg_fuera"], "h2h": hh, "racha": a["racha"] - b["racha"],
         "descanso": a["descanso"] - b["descanso"]}
    d = {k: round(_tope(v, TOPE[k]), 4) for k, v in d.items()}
    d["derbi"] = es_derbi(local, visitante)
    return d


# --------------------------------------------------------------------------- jornadas
DIAS = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]


def fecha_base(esc) -> dt.date:
    return (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(esc["fecha_jornada"]) + 3 * 3600)).date()


def fecha_partido(base: dt.date, dia: str):
    """Fecha de un partido a partir del dia de la semana de la web, la mas cercana a ``base``."""
    d = (dia or "").upper().replace("É", "E")
    if d not in DIAS:
        return base
    c = [base + dt.timedelta(days=x) for x in range(-6, 5) if (base + dt.timedelta(days=x)).weekday() == DIAS.index(d)]
    return min(c, key=lambda f: abs((f - base).days))


def corte_jornada(esc) -> dt.date:
    """Dia del primer partido de la jornada (los 15): nada de ese dia o posterior se puede usar."""
    base = fecha_base(esc)
    return min(fecha_partido(base, p.get("dia")) for p in esc["partidos"])


def indice_liga(partidos):
    return {(m["temporada"], m["local"], m["visitante"]): m for m in partidos}


def buscar_liga(idx, t, local, visitante, base):
    """Partido de liga correspondiente a un partido de quiniela, o None (Copa, aplazado, otra liga)."""
    m = idx.get((t, ligas.nombre_q(local), ligas.nombre_q(visitante)))
    if m and VENTANA[0] <= (m["fecha"] - base).days <= VENTANA[1]:
        return m
    return None


def tabla_quiniela(partidos=None):
    partidos = partidos if partidos is not None else ligas.partidos_liga()
    h, idx = Historial(partidos), indice_liga(partidos)
    filas = []
    for f in sorted(glob.glob(os.path.join(RAW, "*.json"))):
        m0 = re.match(r"(\d+)_(\d+)\.json", os.path.basename(f))
        if not m0:
            continue
        esc = json.load(open(f, encoding="utf-8"))
        if esc.get("estado") != "ESCRUTADA" or not esc.get("partidos"):
            continue
        t, j = int(m0.group(1)), int(m0.group(2))
        base, corte = fecha_base(esc), corte_jornada(esc)
        for p in esc["partidos"]:
            n = int(p["num"])
            if n > 14:
                continue
            m = buscar_liga(idx, t, p["local"], p["visitante"], base)
            fila = {"temporada": t, "jornada": j, "num": n, "local": p["local"], "visitante": p["visitante"],
                    "division": p.get("division"), "signo": p.get("signo"), "corte": corte.isoformat(),
                    "cubierto": int(m is not None), "div": m["div"] if m else "",
                    "fecha_liga": m["fecha"].isoformat() if m else ""}
            if m:
                fila.update(variables(h, m["local"], m["visitante"], t, m["div"], min(corte, m["fecha"])))
            filas.append(fila)
    return filas


def tabla_liga(partidos=None):
    """Todos los partidos de liga con sus variables (corte = su propia fecha): para ajustar el modelo A."""
    partidos = partidos if partidos is not None else ligas.partidos_liga()
    h = Historial(partidos)
    filas = []
    for m in partidos:
        if m["temporada"] < 2017:
            continue
        s = 0 if m["gl"] > m["gv"] else (1 if m["gl"] == m["gv"] else 2)
        fila = {"temporada": m["temporada"], "fecha": m["fecha"].isoformat(), "div": m["div"],
                "local": m["local"], "visitante": m["visitante"], "s": s}
        fila.update(variables(h, m["local"], m["visitante"], m["temporada"], m["div"], m["fecha"]))
        filas.append(fila)
    return filas


def _escribir(path, filas):
    keys = []
    for f in filas:
        for k in f:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(filas)


def leer_tabla(path=F_QUINIELA):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    partidos = ligas.partidos_liga()
    q = tabla_quiniela(partidos)
    _escribir(F_QUINIELA, q)
    _escribir(F_LIGA, tabla_liga(partidos))
    n = len(q)
    c = sum(r["cubierto"] for r in q)
    print(f"{n} partidos de quiniela, {c} con datos de liga ({100 * c / n:.1f} %)")
    return q


if __name__ == "__main__":
    main()
