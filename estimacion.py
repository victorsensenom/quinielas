"""Estado de la jornada (resultados en directo) y estimacion de premios.

La estimacion reproduce el metodo de la web de eduardolosilla.es (funcion estimarPremios):
  - apuestas jugadas N = recaudacion / precio
  - para cada partido se toma el % JUGADO (LAE) del signo que va saliendo; si el partido no ha
    empezado, el % del signo mas jugado (se supone que gana el favorito del publico)
  - acertantes de 14 = N * prod(V/100); de 13 = suma de los casos con 1 fallo (V -> 100-V); 12 con
    2 fallos; 11 con 3; 10 con 4 fallos dividido entre 3,5 (correccion empirica de la web)
  - acertantes de 15 = acertantes de 14 * % jugado del marcador del pleno
  - premio = recaudacion * % del fondo de la categoria / acertantes (15: + bote), con la retencion
    del 20 % sobre lo que pase de 40.000 EUR. Premio de 11 < 1 EUR -> 0 (su fondo pasa a 12);
    premio de 10 < 1,50 EUR -> 0.
Supone que cada jugador elige cada partido por separado segun los % jugados, asi que es una
aproximacion (la propia web la presenta como estimacion).
"""
import json
import math
import urllib.request

import generar_jornada as gj

LIVE_URL = "https://static.eduardolosilla.es/marcador/json/partidos.json"
GOALS = "012M"


def _num_es(s):
    if s in (None, ""):
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    return float(str(s).replace(".", "").replace(",", "."))


def impuestos(x, umbral=40000.0):
    return x - 0.2 * (x - umbral) if x > umbral else x


def _esym(R, kmax=4):
    e = [1.0] + [0.0] * kmax
    for r in R:
        for k in range(kmax, 0, -1):
            e[k] += e[k - 1] * r
    return e


def _n10_web(N, V):
    """Acertantes de 10 tal como los cuenta la web (bucle literal de estimarPremios: el indice
    exterior no excluye a los interiores, por eso cuenta de mas y luego divide entre 3,5)."""
    V = list(V)
    c = 0.0

    def flip(i):
        V[i] = 100.0 - V[i]

    for g in range(11):
        flip(g)
        for f in range(12):
            flip(f)
            for u in range(f + 1, 13):
                flip(u)
                for p in range(u + 1, 14):
                    flip(p)
                    s = N
                    for v in V:
                        s *= v / 100.0
                    c += s
                    flip(p)
                flip(u)
            flip(f)
        flip(g)
    return round(c / 3.5)


