"""Programa de la quiniela.

Ventana principal: escrutinio (en directo) de la apuesta real de la jornada e historial de jornadas
jugadas. "Cargar fichero de la jornada" fija la apuesta real (con su pleno al 15) hasta la siguiente.
"Generar quiniela" abre la ventana del generador (estrategia de valor).
"""
import dataclasses
import json
import urllib.request
import webbrowser
import math
import os
import re
import sys
import threading

# numpy viaja en lib\ junto al programa, por si el usuario de Windows no lo tiene instalado
_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_LIB):
    sys.path.insert(0, _LIB)
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np

import generar_jornada as gj
import estimacion
import cierre
import clasificacion
import ligas
import puntos_jornada
from panel_directo import PanelDirecto
from pleno15 import PlenoTabla
from engine.reduce import col_prob, cols_to_idx, coverage_report
from engine.data import GOAL_CHARS, SIGN_CHARS
from strategies.valor_mix import Strategy

GOALS = ["0", "1", "2", "M"]

CARPETA = os.path.dirname(os.path.abspath(__file__))


def poner_icono(ventana):
    """Icono del programa (icono.ico / icono.png junto al programa); si no están, se queda el de Python."""
    try:
        ico = os.path.join(CARPETA, "icono.ico")
        if os.path.exists(ico):
            ventana.iconbitmap(ico)
        png = os.path.join(CARPETA, "icono.png")
        if os.path.exists(png):
            ventana._icono = tk.PhotoImage(file=png)
            ventana.iconphoto(True, ventana._icono)
    except tk.TclError:
        pass


# Enlace para invitar al autor a un café (PayPal). Vacío = no se muestra el botón.
DONAR_URL = "https://paypal.me/Iquinielas"
REPO_URL = "https://github.com/victorsensenom/quinielas"

# colores de la ventana del generador
C_AZUL, C_AZUL2, C_LINEA = "#1a365d", "#2b6cb0", "#cbd5e0"
C_FILAS = ("#ffffff", "#f7fafc")       # filas alternas
C_ENCIMA, C_MARCADA = "#ebf8ff", "#90cdf4"
C_FIJO, C_DOBLE, C_TRIPLE = "#c6f6d5", "#fefcbf", "#fed7d7"


