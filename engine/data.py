"""Carga de datos de La Quiniela.

Lee ``partidos.csv`` y ``jornadas.csv`` (UTF-8, coma, punto decimal, campos
posiblemente vacios) y construye una lista de ``Jornada`` ordenada por
(temporada, jornada).

Separacion antifuga: cada ``Jornada`` contiene un ``JornadaInfo`` con SOLO la
informacion disponible antes de los partidos (equipos, division, % LAE, % prob,
% quin, precio, fecha). Resultados, signos, premios, recaudacion y acertantes
viven en atributos de ``Jornada`` que nunca se entregan a la estrategia para la
jornada en curso. Todos los objetos son inmutables (dataclasses frozen + arrays
numpy de solo lectura).

Codificacion:
    signos 1/X/2 -> 0/1/2 ; -1 = desconocido
    goles del pleno 0/1/2/M -> 0/1/2/3
"""
from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

N_MATCHES = 14
SIGN_CHARS = "1X2"
SIGN_TO_CODE = {"1": 0, "X": 1, "2": 2}
GOAL_CHARS = "012M"
GOAL_TO_CODE = {"0": 0, "1": 1, "2": 2, "M": 3}
CATEGORIES = (15, 14, 13, 12, 11, 10)


def _ro(a: np.ndarray) -> np.ndarray:
    a = np.array(a, copy=True)
    a.flags.writeable = False
    return a


def _f(x) -> float:
    if x is None:
        return math.nan
    s = str(x).strip()
    if s == "":
        return math.nan
    s = s.replace("%", "").replace("€", "").strip()
    try:
        return float(s)
    except ValueError:
        # tolera coma decimal suelta ("0,75") si llegase asi
        try:
            return float(s.replace(".", "").replace(",", ".")) if "," in s else math.nan
        except ValueError:
            return math.nan


def _i(x) -> Optional[int]:
    v = _f(x)
    return None if math.isnan(v) else int(round(v))


def season_year(temporada: str) -> int:
    """Anio de inicio de la temporada: '2019-2020' -> 2019, '2019/20' -> 2019, '2019' -> 2019."""
    m = re.search(r"\d{4}", str(temporada))
    if m:
        return int(m.group(0))
    m = re.search(r"\d{2}", str(temporada))
    return 2000 + int(m.group(0)) if m else 0


def default_price(temporada: str) -> float:
    """Precio por columna si jornadas.csv no lo trae.

    SUPUESTO: 0,75 EUR desde la temporada 2019-20 y 0,50 EUR antes. Solo se usa
    como respaldo cuando ``precio_apuesta`` viene vacio.
    """
    return 0.75 if season_year(temporada) >= 2019 else 0.50


def parse_pleno(s: str):
    """'M1' -> ('goals', (3, 1)); '1'/'X'/'2' (formato antiguo) -> ('sign', code); otro -> (None, None)."""
    s = (s or "").strip().upper()
    if len(s) == 2 and all(c in GOAL_TO_CODE for c in s):
        return "goals", (GOAL_TO_CODE[s[0]], GOAL_TO_CODE[s[1]])
    if s.replace("-", "") and len(s.replace("-", "")) == 2 and all(c in GOAL_TO_CODE for c in s.replace("-", "")):
        t = s.replace("-", "")
        return "goals", (GOAL_TO_CODE[t[0]], GOAL_TO_CODE[t[1]])
    if s in SIGN_TO_CODE:
        return "sign", SIGN_TO_CODE[s]
    return None, None


# --------------------------------------------------------------------------- pre-partido
@dataclass(frozen=True, slots=True)
class MatchInfo:
    """Datos de un partido conocidos ANTES de jugarse. No tiene resultado ni signo."""
    num: int
    local: str
    visitante: str
    division: str
    lae: tuple   # (1, X, 2) en %, NaN si falta
    prob: tuple
    quin: tuple


@dataclass(frozen=True, slots=True)
class JornadaInfo:
    """Lo unico que ve la estrategia de la jornada en curso.

    Arrays (14, 3) de solo lectura con NaN donde no hay dato:
    ``lae``, ``prob``, ``quin`` (en %, tal como vienen en el CSV).
    ``pleno`` es el MatchInfo del partido 15 (o None).
    """
    temporada: str
    jornada: int
    fecha: str
    precio_apuesta: float
    partidos: tuple          # 14 MatchInfo
    pleno: Optional[MatchInfo]
    lae: np.ndarray
    prob: np.ndarray
    quin: np.ndarray

    @property
    def key(self):
        return (season_year(self.temporada), self.temporada, self.jornada)

    def has_pct(self) -> bool:
        """True si cada uno de los 14 partidos tiene % prob o % lae completos."""
        ok_p = ~np.isnan(self.prob).any(1)
        ok_l = ~np.isnan(self.lae).any(1)
        return bool((ok_p | ok_l).all())


