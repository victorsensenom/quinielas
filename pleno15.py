"""Pleno al 15 en el generador: tabla de goles 0/1/2/M de cada equipo y reparto entre columnas."""
import math
import tkinter as tk
from tkinter import ttk

import numpy as np

GOALS = "012M"


def _pct(d, side):
    v = []
    for g in GOALS:
        x = (d or {}).get(f"porc_15{side}_{g}_dec", (d or {}).get(f"porc_15{side}_{g}"))
        v.append(float(x) if x not in (None, "") else math.nan)
    return np.array(v)


def marcadores(L, V, Llae=None, Vlae=None):
    """Lista de (marcador '21', prob %, jugado %) ordenada de más a menos probable."""
    out = []
    for i, gl in enumerate(GOALS):
        for k, gv in enumerate(GOALS):
            p = L[i] * V[k] / 100
            j = (Llae[i] * Vlae[k] / 100) if Llae is not None and Vlae is not None else math.nan
            out.append((gl + gv, p, j))
    return sorted(out, key=lambda x: -x[1])


def repartir(K, L, V, Llae, Vlae, b=0.5, max_marcadores=8):
    """Reparte K columnas entre los marcadores más valiosos (prob x (prob/jugado)^b), en proporción.
    Devuelve una lista de K plenos ('11', '10'...) intercalados para que cada uno caiga en columnas
    de todo tipo."""
    # candidatos: los marcadores MÁS PROBABLES; el valor (poco jugados) solo reparte columnas entre ellos
    n = max(1, min(max_marcadores, K))
    ms = marcadores(L, V, Llae, Vlae)[:n]
    top = []
    for m, p, j in ms:
        val = p * (min((p / j) ** b, 2.0) if j and j > 0 and not math.isnan(j) else 1.0)
        top.append((m, val))
    top.sort(key=lambda x: -x[1])
    tot = sum(w for _, w in top) or 1
    cuota = [K * w / tot for _, w in top]
    cnt = [int(c) for c in cuota]
    for i in sorted(range(n), key=lambda i: -(cuota[i] - cnt[i]))[:K - sum(cnt)]:
        cnt[i] += 1
    marc = [(m, c) for (m, _), c in zip(top, cnt) if c > 0]
    # intercalado proporcional
    out, usado = [], [0] * len(marc)
    for _ in range(K):
        i = min(range(len(marc)), key=lambda i: (usado[i] + 0.5) / marc[i][1] if usado[i] < marc[i][1] else 1e9)
        out.append(marc[i][0])
        usado[i] += 1
    return out