def estimar_premios(recaudacion, bote, V, V15, temporada, sin_pleno_15=False, minimos=None):
    """V: 14 % jugados (0-100) del signo considerado en cada partido; V15: % jugado del pleno.
    sin_pleno_15: los 14 partidos tienen resultado pero el pleno no -> 0 acertantes de 15 (como la web).
    minimos: acertantes ya conocidos por categoria (la estimacion no baja de ahi).
    Devuelve {cat: (acertantes, premio)} para 15..10."""
    if temporada < 2016:
        rep, precio = {15: 8.5, 14: 15, 13: 7.5, 12: 7.5, 11: 7.5, 10: 9}, 0.5
    else:
        rep, precio = {15: 7.5, 14: 16, 13: 7.5, 12: 7.5, 11: 7.5, 10: 9}, 0.75
    o = recaudacion
    N = o / precio
    base = N
    for v in V:
        base *= v / 100.0
    R = [(100.0 - v) / v if v > 0 else 0.0 for v in V]
    e = _esym(R, 4)
    n = {14: round(base), 13: round(base * e[1]), 12: round(base * e[2]),
         11: round(base * e[3]), 10: _n10_web(N, V)}
    for k, m in (minimos or {}).items():
        if k in n and m:
            n[k] = max(n[k], int(m))
    out = {}
    out[14] = (n[14], impuestos(round(o * rep[14] / max(n[14], 1)) / 100))
    n15 = 0 if sin_pleno_15 else round(n[14] * V15 / 100.0)
    if minimos and minimos.get(15):
        n15 = max(n15, int(minimos[15]))
    if n15 > 0:
        out[15] = (n15, impuestos(round(100 * (o * rep[15] / 100 + bote) / n15) / 100))
    else:
        out[15] = (0, impuestos(round(100 * (o * rep[15] / 100 + bote)) / 100))
    for k in (13, 12, 11, 10):
        n[k] = max(n[k], 1)
    out[13] = (n[13], impuestos(round(o * rep[13] / n[13]) / 100))
    out[12] = (n[12], impuestos(round(o * rep[12] / n[12]) / 100))
    p11 = impuestos(round(o * rep[11] / n[11]) / 100)
    if p11 < 1:
        out[11] = (n[11], 0.0)
        out[12] = (n[12], impuestos(round(o * (rep[11] + rep[12]) / n[12]) / 100))
    else:
        out[11] = (n[11], p11)
    p10 = impuestos(round(o * rep[10] / n[10]) / 100)
    out[10] = (n[10], p10 if p10 >= 1.5 else 0.0)
    return out


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": gj.UA if hasattr(gj, "UA") else "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _lae(prob):
    lae = {int(x["numero"]): x for x in (prob.get("partidos", {}).get("lae") or []) if x.get("numero")}
    V = []
    for n in range(1, 15):
        d = lae.get(n) or {}
        V.append([float(d.get(f"porc_{s}_dec", d.get(f"porc_{s}", 0)) or 0) for s in "1X2"])
    d = lae.get(15) or {}
    L = [float(d.get(f"porc_15L_{g}_dec", d.get(f"porc_15L_{g}", 0)) or 0) for g in GOALS]
    Vv = [float(d.get(f"porc_15V_{g}_dec", d.get(f"porc_15V_{g}", 0)) or 0) for g in GOALS]
    return V, L, Vv


def estado_jornada(t, j):
    """Resultados actuales de la jornada: en directo si es la que se esta jugando, si no del escrutinio."""
    esc = gj.get_json("escrutinios", t, j) or {}
    prob = gj.get_json("probabilidades", t, j) or {}
    partidos = {int(p["num"]): p for p in esc.get("partidos", [])}
    live = []
    try:
        live = _get(LIVE_URL)
        if not live or int(live[0].get("jornada", 0)) != j or int(live[0].get("temporada", 0)) != t:
            live = []
    except Exception:  # noqa: BLE001  sin directo: se usa el escrutinio
        live = []
    lv = {int(p["orden"]): p for p in live}
    filas = []
    for n in range(1, 16):
        p, d = partidos.get(n) or {}, lv.get(n)
        if d is not None:
            est = (d.get("estado") or "").lower()
            empezado = est.startswith("final") or d.get("live") in (1, "1") or est == "directo"
            gl, gv = d.get("local_goles"), d.get("visitante_goles")
            marcador = f"{gl}-{gv}" if empezado and gl not in (None, "") else "-"
            signo = (d.get("signo") or "") if empezado else ""
            goles = (d.get("signo_goles") or "") if empezado else ""
            minuto = "Final" if est.startswith("final") else (f"{d.get('info_minute')}'" if d.get("live") in (1, "1") else (d.get("dia", "") + " " + d.get("hora", "")))
            fin = est.startswith("final")
        else:
            res = (p.get("resultado") or "").strip()
            signo = p.get("signo") or ""
            goles = p.get("signo_goles") or ""
            marcador = res if res not in ("", "-") else "-"
            fin = bool(signo)
            minuto = "Final" if fin else (p.get("dia", "") + " " + p.get("hora", ""))
        filas.append(dict(num=n, local=p.get("local", (d or {}).get("local", "")), visitante=p.get("visitante", (d or {}).get("visitante", "")),
                          marcador=marcador, signo=signo if n <= 14 else "", goles=goles if n == 15 else "",
                          minuto=minuto, fin=fin))
    V, L, Vv = _lae(prob)
    return dict(temporada=t, jornada=j, estado=esc.get("estado", "?"), directo=bool(live),
                recaudacion=_num_es(esc.get("recaudacion")), bote=_num_es(esc.get("bote")),
                premios_reales={int(a["acierto"]): (a.get("acertantes"), float(a.get("premio") or 0))
                                for a in esc.get("acertantes") or []},
                filas=filas, lae=V, lae15=(L, Vv))


