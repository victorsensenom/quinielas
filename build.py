"""Construye data/partidos.csv, data/jornadas.csv, data/pleno15.csv y data/jornadas_meta.csv
a partir de la cache cruda en data/raw (generada por fetch.py). No hace peticiones de red."""
import csv
import datetime as dt
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
RAW = os.path.join(DATA, "raw")
PRECIO = 0.75  # vigente desde temporada 2015/16 (ver README)


def load_json(name, t, j):
    p = os.path.join(RAW, name, f"{t}_{j:02d}.json")
    if not os.path.exists(p):
        return None
    try:
        return json.loads(open(p, "rb").read().decode("utf-8"))
    except Exception:
        return None


def load_xml(name, t, j):
    p = os.path.join(RAW, name, f"{t}_{j:02d}.xml")
    if not os.path.exists(p):
        return {}
    try:
        root = ET.fromstring(open(p, "rb").read())
    except Exception:
        return {}
    return {int(e.get("num")): e.attrib for e in root.iter("partido")}


def es_num(s):
    """'4.297.568,25' -> 4297568.25"""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def num(v):
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def triple(d, dec=True):
    """Extrae (1,X,2) de un dict con porc_1/porc_X/porc_2 (+ _dec)."""
    if not d:
        return (None, None, None)
    out = []
    for k in ("1", "X", "2"):
        v = num(d.get(f"porc_{k}_dec")) if dec else None
        if v is None:
            v = num(d.get(f"porcDec_{k}"))
        if v is None:
            v = num(d.get(f"porc_{k}"))
        out.append(v)
    if all(x is None for x in out):
        return (None, None, None)
    return tuple(out)


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return ("%.4f" % v).rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


def fecha(epoch):
    if not epoch:
        return ""
    # fecha_jornada es la medianoche local (Europe/Madrid, UTC+1/+2); +3h cae siempre en el mismo dia
    return (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(epoch) + 3 * 3600)).strftime("%Y-%m-%d")