class Generador(tk.Toplevel):
    """Ventana para generar la quiniela de la semana con la estrategia de valor."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Generar quiniela")
        poner_icono(self)
        self.resizable(True, True)
        self.info = None
        self.web_prob = None
        self.columns = None
        self.t = gj.temporada_actual()
        self.j = None

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Temporada:").pack(side="left")
        self.temporadas = {f"{y - 2001:02d}/{y - 2000:02d}": y for y in range(self.t, 2004, -1)}
        self.cb_t = ttk.Combobox(top, values=list(self.temporadas), width=6, state="readonly")
        self.cb_t.set(next(iter(self.temporadas)))
        self.cb_t.bind("<<ComboboxSelected>>", lambda _e: setattr(self, "t", self.temporadas[self.cb_t.get()]))
        self.cb_t.pack(side="left", padx=(4, 12))
        ttk.Label(top, text="Jornada (vacío = la abierta):").pack(side="left")
        self.ent_j = ttk.Entry(top, width=5)
        self.ent_j.pack(side="left", padx=(4, 8))
        self.btn_load = ttk.Button(top, text="Cargar jornada", command=self.cargar)
        self.btn_load.pack(side="left")
        ttk.Label(top, text="   Gasto (€):").pack(side="left")
        self.var_gasto = tk.StringVar(value="48")
        self.var_gasto.trace_add("write", lambda *_: self.actualiza_cols())
        ttk.Entry(top, width=7, textvariable=self.var_gasto).pack(side="left", padx=4)
        self.lbl_cols = ttk.Label(top, text="")
        self.lbl_cols.pack(side="left")

        banda = tk.Frame(self, bg=C_AZUL)
        banda.pack(fill="x", padx=8, pady=(0, 6))
        self.lbl_cierre = tk.Label(banda, text="", font=("Segoe UI", 10, "bold"), bg=C_AZUL, fg="#fbd38d", padx=10)
        self.lbl_cierre.pack(side="right")
        self.lbl_tit = tk.Label(banda, text="Pulsa «Cargar jornada»", font=("Segoe UI", 11, "bold"), bg=C_AZUL, fg="white",
                                padx=10, pady=6, anchor="w")
        self.lbl_tit.pack(side="left", fill="x", expand=True)
        self.cierre = (None, False)

        self.tabla = tk.Frame(self, bg=C_LINEA, padx=1, pady=1)
        self.tabla.pack(fill="x", padx=8)
        heads = ["#", "Partido", "Tu % 1", "Tu % X", "Tu % 2", "Jugado 1/X/2", "Columnas 1/X/2",
                 "Casa", "Goles", "Forma", "C.cara", "PUNTOS", "Propone"]
        for c, h in enumerate(heads):
            tk.Label(self.tabla, text=h, font=("Segoe UI", 9, "bold"), bg=C_AZUL2, fg="white", padx=5, pady=5,
                     anchor="w" if c == 1 else "center").grid(row=0, column=c, sticky="nsew")
        self.rows, self.pts, self.fondos = [], [], []
        self.marcada, self.encima = None, None
        fuente, negrita = ("Segoe UI", 9), ("Segoe UI", 9, "bold")
        for i in range(14):
            bg = C_FILAS[i % 2]
            piezas = []

            def etiqueta(col, **kw):
                w = tk.Label(self.tabla, bg=bg, font=kw.pop("font", fuente), text="", pady=3, **kw)
                w.grid(row=i + 1, column=col, sticky="nsew")
                piezas.append(w)
                return w

            etiqueta(0, width=3).config(text=str(i + 1), fg="#718096")
            name = etiqueta(1, width=54, anchor="w", padx=5)
            ents = []
            for k in range(3):
                celda = tk.Frame(self.tabla, bg=bg)
                celda.grid(row=i + 1, column=2 + k, sticky="nsew")
                piezas.append(celda)
                e = tk.Entry(celda, width=6, justify="right", relief="solid", bd=1, highlightthickness=0,
                             font=fuente)
                e.pack(padx=3, pady=2)
                e.bind("<FocusIn>", lambda _e, n=i: self.marcar(n))
                ents.append(e)
            jug = etiqueta(5, width=12)
            res = etiqueta(6, width=14)
            self.rows.append((name, ents, jug, res))
            fila = [etiqueta(7 + c, width=6, anchor="e", padx=4, font=negrita if c == 4 else fuente) for c in range(5)]
            sig = tk.Label(self.tabla, bg=bg, font=negrita, text="", width=8)   # el color lo pone la propuesta
            sig.grid(row=i + 1, column=12, sticky="nsew", padx=3, pady=2)
            fila.append(sig)
            self.pts.append(fila)
            self.fondos.append(piezas)
            for w in piezas + [sig]:
                w.bind("<Button-1>", lambda _e, n=i: self.marcar(n))
                w.bind("<Enter>", lambda _e, n=i: self._encima(n))
                w.bind("<Leave>", lambda _e: self._encima(None))

        self.lbl_pts = ttk.Label(self, text="", foreground="#555", padding=(8, 4), wraplength=1100, justify="left")
        self.lbl_pts.pack(anchor="w")
        self.pleno = PlenoTabla(self)
        self.pleno.pack(fill="x", padx=8)
        self.plenos = None

        est = ttk.Frame(self, padding=8)
        est.pack(fill="x")
        ttk.Label(est, text="Más favoritos").pack(side="left")
        self.var_b = tk.DoubleVar(value=0.5)
        ttk.Scale(est, from_=0.0, to=1.0, variable=self.var_b, length=180).pack(side="left", padx=4)
        ttk.Label(est, text="Más valor (recomendado: centro)").pack(side="left")

        bot = ttk.Frame(self, padding=8)
        bot.pack(fill="x")
        ttk.Button(bot, text="Restaurar % de la web", command=self.restaurar).pack(side="left")
        self.btn_gen = tk.Button(bot, text="Generar quiniela", command=self.generar, bg=C_AZUL2, fg="white", relief="flat",
                                 activebackground=C_AZUL, activeforeground="white", disabledforeground="#e2e8f0",
                                 font=("Segoe UI", 9, "bold"), padx=14, pady=3, cursor="hand2")
        self.btn_gen.pack(side="left", padx=8)
        self.btn_save = ttk.Button(bot, text="Guardar archivo", command=self.guardar, state="disabled")
        self.btn_save.pack(side="left")

        self.txt = tk.Text(self, height=10, width=60, font=("Consolas", 10), bg="#f7fafc", relief="solid", bd=1)
        self.txt.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.estado = ttk.Label(self, text="", padding=(8, 0, 8, 8), foreground="#555")
        self.estado.pack(anchor="w")
        self.actualiza_cols()

    def _pinta_cierre(self):
        txt = cierre.texto(*self.cierre)
        self.lbl_cierre.config(text=txt, fg="#feb2b2" if "CERRADA" in txt else "#fbd38d")
        return txt

    # ------------------------------------------------------------------ fila marcada
    def marcar(self, i):
        """Marca la fila tocada (o donde se está escribiendo) y desmarca la anterior."""
        anterior, self.marcada = self.marcada, i
        if anterior is not None:
            self._color_fila(anterior)
        self._color_fila(i)

    def _encima(self, i):
        anterior, self.encima = self.encima, i
        if anterior is not None:
            self._color_fila(anterior)
        if i is not None:
            self._color_fila(i)

    def _color_fila(self, i):
        c = C_MARCADA if i == self.marcada else C_ENCIMA if i == self.encima else C_FILAS[i % 2]
        for w in self.fondos[i]:
            w.config(bg=c)
        if not self.pts[i][5].cget("text"):
            self.pts[i][5].config(bg=c)

    # ------------------------------------------------------------------ utilidades
    def presupuesto(self):
        try:
            return float(self.var_gasto.get().replace(",", "."))
        except ValueError:
            return None

    def actualiza_cols(self):
        g = self.presupuesto()
        if g is None or g <= 0:
            self.lbl_cols.config(text="(gasto no válido)")
            return
        n = int(math.floor(g / gj.PRECIO + 1e-9))
        self.lbl_cols.config(text=f"= {n} columnas ({n * gj.PRECIO:.2f} €)")

    def ocupado(self, msg):
        self.estado.config(text=msg)
        for b in (self.btn_load, self.btn_gen):
            b.config(state="disabled" if msg else "normal")

    # ------------------------------------------------------------------ cargar
    def cargar(self):
        txt = self.ent_j.get().strip()
        if txt and not txt.isdigit():
            messagebox.showerror("Jornada", "La jornada debe ser un número.")
            return
        t = self.t
        if not txt and t != gj.temporada_actual():
            messagebox.showinfo("Jornada", "En temporadas pasadas escribe el número de jornada.")
            return
        self.ocupado("Descargando jornada...")

        def work():
            try:
                if txt:
                    j, esc = int(txt), gj.get_json("escrutinios", t, int(txt))
                else:
                    j, esc = gj.buscar_abierta(t)
                if not esc or not esc.get("partidos"):
                    raise RuntimeError("No encuentro esa jornada (¿existe en esa temporada? ¿hay internet?).")
                prob = gj.get_json("probabilidades", t, j) or {}
                info, real15, lae15 = gj.construir_info(t, j, esc, prob)
                fm = prob.get("fechaModificacion") or {}
                fm = dict(fm, cierre=cierre.hora_cierre(t, j, esc),
                          recaudacion=estimacion._num_es(esc.get("recaudacion")), bote=estimacion._num_es(esc.get("bote")),
                          estado=esc.get("estado", ""),
                          tabla=clasificacion.obtener() if t == gj.temporada_actual() else {})
                try:                 # si fallan los puntos, la jornada se carga igual
                    ligas.descargar(max_horas=1.0)
                    fm["puntos"] = puntos_jornada.calcular(info, esc)
                except Exception as e:  # noqa: BLE001
                    fm["puntos_error"] = str(e)
                self.after(0, lambda: (setattr(self, "t_cargada", t), self.cargado(j, info, real15, lae15, fm)))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda e=e: (self.ocupado(""), messagebox.showerror("Error", str(e))))

        threading.Thread(target=work, daemon=True).start()

    def cargado(self, j, info, real15, lae15, fm):
        self.j, self.info = j, info
        self.economia = fm
        tabla = fm.get("tabla") or {}
        prob = np.array(info.prob, float)
        bad = np.isnan(prob).any(1)
        prob[bad] = np.array(info.lae, float)[bad]
        self.sin_pct = [i + 1 for i in np.flatnonzero(np.isnan(prob).any(1))]
        prob[np.isnan(prob).any(1)] = 100 / 3     # aún sin publicar: reparto igual hasta que salgan
        self.web_prob = prob
        temp = f"{self.t_cargada - 2001:02d}/{self.t_cargada - 2000:02d}"
        import datetime as _dt
        ts = fm.get("betfair") or fm.get("lae")
        aviso = ""
        if ts:
            hace = (_dt.datetime.now() - _dt.datetime.fromtimestamp(int(ts))).total_seconds() / 3600
            aviso = f"   ·   % probables actualizados el {_dt.datetime.fromtimestamp(int(ts)):%d/%m a las %H:%M}"
            if hace > 12 and info.temporada == str(gj.temporada_actual()):
                aviso += f" (hace {hace:.0f} h: mejor generar cerca del cierre)"
        self.lbl_tit.config(text=f"Temporada {temp} · Jornada {j}{aviso}")
        self.cierre = fm.get("cierre") or (None, False)
        self._pinta_cierre()
        for i, (name, ents, jug, res) in enumerate(self.rows):
            m = info.partidos[i]
            name.config(text=f"{clasificacion.texto(tabla, m.local)} - {clasificacion.texto(tabla, m.visitante)}")
            jug.config(text="—" if any(math.isnan(x) for x in m.lae) else "/".join(f"{x:.0f}" for x in m.lae))
            res.config(text="")
        self.restaurar()
        self._pinta_puntos(fm)
        if info.pleno:
            self.pleno.cargar(clasificacion.texto(tabla, info.pleno.local), clasificacion.texto(tabla, info.pleno.visitante),
                              real15, lae15)
        self.txt.delete("1.0", "end")
        self.columns = None
        self.plenos = None
        self.btn_save.config(state="disabled")
        self.ocupado("")
        self.estado.config(text="Jornada cargada. Cambia los % si quieres y pulsa «Generar quiniela».")

    def _pinta_puntos(self, fm):
        """Tabla de puntos junto a cada partido: es una ayuda para revisar, no decide las columnas."""
        p = fm.get("puntos")
        for i, fila in enumerate(self.pts):
            f = p["ui"][i] if p else None
            tr = f["trozos"] if f else None
            vals = [f"{x:+.1f}".replace(".", ",") for x in tr] + [f"{f['total']:+.1f}".replace(".", ",")] if tr else [""] * 4 + ["—"]
            for w, v in zip(fila, vals):
                w.config(text=v)
            h = p["pesos"]["h"] if p else 0
            total = f["total"] if f else None
            fila[4].config(fg="#4a5568" if total is None else "#2f855a" if total > h else "#c53030" if total < -h else "#b7791f")
            sg = f["signo"] if f else ""
            fila[5].config(text=sg, bg={1: C_FIJO, 2: C_DOBLE, 3: C_TRIPLE}.get(len(sg), C_FILAS[i % 2]))
        if p:
            cub = sum(1 for f in p["ui"] if f["trozos"])
            h = f"{p['pesos']['h']:.2f}".replace(".", ",")
            self.lbl_pts.config(text=f"Puntos: verde, más de +{h} (tiende a 1); rojo, menos de -{h} (tiende a 2); ámbar, partido abierto. "
                                     "Propone: verde fijo, amarillo doble, rojo triple. "
                                     f"Con datos de liga: {cub} de 14 (ligas hasta el {p['ultima']:%d/%m}); «—» usa solo cuotas. "
                                     f"Propone: {p['ncol']} columnas ({p['ncol'] * gj.PRECIO:.2f} €). "
                                     "Es una ayuda para revisar: en la simulación no ganó a las cuotas."
                                     + (f" Aún sin % publicados en los partidos {', '.join(map(str, self.sin_pct))}: "
                                        "llevan 33/33/33; genera más cerca del cierre." if self.sin_pct else ""))
        else:
            self.lbl_pts.config(text=f"No se pudo calcular la tabla de puntos: {fm.get('puntos_error', '')}")

    def restaurar(self):
        if self.web_prob is None:
            return
        for i, (_, ents, _, _) in enumerate(self.rows):
            for k, e in enumerate(ents):
                e.delete(0, "end")
                e.insert(0, f"{self.web_prob[i, k]:.0f}")

    # ------------------------------------------------------------------ generar
    def leer_prob(self):
        P = np.zeros((14, 3))
        for i, (_, ents, _, _) in enumerate(self.rows):
            for k, e in enumerate(ents):
                try:
                    v = float(e.get().replace(",", ".") or 0)
                except ValueError:
                    raise ValueError(f"Partido {i + 1}: «{e.get()}» no es un número.")
                if v < 0:
                    raise ValueError(f"Partido {i + 1}: los % no pueden ser negativos.")
                # la casilla muestra el % redondeado: si no se ha tocado, usa el valor exacto de la web
                # (redondear cambia las columnas elegidas)
                if self.web_prob is not None and e.get().strip() == f"{self.web_prob[i, k]:.0f}":
                    v = float(self.web_prob[i, k])
                P[i, k] = v
            if P[i].sum() <= 0:
                raise ValueError(f"Partido {i + 1}: pon al menos un % mayor que 0.")
        return P / P.sum(1, keepdims=True) * 100

    def generar(self):
        if self.info is None:
            messagebox.showinfo("Quiniela", "Primero carga la jornada.", parent=self)
            return
        g = self.presupuesto()
        if g is None or g < gj.PRECIO:
            messagebox.showerror("Gasto", f"El gasto mínimo es {gj.PRECIO:.2f} €.")
            return
        try:
            P = self.leer_prob()
        except ValueError as e:
            messagebox.showerror("Porcentajes", str(e))
            return
        info = dataclasses.replace(self.info, prob=P)
        b = round(self.var_b.get(), 2)
        K = int(math.floor(g / gj.PRECIO + 1e-9))
        try:
            plenos, p_pleno = self.pleno.plenos_para(K, b)
        except ValueError as e:
            messagebox.showerror("Pleno", str(e), parent=self)
            return
        self.ocupado("Calculando columnas...")

        def work():
            try:
                cols = Strategy(a=1.0, b=b, radius=1).generate(info, [], g)
                S = np.asarray(cols.signs)
                idx = cols_to_idx(S)
                Pn = P / 100.0
                rep = coverage_report(idx, Pn)
                pc = col_prob(idx, Pn)
                rep["p15"] = float(sum(a * q for a, q in zip(pc, p_pleno[:len(S)])))
                self.after(0, lambda: self.generado(S, plenos[:len(S)], rep))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda e=e: (self.ocupado(""), messagebox.showerror("Error", str(e))))

        threading.Thread(target=work, daemon=True).start()

    def generado(self, S, plenos, rep):
        self.columns, self.plenos = S, plenos
        for i, (_, _, _, res) in enumerate(self.rows):
            c = [int((S[:, i] == k).sum()) for k in range(3)]
            res.config(text=f"{c[0]} / {c[1]} / {c[2]}")
        self.txt.delete("1.0", "end")
        pc = lambda x: f"{100 * x:.2f} %".replace(".", ",")
        self.txt.insert("end", f"Probabilidades de este boleto (según tus %):  12 o más: {pc(rep['p12'])}  ·  "
                               f"13 o más: {pc(rep['p13'])}  ·  14: {pc(rep['p14'])}  ·  15 (con pleno): {pc(rep['p15'])}\n")
        cuenta = {}
        for p in plenos:
            cuenta[p] = cuenta.get(p, 0) + 1
        self.txt.insert("end", "Plenos: " + ", ".join(f"{p[0]}-{p[1]} en {n}" for p, n in
                                                     sorted(cuenta.items(), key=lambda x: -x[1])) + "\n\n")
        for r, p in zip(S, plenos):
            self.txt.insert("end", "".join(SIGN_CHARS[s] for s in r) + f" {p[0]}-{p[1]}\n")
        self.btn_save.config(state="normal")
        self.ocupado("")
        c = self._pinta_cierre()
        self.estado.config(text=f"{len(S)} columnas = {len(S) * gj.PRECIO:.2f} €. " + (f"{c}. " if c else "")
                                + "Recuerda: no hay garantía de premio.")
        self._pinta_valor(S, plenos)

    def _pinta_valor(self, S, plenos):
        """Premio estimado de cada columna si se acierta (método de la web con los % jugados)."""
        eco = getattr(self, "economia", {}) or {}
        recaud = eco.get("recaudacion") or 0
        if not recaud:
            return
        J = np.array(self.info.lae, float)
        Q = np.array(self.info.quin, float)
        fuente = "% jugados (LAE)"
        if np.isnan(J).any():
            J = np.where(np.isnan(J), Q, J)
            fuente = "% jugados (LAE) y, donde aún no hay, % de los quinielistas de la web"
        J = np.where(np.isnan(J), 100 / 3, J)
        L15, V15 = self.pleno.lae
        if L15 is None or np.isnan(L15).any() or np.isnan(V15).any():
            L15, V15 = self.pleno.leer()   # sin % jugados del pleno: se usan los probables como aproximación
        t = int(self.info.temporada)
        res = []
        for r, p in zip(S, plenos):
            V = [J[i, s] for i, s in enumerate(r)]
            v15 = L15["012M".index(p[0])] * V15["012M".index(p[1])] / 100 if p else 0
            e = estimacion.estimar_premios(recaud, eco.get("bote") or 0, V, v15, t)
            res.append((e[14][1], e[15][1] if p else None))
        p14 = sorted(x[0] for x in res)
        med = p14[len(p14) // 2]
        self.txt.delete("4.0", "end")
        nota = " (recaudación aún estimada)" if eco.get("estado") == "ABIERTA" else ""
        self.txt.insert("end", f"Si aciertas una columna, premio estimado de 14 (y de 15 con su pleno), con la recaudación "
                               f"{_eur(recaud)}{nota} y {fuente}:\n"
                               f"  la mitad de tus columnas pagaría más de {_eur(med)} el 14 · "
                               f"la más «popular» {_eur(p14[0])} · la de más valor {_eur(p14[-1])}\n\n")
        for (r, p), (e14, e15) in zip(zip(S, plenos), res):
            marca = "  ← popular" if e14 <= p14[len(p14) // 5] else "  ← mucho valor" if e14 >= p14[-(len(p14) // 5) - 1] else ""
            self.txt.insert("end", "".join(SIGN_CHARS[s] for s in r) + f" {p[0]}-{p[1]}   14: ≈{_eur(e14):>14}"
                            + (f"   15: ≈{_eur(e15):>16}" if e15 is not None else "") + marca + "\n")

    # ------------------------------------------------------------------ guardar
    def guardar(self):
        if self.columns is None:
            return
        os.makedirs(gj.OUT, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, initialdir=gj.OUT, initialfile=f"quiniela_{self.t_cargada}_j{self.j:02d}.txt",
            defaultextension=".txt", filetypes=[("Texto", "*.txt")])
        if not path:
            return
        # mismo formato que los ficheros de eduardolosilla: 14 signos + pleno en goles pegado
        # (p. ej. X12X1211X1111121), sin espacios, fin de línea de Windows
        with open(path, "w", encoding="ascii", newline="") as f:
            for r, p in zip(self.columns, self.plenos or [None] * len(self.columns)):
                f.write("".join(SIGN_CHARS[s] for s in r) + (p if p else "") + "\r\n")
        self.estado.config(text=f"Guardado en {path} (formato de la web, con el pleno al 15 en cada línea)")


APUESTAS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mis_apuestas")
INDICE = os.path.join(APUESTAS_DIR, "historial.json")


def _temp(t):
    return f"{t - 2001:02d}/{t - 2000:02d}"


def _eur(x):
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def cargar_indice():
    try:
        with open(INDICE, encoding="utf-8") as f:
            idx = json.load(f)
    except (OSError, ValueError):
        return {"activa": None, "apuestas": []}
    # si la carpeta se ha copiado a otro sitio u otro PC, los ficheros se buscan junto al historial
    for a in idx.get("apuestas", []):
        if not os.path.exists(a.get("fichero", "")):
            local = os.path.join(APUESTAS_DIR, os.path.basename(a.get("fichero", "")))
            if os.path.exists(local):
                a["fichero"] = local
    return idx


def guardar_indice(idx):
    os.makedirs(APUESTAS_DIR, exist_ok=True)
    tmp = INDICE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    os.replace(tmp, INDICE)


class Principal(tk.Tk):
    """Ventana principal: escrutinio en directo de la apuesta real y su historial."""

    def __init__(self):
        super().__init__()
        self.title("Quiniela · escrutinio")
        poner_icono(self)
        try:
            self.state("zoomed")  # maximizada, para que no la tape la barra de tareas
        except tk.TclError:
            pass
        self.idx = cargar_indice()
        self.filas = []
        self.actual = None        # dict de la apuesta que se ve (del historial o temporal)
        self._auto_id = None
        self.gen = None

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Generar quiniela...", command=self.abrir_generador).pack(side="left")
        ttk.Button(top, text="Cargar fichero de la jornada...", command=self.cargar_fichero).pack(side="left", padx=8)
        ttk.Button(top, text="Actualizar", command=self.actualizar).pack(side="left")
        ttk.Button(top, text="Cerrar boleto", command=self.cerrar_boleto).pack(side="left", padx=8)
        self.var_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto cada 60 s", variable=self.var_auto, command=self._auto).pack(side="left", padx=8)
        self.lbl_fuente = ttk.Label(top, text="", foreground="#555")
        self.lbl_fuente.pack(side="left", padx=8)
        if DONAR_URL:
            tk.Button(top, text="♥ Donar", command=lambda: webbrowser.open(DONAR_URL), bg="#ffc439", fg="#1a202c",
                      relief="flat", font=("Segoe UI", 9, "bold"), padx=10, cursor="hand2").pack(side="right", padx=(4, 8))
        self.lbl_hora = ttk.Label(top, text="", foreground="#2b6cb0", font=("Segoe UI", 9, "bold"))
        self.lbl_hora.pack(side="right", padx=8)
        self.en_juego = {}  # clave -> (cobro estimado ahora, mejor posibilidad) de jornadas sin escrutar

        body = ttk.Frame(self, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)
        hist = ttk.Frame(body)
        hist.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(hist, text="Jornadas jugadas", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.lst = tk.Listbox(hist, width=56, height=28, font=("Consolas", 9), activestyle="none",
                              selectbackground="#2b6cb0")
        self.lst.pack(fill="y", expand=True)
        self.lst.bind("<<ListboxSelect>>", self._sel_historial)
        self.lbl_tot = tk.Label(hist, text="", font=("Segoe UI", 9, "bold"), justify="left", anchor="w")
        self.lbl_tot.pack(fill="x", pady=(6, 0))
        bh = ttk.Frame(hist)
        bh.pack(anchor="w", pady=(6, 0))
        ttk.Button(bh, text="Cambiar nombre", command=self.renombrar).pack(side="left", padx=(0, 6))
        ttk.Button(bh, text="Quitar del historial", command=self.quitar).pack(side="left")

        self.panel = PanelDirecto(body, on_simular=self._simulando)
        self.panel.btn_sim.config(command=self._quitar_sim)
        self.panel.pack(side="left", fill="both", expand=True)
        self.panel.mensaje("Carga el fichero de la jornada para ver su escrutinio.")

        self.pinta_historial()
        activa = self._buscar(self.idx.get("activa"))
        if activa:
            self.ver(activa)
        self.after(500, self.rellenar_historial)

    # ------------------------------------------------------------------ historial
    def _buscar(self, clave):
        return next((a for a in self.idx["apuestas"] if a["clave"] == clave), None) if clave else None

    def _ordenadas(self):
        return sorted(self.idx["apuestas"], key=lambda a: (a["temporada"], a["jornada"], a.get("n", 1)), reverse=True)

    def _boletos(self, t, j):
        return sorted((a for a in self.idx["apuestas"] if a["temporada"] == t and a["jornada"] == j),
                      key=lambda a: a.get("n", 1))

    def _texto_fila(self, a):
        gasto = a["columnas"] * gj.PRECIO
        nombre = f"{_temp(a['temporada'])} J{a['jornada']:<2}"
        if a.get("nombre"):
            nombre += f" {a['nombre'][:14]}"
        elif len(self._boletos(a["temporada"], a["jornada"])) > 1:
            nombre += f" #{a.get('n', 1)}"
        if a.get("cobrado") is not None:
            bal = a["cobrado"] - gasto
            return (f"{nombre} {gasto:6.2f}€ cob {a['cobrado']:8.2f}€ {bal:+8.2f}€"
                    + (" ✔" if a.get("cerrado") else " ·sin cerrar"))
        est = self.en_juego.get(a["clave"])
        return f"{nombre} {gasto:6.2f}€ " + (f"≈ {est[0]:7.2f}€ (máx {est[1]:.0f}€)" if est else "(en juego)")

    def pinta_historial(self):
        self.lst.delete(0, "end")
        jugado = cobrado = 0.0
        self.filas = self._ordenadas()
        for a in self.filas:
            activa = a["clave"] == self.idx.get("activa")
            self.lst.insert("end", ("► " if activa else "  ") + self._texto_fila(a))
            if a.get("cobrado") is not None:
                gasto = a["columnas"] * gj.PRECIO
                self.lst.itemconfig("end", fg="#2f855a" if a["cobrado"] - gasto >= 0 else "#c53030")
                jugado += gasto
                cobrado += a["cobrado"]
        bal = cobrado - jugado
        self.lbl_tot.config(text=f"Jornadas terminadas: jugado {_eur(jugado)}\ncobrado {_eur(cobrado)} · "
                                 f"balance {'+' if bal >= 0 else ''}{_eur(bal)}",
                            fg="#2f855a" if bal >= 0 else "#c53030")
        if self.actual:
            for i, a in enumerate(self.filas):
                if a["clave"] == self.actual.get("clave"):
                    self.lst.selection_clear(0, "end")
                    self.lst.selection_set(i)

    def _sel_historial(self, _e):
        sel = self.lst.curselection()
        if sel:
            self.ver(self.filas[sel[0]])

    def renombrar(self):
        sel = self.lst.curselection()
        if not sel:
            messagebox.showinfo("Nombre", "Selecciona un boleto del historial.", parent=self)
            return
        a = self.filas[sel[0]]
        nuevo = simpledialog.askstring("Nombre del boleto", "Nombre del boleto (vacío = sin nombre):",
                                       initialvalue=a.get("nombre", ""), parent=self)
        if nuevo is None:
            return
        a["nombre"] = nuevo.strip()
        guardar_indice(self.idx)
        self.pinta_historial()
        if self.actual is a:
            self.ver(a)

    def quitar(self):
        sel = self.lst.curselection()
        if not sel:
            return
        a = self.filas[sel[0]]
        if not messagebox.askyesno("Historial", f"¿Quitar este boleto de la jornada {a['jornada']} de la "
                                   f"{_temp(a['temporada'])} del historial?", parent=self):
            return
        self.idx["apuestas"] = [x for x in self.idx["apuestas"] if x["clave"] != a["clave"]]
        if self.idx.get("activa") == a["clave"]:
            self.idx["activa"] = self._ordenadas()[0]["clave"] if self.idx["apuestas"] else None
        guardar_indice(self.idx)
        self.pinta_historial()

    def rellenar_historial(self):
        """Calcula en segundo plano lo cobrado en jornadas ya escrutadas que aún no lo tienen."""
        pend = [a for a in self.idx["apuestas"] if a.get("cobrado") is None]

        def work():
            cambios = False
            for a in pend:
                try:
                    st = estimacion.estado_jornada(a["temporada"], a["jornada"])
                    total, escrutada = estimacion.cobro(st, *leer_columnas(a["fichero"]))
                    if escrutada:
                        a["cobrado"] = round(total, 2)
                        cambios = True
                except Exception:  # noqa: BLE001
                    pass
            if cambios:
                self.after(0, lambda: (guardar_indice(self.idx), self.pinta_historial()))

        if pend:
            threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ cargar fichero real
    def cargar_fichero(self):
        link = simpledialog.askstring(
            "Fichero de la jornada",
            "Pega el link del fichero de apuestas\n(p. ej. https://files.eduardolosilla.es/redus/1X2/2027/14/...txt)\n\n"
            "o déjalo vacío y pulsa Aceptar para elegir un archivo del ordenador:", parent=self)
        if link is None:
            return
        link = link.strip()
        t = j = None
        if link:
            m = re.search(r"/(\d{4})/(\d{1,3})/[^/]*$", link)
            if m:
                t, j = int(m.group(1)), int(m.group(2))
            try:
                req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    datos = r.read().decode("utf-8-sig", errors="replace")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Link", f"No se pudo descargar el fichero:\n{e}", parent=self)
                return
            os.makedirs(os.path.join(APUESTAS_DIR, "descargas"), exist_ok=True)
            path = os.path.join(APUESTAS_DIR, "descargas", os.path.basename(link.split("?")[0]) or "apuesta.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(datos)
        else:
            path = filedialog.askopenfilename(parent=self, initialdir=gj.OUT, title="Fichero de la jornada",
                                              filetypes=[("Texto", "*.txt"), ("Todos", "*.*")])
            if not path:
                return
            sug = re.search(r"_(\d{4})_j(\d+)", os.path.basename(path))
            if sug:
                t, j = int(sug.group(1)), int(sug.group(2))
        try:
            cols, plenos = leer_columnas(path)
        except ValueError as e:
            messagebox.showerror("Archivo", str(e), parent=self)
            return
        res = PedirJornada(self, t, j).resultado
        if not res:
            return
        t, j = res
        con = [p for p in plenos if p]
        resumen = sorted({p: con.count(p) for p in con}.items(), key=lambda x: -x[1])
        pleno = resumen[0][0] if resumen else None
        txt_pleno = ", ".join(f"{p[0]}-{p[1]} ({n})" for p, n in resumen) if resumen else "—"
        aviso = "" if len(con) == len(plenos) else (
            "\n\nOjo: el fichero no trae el pleno al 15." if not con else f"\n\nOjo: {len(plenos) - len(con)} columnas sin pleno.")
        real = messagebox.askyesno(
            "Fichero de apuestas",
            f"{os.path.basename(path)}\nTemporada {_temp(t)} · jornada {j} · {len(cols)} columnas "
            f"({len(cols) * gj.PRECIO:.2f} €)\nPleno al 15: {txt_pleno}{aviso}\n\n"
            "¿Es este el fichero REAL de apuestas?\n\n"
            "Sí: se guarda en el historial y el programa se abrirá siempre con él hasta que cargues el de la "
            "siguiente jornada.\nNo: solo se muestra ahora, sin guardarlo.", parent=self)
        if real:
            os.makedirs(APUESTAS_DIR, exist_ok=True)
            existentes = self._boletos(t, j)
            n, clave = 1, f"{t}_j{j:02d}"
            if existentes:
                ultimo = existentes[-1]
                r = messagebox.askyesnocancel(
                    "Boletos de la jornada",
                    f"Ya tienes {len(existentes)} boleto(s) en la jornada {j}.\n\n"
                    f"Sí: añadir este como otro boleto.\nNo: sustituir el último (#{ultimo.get('n', 1)}).\n"
                    "Cancelar: no guardar nada.", parent=self)
                if r is None:
                    return
                if r:
                    n = max(b.get("n", 1) for b in existentes) + 1
                    clave = f"{t}_j{j:02d}_{n}"
                else:
                    n, clave = ultimo.get("n", 1), ultimo["clave"]
            previo = (self._buscar(clave) or {}).get("nombre", "")
            nombre_b = simpledialog.askstring("Nombre del boleto", "Ponle un nombre a este boleto (opcional):",
                                              initialvalue=previo, parent=self)
            destino = os.path.join(APUESTAS_DIR, f"apuesta_{clave}.txt")
            with open(destino, "w", encoding="utf-8") as f:
                for c, p in zip(cols, plenos):
                    f.write(c + (f" {p[0]}-{p[1]}" if p else "") + "\n")
            a = dict(clave=clave, n=n, nombre=(nombre_b or "").strip(), temporada=t, jornada=j, fichero=destino,
                     origen=link or path, columnas=len(cols), pleno=pleno, cobrado=None)
            self.idx["apuestas"] = [x for x in self.idx["apuestas"] if x["clave"] != clave] + [a]
            self.idx["activa"] = clave
            guardar_indice(self.idx)
            self.pinta_historial()
        else:
            a = dict(clave=None, temporada=t, jornada=j, fichero=path, columnas=len(cols), pleno=pleno)
        self.ver(a)

    # ------------------------------------------------------------------ ver / actualizar
    def ver(self, a):
        if a is not self.actual:
            self.panel.sim, self.panel.sim15 = {}, None
            self.panel.btn_sim.pack_forget()
        self.actual = a
        if a.get("clave"):
            nombre = "boleto cerrado" if a.get("cerrado") else "apuesta real"
            if a.get("nombre"):
                nombre = f"{a['nombre']} · {nombre}"
            elif len(self._boletos(a["temporada"], a["jornada"])) > 1:
                nombre = f"boleto #{a.get('n', 1)} · {nombre}"
        else:
            nombre = os.path.basename(a["fichero"]) + " (solo ver)"
        self.lbl_fuente.config(text=f"{_temp(a['temporada'])} · J{a['jornada']} · {nombre}")
        self.pinta_historial()
        self.actualizar()
        self._auto()

    def actualizar(self):
        a = self.actual
        if not a:
            return
        try:
            cols, plenos = leer_columnas(a["fichero"])
        except (OSError, ValueError) as e:
            self.panel.mensaje(f"No puedo leer el fichero: {e}")
            return

        def work():
            try:
                st = estimacion.estado_jornada(a["temporada"], a["jornada"])
                self.after(0, lambda: self._pinta(a, st, cols, plenos))
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda e=e: self.panel.mensaje(f"No se pudo actualizar: {e}"))

        self.lbl_hora.config(text="Actualizando premios y resultados...")
        threading.Thread(target=work, daemon=True).start()

    def _pinta(self, a, st, cols, plenos):
        import datetime as _dt
        if a is not self.actual:
            return
        hora = f"{_dt.datetime.now():%H:%M:%S}"
        total, escrutada = self.panel.render(st, cols, plenos, hora)
        self.lbl_hora.config(text=f"Actualizado a las {hora}" + (" · con simulación" if self.panel.simulando else ""))
        if a.get("clave") and escrutada and not a.get("cerrado") and a.get("cobrado") != round(total, 2):
            a["cobrado"] = round(total, 2)
            guardar_indice(self.idx)
        if a.get("clave") and not escrutada and not self.panel.simulando:
            # importe estimado en el historial: lo que se cobraría ahora y lo máximo posible
            self.en_juego[a["clave"]] = (total, estimacion.mejor_caso(st, cols, plenos)[0])
        self.pinta_historial()

    def _quitar_sim(self):
        self.panel.quitar_simulacion()
        self.lbl_hora.config(text="Sin simulación · marca «Auto cada 60 s» para volver a refrescar solo")

    def _simulando(self):
        """Al simular se para el refresco automático, para que no borre la simulación."""
        if self.var_auto.get():
            self.var_auto.set(False)
            self._auto()
        self.lbl_hora.config(text="Simulando · refresco automático parado")

    def _auto(self):
        if self._auto_id:
            self.after_cancel(self._auto_id)
            self._auto_id = None
        if self.var_auto.get() and self.actual:
            self._auto_id = self.after(60000, lambda: (self.actualizar(), self._auto()))

    def cerrar_boleto(self):
        """Cuando la jornada está escrutada: guarda definitivamente los premios reales del boleto."""
        a = self.actual
        if not a or not a.get("clave"):
            messagebox.showinfo("Cerrar boleto", "Selecciona una apuesta real del historial.", parent=self)
            return
        if a.get("cerrado"):
            messagebox.showinfo("Cerrar boleto", f"Este boleto ya está cerrado: cobrado {_eur(a['cobrado'])}.", parent=self)
            return
        boletos = [a]

        def work():
            try:
                st = estimacion.estado_jornada(a["temporada"], a["jornada"])
                dets = None
                if st["estado"] == "ESCRUTADA":
                    dets = [estimacion.detalle_real(st, *leer_columnas(b["fichero"])) for b in boletos]
                res = (st, dets)
            except Exception as e:  # noqa: BLE001
                res = (None, e)
            self.after(0, lambda: self._cerrar(a, boletos, *res))

        threading.Thread(target=work, daemon=True).start()

    def _cerrar(self, a, boletos, st, dets):
        import datetime as _dt
        if st is None:
            messagebox.showerror("Cerrar boleto", f"No se pudo consultar la jornada: {dets}", parent=self)
            return
        if dets is None:
            messagebox.showinfo("Cerrar boleto", f"La jornada {a['jornada']} aún no está escrutada (estado: {st['estado']}).\n"
                                "Los premios reales se publican al terminar; vuelve a pulsar entonces.", parent=self)
            return
        signos, goles15 = dets[0][2], dets[0][3]
        partes = []
        for b, (detalle, total, _s, _g) in zip(boletos, dets):
            cab = f"{b.get('nombre') or 'Boleto #' + str(b.get('n', 1))}: {_eur(total)}\n" if len(boletos) > 1 else ""
            lineas = "\n".join(f"  {('15 (pleno)' if c == 15 else str(c)) + ' aciertos':<18} {n:>3} col. × {_eur(p)} = {_eur(n * p)}"
                               for c, (n, p) in sorted(detalle.items(), reverse=True)) or "  Ningún premio."
            partes.append(cab + lineas)
        total = round(sum(d[1] for d in dets), 2)
        gasto = sum(b["columnas"] for b in boletos) * gj.PRECIO
        if not messagebox.askyesno(
                "Cerrar boleto",
                f"{_temp(a['temporada'])} · jornada {a['jornada']} · escrutada\nResultado: {signos}  pleno {goles15[:1]}-{goles15[1:]}\n\n"
                + "\n\n".join(partes) +
                f"\n\nCOBRADO: {_eur(total)}   (gasto {_eur(gasto)}, balance {'+' if total >= gasto else ''}{_eur(total - gasto)})\n\n"
                "¿Guardar definitivamente?", parent=self):
            return
        for b, (detalle, tot, _s, _g) in zip(boletos, dets):
            b.update(cobrado=tot, cerrado=True, fecha_cierre=f"{_dt.datetime.now():%Y-%m-%d %H:%M}", resultado=signos,
                     pleno_resultado=goles15, premios={str(c): [n, p] for c, (n, p) in detalle.items()})
        guardar_indice(self.idx)
        self.pinta_historial()
        self.lbl_fuente.config(text=self.lbl_fuente.cget("text").replace("apuesta real", "boleto cerrado"))

    def abrir_generador(self):
        if self.gen is not None and self.gen.winfo_exists():
            self.gen.lift()
            return
        self.gen = Generador(self)


class PedirJornada(tk.Toplevel):
    """Dialogo para confirmar temporada y jornada del fichero."""

    def __init__(self, master, t, j):
        super().__init__(master)
        self.title("¿De qué jornada es?")
        self.resultado = None
        self.transient(master)
        ttk.Label(self, text="Temporada:").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        actual = gj.temporada_actual()
        self.temps = {_temp(y): y for y in range(actual, 2004, -1)}
        self.cb = ttk.Combobox(self, values=list(self.temps), width=7, state="readonly")
        self.cb.set(_temp(t) if t else _temp(actual))
        self.cb.grid(row=0, column=1, padx=8, sticky="w")
        ttk.Label(self, text="Jornada:").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        self.ent = ttk.Entry(self, width=6)
        self.ent.insert(0, str(j or ""))
        self.ent.grid(row=1, column=1, padx=8, sticky="w")
        ttk.Button(self, text="Aceptar", command=self._ok).grid(row=2, column=0, columnspan=2, pady=8)
        self.ent.focus_set()
        self.bind("<Return>", lambda _e: self._ok())
        self.grab_set()
        self.wait_window()

    def _ok(self):
        if not self.ent.get().strip().isdigit():
            messagebox.showerror("Jornada", "Escribe el número de jornada.", parent=self)
            return
        self.resultado = (self.temps[self.cb.get()], int(self.ent.get()))
        self.destroy()


def leer_columnas(path):
    """Lee columnas: 14 signos por linea, opcionalmente seguidos del pleno ('1-1', 'M2'...)."""
    cols, plenos = [], []
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            s = line.strip().upper().replace("\t", " ")
            if not s:
                continue
            # 14 signos y, opcional, el pleno en goles: "...1X2 1-1", "...1X2 11" o pegado "...1X211"
            m = re.fullmatch(r"([1X2]{14})(?:[\s;,]*([012M])\s*-?\s*([012M]))?", s)
            if not m:
                raise ValueError(f"Línea {n} no válida: «{line.strip()}»\nCada línea debe tener 14 signos 1/X/2.")
            cols.append(m.group(1))
            plenos.append(m.group(2) + m.group(3) if m.group(2) else None)
    if not cols:
        raise ValueError("El archivo no tiene columnas.")
    return cols, plenos


def escrutinio(esc, cols, plenos, pleno_ui, nombre):
    partidos = {int(p["num"]): p for p in esc.get("partidos", [])}
    signos = [(partidos.get(n) or {}).get("signo") or "" for n in range(1, 15)]
    p15 = partidos.get(15) or {}
    goles15 = (p15.get("signo_goles") or "").upper()
    jugados = [s in ("1", "X", "2") for s in signos]
    n_jug = sum(jugados)
    escrutada = esc.get("estado") == "ESCRUTADA"
    premios = {int(a["acierto"]): float(a.get("premio") or 0) for a in esc.get("acertantes") or []}

    filas, total, cuenta = [], 0.0, {}
    for c, pl in zip(cols, plenos):
        ac = sum(1 for i in range(14) if jugados[i] and c[i] == signos[i])
        pl = pl or pleno_ui
        cat = ac
        if ac == 14 and len(goles15) == 2 and pl == goles15:
            cat = 15
        pr = premios.get(cat, 0.0) if (escrutada and cat >= 10) else 0.0
        total += pr
        cuenta[cat] = cuenta.get(cat, 0) + 1
        filas.append((c, ac, cat, pr))

    out = [f"Archivo: {nombre}  ({len(cols)} columnas, {len(cols) * gj.PRECIO:.2f} €)",
           f"Estado de la jornada: {esc.get('estado', '?')}  ·  partidos con resultado: {n_jug} de 14", "",
           "Resultados:"]
    for n in range(1, 15):
        p = partidos.get(n) or {}
        out.append(f"  {n:>2}. {p.get('local', ''):<18} - {p.get('visitante', ''):<18} "
                   f"{p.get('resultado') or '':>5}  {signos[n - 1] or '·'}")
    out.append(f"  15. {p15.get('local', ''):<18} - {p15.get('visitante', ''):<18} "
               f"{p15.get('resultado') or '':>5}  {goles15 or '·'}")
    out += ["", "Columnas por aciertos:"]
    for cat in sorted(cuenta, reverse=True):
        nombre_cat = "15 (pleno)" if cat == 15 else str(cat)
        pr = premios.get(cat) if escrutada and cat >= 10 else None
        extra = f"  x {pr:,.2f} € = {pr * cuenta[cat]:,.2f} €" if pr else ""
        if escrutada and cat >= 10 and not pr:
            extra = "  (premio 0 €: categoría sin premio publicado, consulta el escrutinio oficial)"
        out.append(f"  {nombre_cat:>10} aciertos: {cuenta[cat]:>4} columnas{extra}")
    if escrutada:
        gasto = len(cols) * gj.PRECIO
        out += ["", f"PREMIO TOTAL: {total:,.2f} €   (gasto {gasto:.2f} €, balance {total - gasto:+,.2f} €)"]
    else:
        out += ["", "La jornada aún no está escrutada: los premios todavía no se conocen.",
                f"Máximo de aciertos posible de tu mejor columna: "
                f"{max(a for _, a, _, _ in filas) + (14 - n_jug)}"]
    out += ["", "Mejores columnas:"]
    for c, ac, cat, pr in sorted(filas, key=lambda x: -x[1])[:10]:
        fallos = "".join("^" if jugados[i] and ch != signos[i] else " " for i, ch in enumerate(c))
        out.append(f"  {c}  {ac} aciertos" + (f"  {pr:,.2f} €" if pr else ""))
        if fallos.strip():
            out.append(f"  {fallos}")
    out.append("  (^ = signo fallado)")
    return "\n".join(out)


def mostrar(parent, titulo, texto):
    w = tk.Toplevel(parent)
    w.title(titulo)
    t = tk.Text(w, width=90, height=40, font=("Consolas", 10))
    t.pack(fill="both", expand=True)
    t.insert("1.0", texto)
    t.config(state="disabled")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:   # para que la barra de tareas de Windows muestre el icono del programa y no el de Python
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("quinielas.programa")
    except (AttributeError, OSError):
        pass
    try:
        Principal().mainloop()
    except Exception:  # noqa: BLE001  con pythonw no hay consola: deja el error a la vista
        import traceback
        err = traceback.format_exc()
        with open("quiniela_app_error.log", "w", encoding="utf-8") as f:
            f.write(err)
        messagebox.showerror("Quiniela", "No se pudo abrir el programa:\n\n" + err)
