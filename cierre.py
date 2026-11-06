"""Hora de cierre de la quiniela para particulares.

La web publica el cierre oficial (cierreParticulares) solo de la jornada que está en venta, en
https://api.eduardolosilla.es/datosGeneralesJornada (público). Para otras jornadas se calcula como
suele ser: una hora antes del primer partido.
"""
import datetime as dt
import json
import urllib.request

URL = "https://api.eduardolosilla.es/datosGeneralesJornada"
DIAS = {"LUN": 0, "MAR": 1, "MIE": 2, "MIÉ": 2, "JUE": 3, "VIE": 4, "SAB": 5, "SÁB": 5, "DOM": 6}
NOMBRES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _oficial(t, j):
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
        if int(d.get("temporada", 0)) == int(t) and int(d.get("jornada", 0)) == int(j) and d.get("cierreParticulares"):
            return dt.datetime.fromtimestamp(int(d["cierreParticulares"]))
    except Exception:  # noqa: BLE001  sin conexión: se usa el cálculo
        pass
    return None


def primer_partido(esc):
    """Fecha y hora del primer partido según 'dia' y 'hora' de cada partido."""
    base = dt.datetime.fromtimestamp(int(esc.get("fecha_jornada") or 0)).date()
    inicio = base - dt.timedelta(days=2)          # a veces hay partido el viernes antes de la fecha
    horas = []
    for p in esc.get("partidos", []):
        dia, hora = str(p.get("dia") or "").upper(), str(p.get("hora") or "")
        if dia not in DIAS or ":" not in hora:
            continue
        d = inicio + dt.timedelta(days=(DIAS[dia] - inicio.weekday()) % 7)
        hh, mm = hora.split(":")[:2]
        horas.append(dt.datetime.combine(d, dt.time(int(hh), int(mm))))
    return min(horas) if horas else None


def hora_cierre(t, j, esc):
    """(fecha y hora de cierre, True si es la oficial de la web / False si es calculada) o (None, False)."""
    of = _oficial(t, j)
    if of:
        return of, True
    pp = primer_partido(esc)
    return (pp - dt.timedelta(hours=1), False) if pp else (None, False)


def texto(cierre, oficial):
    if not cierre:
        return ""
    s = f"Cierre: {NOMBRES[cierre.weekday()]} {cierre:%d/%m} a las {cierre:%H:%M}"
    s += " (particulares)" if oficial else " (aprox.: 1 h antes del primer partido)"
    falta = cierre - dt.datetime.now()
    if falta.total_seconds() <= 0:
        s += " · YA CERRADA"
    elif falta.total_seconds() < 6 * 3600:
        h, m = divmod(int(falta.total_seconds() // 60), 60)
        s += f" · quedan {h} h {m:02d} min"
    return s
