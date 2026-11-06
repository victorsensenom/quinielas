"""Ligas completas (1a y 2a) de football-data.co.uk, con cache en data/ligas/.

Fuente publica, sin login:  https://www.football-data.co.uk/mmz4281/{yyzz}/{SP1|SP2}.csv
Cada CSV es una temporada completa (solo liga regular: sin Copa ni play-off).

Uso:
    python ligas.py            # descarga lo que falte y refresca la temporada en curso
    python ligas.py --todo     # vuelve a descargar todo

Modulo:  partidos_liga() -> lista de dict {fecha, div, temporada, local, visitante, gl, gv}
con los nombres ya convertidos al nombre canonico (el de la quiniela, ver ``nombre_fd``).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import sys
import time
import unicodedata
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "data", "ligas")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
URL = "https://football-data.co.uk/mmz4281/{s}/{d}.csv"
PRIMERA_T = 2011          # primera temporada descargada (10/11), para el cara a cara
ULTIMA_T = 2027
DIVS = ("SP1", "SP2")


def s_code(t: int) -> str:
    """2027 -> '2627'."""
    return f"{(t - 1) % 100:02d}{t % 100:02d}"


def ruta(d: str, t: int) -> str:
    return os.path.join(DIR, f"{d}_{s_code(t)}.csv")


def _get(url: str, retries: int = 3):
    err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:      # noqa: BLE001
            err = e
            time.sleep(2 * (i + 1))
    print("  FALLO", url, err, file=sys.stderr)
    return None


def descargar(todo: bool = False, temporada_actual: int = ULTIMA_T, max_horas: float = 6.0) -> list[str]:
    """Baja lo que falte. La temporada en curso se refresca si tiene mas de ``max_horas``."""
    os.makedirs(DIR, exist_ok=True)
    log = []
    for t in range(PRIMERA_T, ULTIMA_T + 1):
        for d in DIVS:
            p = ruta(d, t)
            viejo = os.path.exists(p) and (time.time() - os.path.getmtime(p)) > max_horas * 3600
            if os.path.exists(p) and not todo and not (t >= temporada_actual and viejo):
                continue
            data = _get(URL.format(s=s_code(t), d=d))
            if data and len(data) > 500:
                with open(p, "wb") as fh:
                    fh.write(data)
                log.append(f"{d} {s_code(t)}: {len(data)} bytes")
                time.sleep(0.3)
            else:
                log.append(f"{d} {s_code(t)}: SIN DATOS")
    return log


# --------------------------------------------------------------------------- nombres
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


# football-data -> nombre de la quiniela (mayusculas sin acentos, ver ``norm``).
FD_A_Q = {
    "ALAVES": "ALAVES", "ALBACETE": "ALBACETE", "ALCORCON": "ALCORCON", "ALMERIA": "ALMERIA",
    "AMOREBIETA": "AMOREBIETA", "ATH BILBAO": "ATH.CLUB", "ATH MADRID": "AT.MADRID",
    "BARCELONA": "BARCELONA", "BARCELONA B": "BARCELONA B", "BETIS": "BETIS", "BURGOS": "BURGOS",
    "CADIZ": "CADIZ", "CARTAGENA": "CARTAGENA", "CASTELLON": "CASTELLON", "CASTILLA": "R.MADRID CAST.",
    "CELTA": "CELTA", "CEUTA": "CEUTA", "CORDOBA": "CORDOBA", 
    "DEPORTIVO LA CORUNA": "DEPORTIVO", "LA CORUNA": "DEPORTIVO", "EIBAR": "EIBAR", "EIBAR ": "EIBAR",
    "ELCHE": "ELCHE", "ELDENSE": "ELDENSE", "ESPANOL": "ESPANYOL", "EXTREMADURA UD": "EXTREMADURA",
    "FUENLABRADA": "FUENLABRADA", "GETAFE": "GETAFE", "GIMNASTIC": "GIMNASTIC", "GIRONA": "GIRONA",
    "GRANADA": "GRANADA", "HERCULES": "HERCULES", "HUESCA": "HUESCA", "IBIZA": "IBIZA", "LAS PALMAS": "LAS PALMAS",
    "LEGANES": "LEGANES", "LEVANTE": "LEVANTE", "LLAGOSTERA": "LLAGOSTERA",
    "LORCA": "LORCA", "LUGO": "LUGO", "MALAGA": "MALAGA", "MALLORCA": "MALLORCA", "MIRANDES": "MIRANDES",
    "MURCIA": "MURCIA", "NUMANCIA": "NUMANCIA", "OSASUNA": "OSASUNA", "OVIEDO": "R.OVIEDO",
    "PONFERRADINA": "PONFERRADINA", "RAYO VALLECANO": "RAYO",
    "VALLECANO": "RAYO", "REAL MADRID": "R.MADRID", "REAL MADRID B": "R.MADRID CAST.", "RACING": "RACING S.", "SANTANDER": "RACING S.",
    "RACING FERROL": "RACING FERROL", "FERROL": "RACING FERROL", "REUS DEPORTIU": "REUS", "REUS": "REUS",
    "SABADELL": "SABADELL", "SD HUESCA": "HUESCA", "SEVILLA": "SEVILLA", "SEVILLA B": "SEVILLA AT.",
    "SOCIEDAD": "R.SOCIEDAD", "SOCIEDAD B": "R.SOCIEDAD B", "SPORTING GIJON": "SPORTING", "SP GIJON": "SPORTING",
    "TENERIFE": "TENERIFE", "UCAM MURCIA": "UCAM MURCIA", "VALENCIA": "VALENCIA", "VALLADOLID": "VALLADOLID",
    "VILLARREAL": "VILLARREAL", "VILLARREAL B": "VILLARREAL B", "ZARAGOZA": "ZARAGOZA",
    "HOSPITALET": "HOSPITALET", "XEREZ": "XEREZ", "GUADALAJARA": "GUADALAJARA", "ALCOYANO": "ALCOYANO",
    "ALMERIA ": "ALMERIA", "ATH BILBAO B": "ATH.CLUB B", "CELTA B": "CELTA FORTUNA", "ANDORRA": "ANDORRA FC", "RECREATIVO": "REC.HUELVA", "RAYO MAJADAHONDA": "RAYO MJ", "CULTURAL LEONESA": "C. LEONESA", "LEONESA": "C. LEONESA", "GIMNASTIC ": "GIMNASTIC",
}

# nombre de la quiniela (ya normalizado) -> canonico, cuando la web usa variantes
Q_ALIAS = {
    "ATH. CLUB": "ATH.CLUB", "ATHLETIC": "ATH.CLUB", "ATLETICO": "AT.MADRID", "ATL.MADRID": "AT.MADRID",
    "R. MADRID": "R.MADRID", "REAL MADRID": "R.MADRID", "REAL MADRID B": "R.MADRID CAST.", "RACING": "RACING S.", "R.SANTANDER": "RACING S.",
    "RACING SANTANDER": "RACING S.", "R.RACING": "RACING S.", "R. SOCIEDAD": "R.SOCIEDAD", "OVIEDO": "R.OVIEDO",
    "SPORTING GIJON": "SPORTING", "SP.GIJON": "SPORTING", "S.GIJON": "SPORTING", "R.SPORTING": "SPORTING",
    "RAYO VALLECANO": "RAYO", "R.VALLECANO": "RAYO", "R.BETIS": "BETIS", "NASTIC": "GIMNASTIC",
    "RACING FERROL": "RACING FERROL", "R.FERROL": "RACING FERROL", "RAC.FERROL": "RACING FERROL",
    "R.ZARAGOZA": "ZARAGOZA", "R.VALLADOLID": "VALLADOLID", "RCD MALLORCA": "MALLORCA", "D.ALAVES": "ALAVES",
    "R.MURCIA": "MURCIA", "D.CORUNA": "DEPORTIVO", "DEPOR": "DEPORTIVO", "R.CASTILLA": "R.MADRID CAST.",
    "CASTILLA": "R.MADRID CAST.", "R.MADRID C.": "R.MADRID CAST.", "R.M.CASTILLA": "R.MADRID CAST.",
    "CULT.LEONESA": "CULTURAL", "C.LEONESA": "CULTURAL", "CULTURAL LEONESA": "CULTURAL", "EXTREMADURA UD": "EXTREMADURA",
    "AD ALCORCON": "ALCORCON", "RAYO MAJAD.": "RAYO MAJADAHONDA", "R.MAJADAHONDA": "RAYO MAJADAHONDA",
    "SEVILLA ATCO.": "SEVILLA AT.", "SEVILLA ATCO": "SEVILLA AT.", "SEVILLA ATL.": "SEVILLA AT.",
    "BARCELONA AT.": "BARCELONA B", "BARCELONA ATL.": "BARCELONA B", "SD AMOREBIETA": "AMOREBIETA",
    "FC ANDORRA": "ANDORRA", "UD IBIZA": "IBIZA", "U.D.IBIZA": "IBIZA", "REUS DEP.": "REUS", "MIRANDES ": "MIRANDES",
    "VILLARREAL B": "VILLARREAL B", "R.SOCIEDAD B": "R.SOCIEDAD B", "CD CASTELLON": "CASTELLON",
    "LAS PALMAS": "LAS PALMAS", "U.LAS PALMAS": "LAS PALMAS", "L.PALMAS": "LAS PALMAS", "UD LAS PALMAS": "LAS PALMAS",
    "CD ELDENSE": "ELDENSE", "CD LUGO": "LUGO", "CE SABADELL": "SABADELL", "MALAGA CF": "MALAGA",
}


def nombre_fd(s: str) -> str:
    n = norm(s)
    return FD_A_Q.get(n, n)


def nombre_q(s: str) -> str:
    n = norm(s)
    return Q_ALIAS.get(n, n)


# --------------------------------------------------------------------------- lectura
def _fecha(s: str):
    s = s.strip()
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def leer_csv(path: str):
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("latin-1")
    return list(csv.DictReader(io.StringIO(txt)))


def partidos_liga(temporadas=None) -> list[dict]:
    out = []
    for t in range(PRIMERA_T, ULTIMA_T + 1):
        if temporadas is not None and t not in temporadas:
            continue
        for d in DIVS:
            p = ruta(d, t)
            if not os.path.exists(p):
                continue
            for r in leer_csv(p):
                f = _fecha(r.get("Date") or "")
                if f is None or not (r.get("HomeTeam") or "").strip():
                    continue
                try:
                    gl, gv = int(float(r["FTHG"])), int(float(r["FTAG"]))
                except (KeyError, TypeError, ValueError):
                    continue          # partido aun sin resultado
                out.append({"fecha": f, "div": d, "temporada": t, "local": nombre_fd(r["HomeTeam"]),
                            "visitante": nombre_fd(r["AwayTeam"]), "gl": gl, "gv": gv})
    out.sort(key=lambda m: (m["fecha"], m["div"], m["local"]))
    return out


if __name__ == "__main__":
    for line in descargar(todo="--todo" in sys.argv):
        print(line)
    ms = partidos_liga()
    print(len(ms), "partidos;", "ultimo:", ms[-1]["fecha"] if ms else None)