class PlenoTabla(ttk.LabelFrame):
    """Tabla editable de % de goles (probables) de cada equipo, con el % jugado al lado."""

    def __init__(self, master):
        super().__init__(master, text="Pleno al 15", padding=6)
        self.web = None
        self.lae = (None, None)
        top = ttk.Frame(self)
        top.pack(fill="x")
        for c, h in enumerate(["Equipo", "0", "1", "2", "M"]):
            ttk.Label(top, text=h, font=("Segoe UI", 9, "bold")).grid(row=0, column=c, padx=4)
        self.nombres, self.ents, self.jug = [], [], []
        for r in range(2):
            nm = ttk.Label(top, text="Local" if r == 0 else "Visitante", width=32)
            nm.grid(row=1 + 2 * r, column=0, sticky="w", rowspan=2)
            fila, fj = [], []
            for c in range(4):
                e = ttk.Entry(top, width=6, justify="right")
                e.grid(row=1 + 2 * r, column=1 + c, padx=2)
                lj = ttk.Label(top, text="", foreground="#777", font=("Segoe UI", 8))
                lj.grid(row=2 + 2 * r, column=1 + c)
                fila.append(e)
                fj.append(lj)
            self.nombres.append(nm)
            self.ents.append(fila)
            self.jug.append(fj)
        ttk.Label(top, text="(gris = % jugado)", foreground="#777", font=("Segoe UI", 8)).grid(row=5, column=0, sticky="w")

        modo = ttk.Frame(self)
        modo.pack(fill="x", pady=(4, 0))
        self.var_modo = tk.StringVar(value="repartir")
        ttk.Radiobutton(modo, text="Repartir entre los marcadores más probables", value="repartir",
                        variable=self.var_modo).pack(side="left")
        ttk.Radiobutton(modo, text="Uno solo:", value="fijo", variable=self.var_modo).pack(side="left", padx=(10, 2))
        self.cb_l = ttk.Combobox(modo, values=list(GOALS), width=3, state="readonly")
        self.cb_l.pack(side="left")
        ttk.Label(modo, text="-").pack(side="left")
        self.cb_v = ttk.Combobox(modo, values=list(GOALS), width=3, state="readonly")
        self.cb_v.pack(side="left")
        ttk.Button(modo, text="Ver marcadores", command=self.pinta_marcadores).pack(side="left", padx=8)
        self.lbl = ttk.Label(self, text="", foreground="#333", font=("Consolas", 9), justify="left")
        self.lbl.pack(anchor="w", pady=(4, 0))

    def cargar(self, local, visitante, real15, lae15):
        self.nombres[0].config(text=local[:32])
        self.nombres[1].config(text=visitante[:32])
        L, V = _pct(real15, "L"), _pct(real15, "V")
        Ll, Vl = _pct(lae15, "L"), _pct(lae15, "V")
        if np.isnan(L).any() or np.isnan(V).any():
            L, V = np.array([25.0, 35, 25, 15]), np.array([30.0, 35, 22, 13])
        self.web = (L, V)
        self.lae = (Ll, Vl)
        for r, arr in enumerate((Ll, Vl)):
            for c in range(4):
                self.jug[r][c].config(text="" if math.isnan(arr[c]) else f"{arr[c]:.0f}%")
        self.restaurar()
        m = marcadores(L, V)[0][0]
        self.cb_l.set(m[0])
        self.cb_v.set(m[1])
        self.pinta_marcadores()

    def restaurar(self):
        if not self.web:
            return
        for r, arr in enumerate(self.web):
            for c in range(4):
                self.ents[r][c].delete(0, "end")
                self.ents[r][c].insert(0, f"{arr[c]:.0f}")

    def leer(self):
        """(L, V) en % (suman 100), respetando el valor exacto de la web si la casilla no se tocó."""
        res = []
        for r in range(2):
            v = []
            for c in range(4):
                txt = self.ents[r][c].get().strip().replace(",", ".")
                try:
                    x = float(txt or 0)
                except ValueError:
                    raise ValueError(f"Pleno: «{txt}» no es un número.")
                if self.web is not None and txt == f"{self.web[r][c]:.0f}":
                    x = float(self.web[r][c])
                v.append(max(x, 0.0))
            v = np.array(v)
            if v.sum() <= 0:
                raise ValueError("Pleno: pon algún % mayor que 0.")
            res.append(v / v.sum() * 100)
        return res[0], res[1]

    def pinta_marcadores(self):
        try:
            L, V = self.leer()
        except ValueError:
            return
        ms = marcadores(L, V, *self.lae)[:6]
        self.lbl.config(text="Más probables: " + "  ".join(
            f"{m[0]}-{m[1]} {p:.1f}%" + (f" (jug {j:.1f}%)" if not math.isnan(j) else "") for m, p, j in ms))

    def plenos_para(self, K, b):
        """Lista de K plenos y la probabilidad de acertar el de cada columna."""
        L, V = self.leer()
        if self.var_modo.get() == "fijo" and self.cb_l.get() and self.cb_v.get():
            pl = [self.cb_l.get() + self.cb_v.get()] * K
        else:
            pl = repartir(K, L, V, *self.lae, b=b)
        prob = {m: p / 100 for m, p, _ in marcadores(L, V)}
        return pl, [prob[p] for p in pl]