def estimar_desde_estado(st, modo="min"):
    """modo "min": lo que falta sale como juega la mayoría (premio mínimo, el de la web por defecto);
    modo "max": lo que falta sale con el signo menos jugado (premio máximo)."""
    elegir = min if modo == "max" else max
    V = []
    for f, pcts in zip(st["filas"][:14], st["lae"]):
        if f["signo"] in ("1", "X", "2"):
            V.append(pcts["1X2".index(f["signo"])])
        else:
            V.append(elegir(pcts))
    L, Vv = st["lae15"]
    g = st["filas"][14]["goles"]
    if len(g) == 2 and g[0] in GOALS and g[1] in GOALS:
        V15 = L[GOALS.index(g[0])] * Vv[GOALS.index(g[1])] / 100
    else:
        V15 = elegir(L) * elegir(Vv) / 100 if L and Vv else 0
    sin_pleno = all(f["signo"] in ("1", "X", "2") for f in st["filas"][:14]) and len(g) != 2
    minimos = {c: n for c, (n, _p) in (st.get("premios_reales") or {}).items() if n} if modo == "min" else None
    return estimar_premios(st["recaudacion"], st["bote"], V, V15, st["temporada"],
                           sin_pleno_15=sin_pleno, minimos=minimos)


def cobro(st, cols, pleno):
    """Lo que cobran las columnas con la situacion actual (premios reales si esta escrutada,
    estimados si no). pleno: 'gl gv' tipo '11' o None (sin pleno no se puede cobrar el 15)."""
    signos = [f["signo"] for f in st["filas"][:14]]
    jugados = [s in ("1", "X", "2") for s in signos]
    goles15 = st["filas"][14]["goles"]
    escrutada = st["estado"] == "ESCRUTADA"
    est = estimar_desde_estado(st)
    reales = st["premios_reales"]
    plist = list(pleno) if isinstance(pleno, (list, tuple)) else [pleno] * len(cols)
    total = 0.0
    for c, q in zip(cols, plist):
        ac = sum(1 for i in range(14) if jugados[i] and c[i] == signos[i])
        cat = 15 if (ac == 14 and q and goles15 == q) else ac
        if cat >= 10:
            total += reales[cat][1] if escrutada and cat in reales else est[cat][1]
    return total, escrutada


def detalle_real(st, cols, pleno):
    """Escrutinio definitivo con premios reales: {cat: (columnas, premio_unitario)}, total, signos."""
    plist = list(pleno) if isinstance(pleno, (list, tuple)) else [pleno] * len(cols)
    signos = [f["signo"] for f in st["filas"][:14]]
    goles15 = st["filas"][14]["goles"]
    reales = st["premios_reales"]
    det, total = {}, 0.0
    for c, q in zip(cols, plist):
        ac = sum(1 for i in range(14) if c[i] == signos[i])
        cat = 15 if (ac == 14 and q and goles15 == q) else ac
        if cat >= 10:
            pr = reales.get(cat, (0, 0.0))[1]
            n, _ = det.get(cat, (0, pr))
            det[cat] = (n + 1, pr)
            total += pr
    return det, round(total, 2), "".join(signos), goles15


