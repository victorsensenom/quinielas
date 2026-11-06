"""Clasificación actual de Primera, Segunda y Liga F (datos públicos de laliga.com).

obtener() devuelve un dict {nombre de la quiniela normalizado: (posicion, puntos)} construido bajo
demanda con posicion_de(tablas, 'R.MADRID (F)'). Si algo falla devuelve tablas vacías y el programa
sigue funcionando sin mostrar la clasificación.
"""
import json
import re
import unicodedata
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
PAGINAS = {"primera": "laliga-easports/clasificacion", "segunda": "laliga-hypermotion/clasificacion",
           "femenina": "futbol-femenino/clasificacion"}

# nombre en la quiniela (sin acentos ni "(F)") -> texto que aparece en el nombre de LaLiga
ALIAS = {
    "R.MADRID": "REAL MADRID", "AT.MADRID": "ATLETICO", "ATH.CLUB": "ATHLETIC", "R.SOCIEDAD": "REAL SOCIEDAD",
    "R.SOCIEDAD B": "SOCIEDAD B", "RACING S.": "RACING", "BARCELONA": "FC BARCELONA", "DEPORTIVO": "RC DEPORTIVO",
    "SPORTING": "SPORTING", "R.OVIEDO": "OVIEDO", "CELTA B": "CELTA FORTUNA",
}
ALIAS_F = {"DEPORTIVO": "DEPORTIVO ABANCA", "VALENCIA": "VCF", "BARCELONA": "BARCELONA", "LOGRONO": "LOGRONO",
           "TENERIFE": "TENERIFE", "BADALONA W.": "BADALONA"}


def _norm(s):
    s = unicodedata.normalize("NFD", str(s).upper())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


def _pagina(ruta):
    req = urllib.request.Request("https://www.laliga.com/" + ruta, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", errors="replace")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    props = json.loads(m.group(1))["props"]["pageProps"]
    out = []
    for f in props.get("standings") or []:
        eq = f.get("team") or {}
        out.append((_norm(f"{eq.get('nickname', '')} {eq.get('name', '')}"), int(f["position"]), int(f["points"])))
    return out


def obtener():
    tablas = {}
    for liga, ruta in PAGINAS.items():
        try:
            tablas[liga] = _pagina(ruta)
        except Exception:  # noqa: BLE001  sin clasificación el programa sigue funcionando
            tablas[liga] = []
    return tablas


def posicion_de(tablas, nombre):
    """(posicion, puntos) de un equipo tal como se escribe en la quiniela, o None si no está."""
    n = _norm(nombre)
    femenino = n.endswith("(F)")
    n = n.replace("(F)", "").strip()
    if femenino:
        clave, ligas = ALIAS_F.get(n) or ALIAS.get(n, n), ("femenina",)
        if n == "BARCELONA":
            clave = "BARCELONA"
    else:
        clave, ligas = ALIAS.get(n, n), ("primera", "segunda")
    for liga in ligas:
        for eq, pos, pts in tablas.get(liga, []):
            if clave in eq and (femenino or "SOCIEDAD B" not in eq or "SOCIEDAD B" in clave) \
                    and (femenino or "FORTUNA" not in eq or "FORTUNA" in clave):
                return pos, pts
    return None


def texto(tablas, nombre):
    r = posicion_de(tablas, nombre)
    return f"{nombre} ({r[0]}º, {r[1]} p)" if r else nombre