# --------------------------------------------------------------------------- completa
@dataclass(frozen=True, slots=True)
class Jornada:
    """Jornada completa (para el motor y para el historico de la estrategia)."""
    info: JornadaInfo
    signos: np.ndarray            # (14,) int8, -1 desconocido
    pleno_tipo: Optional[str]     # 'goals' | 'sign' | None
    pleno_res: object             # (gl, gv) codigos 0..3, o codigo de signo, o None
    resultados: tuple             # textos 'resultado' de los 15 partidos (puede tener '')
    recaudacion: float
    bote: float
    acertantes: dict              # cat -> int|None
    premios: dict                 # cat -> float (NaN si falta)

    @property
    def temporada(self):
        return self.info.temporada

    @property
    def jornada(self):
        return self.info.jornada

    @property
    def key(self):
        return self.info.key

    def is_complete(self) -> bool:
        return bool((self.signos >= 0).all()) and self.pleno_tipo is not None

    def has_prizes(self) -> bool:
        return any(not math.isnan(self.premios.get(c, math.nan)) for c in CATEGORIES)


# --------------------------------------------------------------------------- carga
def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _triple(row, prefix):
    return tuple(_f(row.get(prefix + s)) for s in ("1", "X", "2"))


def load(data_dir: str) -> list[Jornada]:
    """Carga ``partidos.csv`` + ``jornadas.csv`` de ``data_dir``.

    Devuelve jornadas ordenadas por (anio de inicio de temporada, temporada, jornada).
    Incluye jornadas incompletas; usa ``Jornada.is_complete()`` para filtrarlas.
    """
    partidos = _read_csv(os.path.join(data_dir, "partidos.csv"))
    jpath = os.path.join(data_dir, "jornadas.csv")
    jrows = {}
    if os.path.exists(jpath):
        for r in _read_csv(jpath):
            j = _i(r.get("jornada"))
            if j is None:
                continue
            jrows[(str(r.get("temporada", "")).strip(), j)] = r

    by_j: dict = {}
    for r in partidos:
        t = str(r.get("temporada", "")).strip()
        j = _i(r.get("jornada"))
        n = _i(r.get("num"))
        if j is None or n is None or not (1 <= n <= 15):
            continue
        by_j.setdefault((t, j), {})[n] = r

    out = []
    for (t, j), rows in by_j.items():
        jr = jrows.get((t, j), {})
        out.append(_build(t, j, rows, jr))
    out.sort(key=lambda x: x.key)
    return out


def _build(t, j, rows, jr) -> Jornada:
    nan3 = (math.nan,) * 3
    matches, signos, resultados = [], [], []
    for n in range(1, N_MATCHES + 1):
        r = rows.get(n)
        if r is None:
            matches.append(MatchInfo(n, "", "", "", nan3, nan3, nan3))
            signos.append(-1)
            resultados.append("")
            continue
        matches.append(MatchInfo(n, (r.get("local") or "").strip(), (r.get("visitante") or "").strip(),
                                 (r.get("division") or "").strip(),
                                 _triple(r, "lae"), _triple(r, "prob"), _triple(r, "quin")))
        signos.append(SIGN_TO_CODE.get((r.get("signo") or "").strip().upper(), -1))
        resultados.append((r.get("resultado") or "").strip())
    r15 = rows.get(15)
    pleno_info, ptipo, pres = None, None, None
    if r15 is not None:
        pleno_info = MatchInfo(15, (r15.get("local") or "").strip(), (r15.get("visitante") or "").strip(),
                               (r15.get("division") or "").strip(),
                               _triple(r15, "lae"), _triple(r15, "prob"), _triple(r15, "quin"))
        ptipo, pres = parse_pleno(r15.get("signo"))
        resultados.append((r15.get("resultado") or "").strip())
    else:
        resultados.append("")

    precio = _f(jr.get("precio_apuesta"))
    if math.isnan(precio) or precio <= 0:
        precio = default_price(t)

    info = JornadaInfo(
        temporada=t, jornada=j, fecha=(jr.get("fecha") or "").strip(), precio_apuesta=precio,
        partidos=tuple(matches), pleno=pleno_info,
        lae=_ro(np.array([m.lae for m in matches], float)),
        prob=_ro(np.array([m.prob for m in matches], float)),
        quin=_ro(np.array([m.quin for m in matches], float)),
    )
    return Jornada(
        info=info, signos=_ro(np.array(signos, np.int8)), pleno_tipo=ptipo, pleno_res=pres,
        resultados=tuple(resultados), recaudacion=_f(jr.get("recaudacion")), bote=_f(jr.get("bote")),
        acertantes={c: _i(jr.get(f"acert{c}")) for c in CATEGORIES},
        premios={c: _f(jr.get(f"premio{c}")) for c in CATEGORIES},
    )