def main():
    files = sorted(glob.glob(os.path.join(RAW, "escrutinios", "*.json")))
    keys = sorted({tuple(map(int, re.match(r"(\d+)_(\d+)", os.path.basename(f)).groups())) for f in files})
    P, J, P15, META = [], [], [], []
    problems = []
    for t, j in keys:
        esc = load_json("escrutinios", t, j)
        if not esc or not esc.get("escrutinio") or esc.get("estado") != "ESCRUTADA":
            continue
        prob = load_json("probabilidades", t, j) or {}
        pp = prob.get("partidos") or {}
        by = {k: {int(x.get("numero")): x for x in (pp.get(k) or []) if x.get("numero") is not None}
              for k in ("lae", "real", "quinielista")}
        xml_lae = load_xml("porcentajes_lae", t, j)
        xml_real = load_xml("probabilidad_real", t, j)
        xml_quin = load_xml("porcentajes_quinielista", t, j)
        partidos = {int(p["num"]): p for p in esc.get("partidos", [])}
        signos = 0
        for n in range(1, 16):
            p = partidos.get(n)
            if p is None:
                problems.append(f"{t}-{j}: falta partido {n}")
                continue
            row = dict(temporada=t, jornada=j, num=n, local=p.get("local", ""), visitante=p.get("visitante", ""),
                       division=p.get("division", ""), resultado=p.get("resultado", "") or "")
            if n <= 14:
                row["signo"] = p.get("signo") or ""
                if row["signo"] in ("1", "X", "2"):
                    signos += 1
                else:
                    problems.append(f"{t}-{j}: partido {n} sin signo ({row['signo']!r})")
                lae = triple(by["lae"].get(n))
                if lae[0] is None:
                    lae = triple({"porc_1": p.get("porcentaje1"), "porc_X": p.get("porcentajeX"),
                                  "porc_2": p.get("porcentaje2")})
                if lae[0] is None:
                    lae = triple(xml_lae.get(n))
                real = triple(by["real"].get(n))
                if real[0] is None:
                    real = triple(xml_real.get(n))
                quin = triple(by["quinielista"].get(n))
                if quin[0] is None:
                    quin = triple(xml_quin.get(n))
                for lab, tr in (("lae", lae), ("prob", real), ("quin", quin)):
                    for k, v in zip(("1", "X", "2"), tr):
                        row[lab + k] = v
                    if tr[0] is not None:
                        s = sum(x or 0 for x in tr)
                        if abs(s - 100) > 2.5:
                            problems.append(f"{t}-{j}: partido {n} {lab} suma {s:.2f}")
            else:
                row["signo"] = p.get("signo_goles") or ""
                if not re.fullmatch(r"[012M][012M]", row["signo"] or ""):
                    problems.append(f"{t}-{j}: pleno15 signo_goles {row['signo']!r}")
                r15 = dict(temporada=t, jornada=j, local=row["local"], visitante=row["visitante"],
                           resultado=row["resultado"], signo_goles=row["signo"])
                for lab, src in (("lae", by["lae"].get(15) or xml_lae.get(15)),
                                 ("prob", by["real"].get(15) or xml_real.get(15)),
                                 ("quin", by["quinielista"].get(15) or xml_quin.get(15))):
                    for side in ("L", "V"):
                        for g in ("0", "1", "2", "M"):
                            v = None
                            if src:
                                v = num(src.get(f"porc_15{side}_{g}_dec"))
                                if v is None:
                                    v = num(src.get(f"porcDec_15{side}_{g}"))
                                if v is None:
                                    v = num(src.get(f"porc_15{side}_{g}"))
                            if v is None and lab == "lae":
                                v = num(p.get(f"porcentaje15{side}{g}"))
                            r15[f"{lab}_{side}{g}"] = v
                P15.append(r15)
            P.append(row)
        if signos != 14:
            problems.append(f"{t}-{j}: {signos} signos 1X2 validos")
        jr = dict(temporada=t, jornada=j, fecha=fecha(esc.get("fecha_jornada")),
                  recaudacion=es_num(esc.get("recaudacion")), bote=es_num(esc.get("bote")), precio_apuesta=PRECIO)
        ac = {int(a["acierto"]): a for a in (esc.get("acertantes") or []) if a.get("acierto") is not None}
        for k in range(15, 9, -1):
            a = ac.get(k)
            jr[f"acert{k}"] = num(a.get("acertantes")) if a else None
            jr[f"premio{k}"] = num(a.get("premio")) if a else None
            if a is None:
                problems.append(f"{t}-{j}: sin categoria {k}")
            elif jr[f"acert{k}"] is None or jr[f"premio{k}"] is None:
                problems.append(f"{t}-{j}: categoria {k} no numerica {a}")
        if jr["recaudacion"] is None:
            problems.append(f"{t}-{j}: recaudacion no numerica {esc.get('recaudacion')!r}")
        J.append(jr)
        fm = prob.get("fechaModificacion") or {}
        META.append(dict(temporada=t, jornada=j, id_jornada=esc.get("Id"), estado=esc.get("estado"),
                         cr=esc.get("cr"), orden_posicion_real=esc.get("orden_posicion_real"),
                         premio_elige8=esc.get("premioElige8"), acertantes_elige8=esc.get("acertantesElige8"),
                         ts_lae=fm.get("lae"), ts_real=fm.get("betfair"), ts_quinielista=fm.get("quinielista")))

    def write(name, rows, cols):
        with open(os.path.join(DATA, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([fmt(r.get(c)) for c in cols])

    write("partidos.csv", P, "temporada,jornada,num,local,visitante,division,resultado,signo,lae1,laeX,lae2,"
          "prob1,probX,prob2,quin1,quinX,quin2".split(","))
    write("jornadas.csv", J, "temporada,jornada,fecha,recaudacion,bote,acert15,premio15,acert14,premio14,acert13,"
          "premio13,acert12,premio12,acert11,premio11,acert10,premio10,precio_apuesta".split(","))
    c15 = ["temporada", "jornada", "local", "visitante", "resultado", "signo_goles"] + \
          [f"{lab}_{s}{g}" for lab in ("lae", "prob", "quin") for s in "LV" for g in "012M"]
    write("pleno15.csv", P15, c15)
    write("jornadas_meta.csv", META, list(META[0].keys()) if META else [])
    with open(os.path.join(DATA, "validacion.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(problems) + "\n")
    print(f"partidos={len(P)} jornadas={len(J)} problemas={len(problems)}")
    for p in problems[:40]:
        print(" ", p)


if __name__ == "__main__":
    main()
