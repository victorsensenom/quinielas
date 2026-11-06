"""Descarga (con cache) de los datos crudos de La Quiniela desde eduardolosilla.es.

Endpoints publicos (sin token):
  escrutinios      https://api.eduardolosilla.es/escrutinios?num_jornada=J&num_temporada=T   (JSON: partidos, resultados, LAE%, premios)
  probabilidades   https://api.eduardolosilla.es/probabilidades?num_jornada=J&num_temporada=T (JSON: % lae, real(=probables), quinielista, tecnicos)
  Fallbacks XML    https://api.eduardolosilla.es/servicios/v1/{porcentajes_lae,probabilidad_real,porcentajes_quinielista}?jornada=J&temporada=T
  Static cache     https://static.eduardolosilla.es/cache/escrutinio{T}_{J}.json (solo jornadas recientes)

Uso: python fetch.py [temporada_ini] [temporada_fin]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data", "raw")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MIN_INTERVAL = 0.25  # <= 4 peticiones/segundo
_last = [0.0]

ENDPOINTS = {
    "escrutinios": ("https://api.eduardolosilla.es/escrutinios?num_jornada={j}&num_temporada={t}", "json"),
    "probabilidades": ("https://api.eduardolosilla.es/probabilidades?num_jornada={j}&num_temporada={t}", "json"),
    "porcentajes_lae": ("https://api.eduardolosilla.es/servicios/v1/porcentajes_lae?jornada={j}&temporada={t}", "xml"),
    "probabilidad_real": ("https://api.eduardolosilla.es/servicios/v1/probabilidad_real?jornada={j}&temporada={t}", "xml"),
    "porcentajes_quinielista": ("https://api.eduardolosilla.es/servicios/v1/porcentajes_quinielista?jornada={j}&temporada={t}", "xml"),
    "static_escrutinio": ("https://static.eduardolosilla.es/cache/escrutinio{t}_{j}.json", "json"),
}


def http_get(url, retries=4):
    """Devuelve (status, bytes). 404/401/403 no se reintentan."""
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*",
                                                   "Accept-Language": "es-ES,es;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                return e.code, e.read()
            err = e
        except Exception as e:  # timeouts, conexion
            err = e
        time.sleep(2 * (attempt + 1) ** 2)
    print("  FALLO", url, err, file=sys.stderr)
    return None, b""


def cached(name, t, j, refresh_if=None):
    """Lee de data/raw/<name>/<t>_<j>.<ext> o descarga. Devuelve bytes o None (404 etc.)."""
    url_tpl, ext = ENDPOINTS[name]
    d = os.path.join(RAW, name)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{t}_{j:02d}.{ext}")
    miss = path + ".missing"
    if os.path.exists(path):
        data = open(path, "rb").read()
        if not (refresh_if and refresh_if(data)):
            return data
    elif os.path.exists(miss):
        return None
    status, data = http_get(url_tpl.format(t=t, j=j))
    if status == 200 and data.strip():
        with open(path, "wb") as f:
            f.write(data)
        if os.path.exists(miss):
            os.remove(miss)
        return data
    if status in (400, 401, 403, 404) or (status == 200 and not data.strip()):
        with open(miss, "w") as f:
            f.write(f"HTTP {status}\n")
    return None


def not_escrutada(data):
    try:
        d = json.loads(data.decode("utf-8"))
        return not d.get("escrutinio") or d.get("estado") != "ESCRUTADA"
    except Exception:
        return True


def main():
    t0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2017
    t1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2027
    for t in range(t0, t1 + 1):
        consecutive_missing = 0
        n_ok = 0
        for j in range(1, 101):
            esc = cached("escrutinios", t, j, refresh_if=not_escrutada)
            if esc is None:
                consecutive_missing += 1
                if consecutive_missing >= 3:
                    break
                continue
            if not_escrutada(esc):
                # jornada futura / anulada / no escrutada
                print(f"{t} j{j}: no escrutada")
                consecutive_missing += 1
                if consecutive_missing >= 3:
                    break
                continue
            consecutive_missing = 0
            n_ok += 1
            prob = cached("probabilidades", t, j)
            # fallbacks XML solo si falta algo en 'probabilidades'
            need = set()
            try:
                p = json.loads(prob.decode("utf-8"))["partidos"] if prob else {}
            except Exception:
                p = {}
            for key, ep in (("lae", "porcentajes_lae"), ("real", "probabilidad_real"),
                            ("quinielista", "porcentajes_quinielista")):
                if not p.get(key) or len(p.get(key)) < 14:
                    need.add(ep)
            for ep in need:
                cached(ep, t, j)
        print(f"temporada {t}: {n_ok} jornadas escrutadas descargadas")


if __name__ == "__main__":
    main()