def mejor_caso(st, cols, pleno):
    """Lo mejor que puede pasar: los partidos que aun no han empezado salen como los tiene una de tus
    columnas (los empezados cuentan con su resultado actual). Se prueba el escenario de cada columna
    (estimando los premios de ese escenario) y se queda el que mas cobra en total.
    Devuelve (total, n_columna, aciertos_de_esa_columna, pendientes)."""
    plist = list(pleno) if isinstance(pleno, (list, tuple)) else [pleno] * len(cols)
    filas = st["filas"]
    pend = [i for i in range(14) if filas[i]["marcador"] == "-" and not filas[i]["signo"]]
    pend15 = filas[14]["marcador"] == "-" and not filas[14]["goles"]
    if not cols:
        return 0.0, None, 0, len(pend)
    mejor = (-1.0, None, 0)
    vistos = set()
    for n, (c, q) in enumerate(zip(cols, plist)):
        clave = ("".join(c[i] for i in pend), q if pend15 else None)
        if clave in vistos:
            continue
        vistos.add(clave)
        esc = dict(st, estado="ESTIMACION", filas=[dict(f) for f in filas])
        for i in pend:
            esc["filas"][i]["signo"] = c[i]
        if pend15 and q:
            esc["filas"][14]["goles"] = q
        total, _ = cobro(esc, cols, plist)
        sig = [f["signo"] for f in esc["filas"][:14]]
        # en este escenario pueden acertar mas otras columnas con los mismos signos pendientes
        ac, n_mejor = max((sum(1 for i in range(14) if x[i] == sig[i]), -k) for k, x in enumerate(cols))
        # primero el escenario con mas aciertos; a igualdad, el que mas cobraria
        if (ac, total) > (mejor[2], mejor[0]):
            mejor = (total, -n_mejor, ac)
    return mejor[0], mejor[1], mejor[2], len(pend)


def informe(st, cols, pleno):
    """Texto del panel: resultados, estimacion y como van tus columnas."""
    signos = [f["signo"] for f in st["filas"][:14]]
    jugados = [s in ("1", "X", "2") for s in signos]
    n_jug = sum(jugados)
    goles15 = st["filas"][14]["goles"]
    est = estimar_desde_estado(st)
    escrutada = st["estado"] == "ESCRUTADA"
    reales = st["premios_reales"]
    temp = f"{st['temporada'] - 2001:02d}/{st['temporada'] - 2000:02d}"
    L = [f"Temporada {temp} · Jornada {st['jornada']} · {st['estado']}" + (" · EN DIRECTO" if st["directo"] else ""),
         f"Recaudación {st['recaudacion']:,.0f} €   Bote {st['bote']:,.0f} €".replace(",", "."), ""]
    for f in st["filas"]:
        s = f["signo"] or (f["goles"] if f["num"] == 15 else "")
        L.append(f"{f['num']:>2} {f['local'][:13]:<13}-{f['visitante'][:13]:<13} {f['marcador']:>5} {s or '·':>2}  {f['minuto']}")
    L += ["", "Premios" + (" (reales | estimación web)" if escrutada else " estimados (método de la web)"),
          "  Cat   Acertantes        Premio"]
    for c in (15, 14, 13, 12, 11, 10):
        na, pe = est[c]
        if escrutada and c in reales:
            ra, rp = reales[c]
            L.append(f"  {c:>3} {ra or 0:>11,} {rp:>13,.2f} € | {pe:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        else:
            L.append(f"  {c:>3} {na:>11,} {pe:>13,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    if cols:
        cuenta, total, mejor = {}, 0.0, 0
        for c in cols:
            ac = sum(1 for i in range(14) if jugados[i] and c[i] == signos[i])
            mejor = max(mejor, ac)
            cat = 15 if (ac == 14 and len(goles15) == 2 and goles15 == pleno) else ac
            cuenta[cat] = cuenta.get(cat, 0) + 1
            if cat >= 10:
                total += (reales[cat][1] if escrutada and cat in reales else est[cat][1])
        gasto = len(cols) * gj.PRECIO
        L += ["", f"Tus {len(cols)} columnas ({gasto:.2f} €) · partidos con resultado: {n_jug}/14 · pleno {pleno[0]}-{pleno[1]}"]
        L.append("  " + "  ".join(f"{k}: {v}" for k, v in sorted(cuenta.items(), reverse=True)))
        L.append(f"  Mejor columna: {mejor} aciertos (máximo posible {mejor + 14 - n_jug})")
        etiqueta = "Premio" if escrutada else "Premio estimado si acabara así"
        L.append(f"  {etiqueta}: {total:,.2f} €   (balance {total - gasto:+,.2f} €)".replace(",", "X").replace(".", ",").replace("X", "."))
    return "\n".join(L)
