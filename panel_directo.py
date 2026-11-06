"""Panel grafico 'Directo y premios' para quiniela_app.

Por cada partido: % de tus columnas con 1 / X / 2 (celdas coloreadas), marcador actual y % de tus
columnas que aciertan el signo que va saliendo. Debajo: barras con cuantas columnas llevan cada
numero de aciertos, y tabla de premios (estimados con el metodo de la web, o reales si ya esta
escrutada) con lo que cobrarias.
"""
import math
import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import estimacion

FONT = ("Segoe UI", 9)
BOLD = ("Segoe UI", 9, "bold")
BLUE = (43, 108, 176)
GREEN, ORANGE, RED, GRAY = "#2f855a", "#dd6b20", "#c53030", "#a0aec0"
PURPLE = "#805ad5"
N_APUESTAS = 15   # apuestas que se ven a la vez en la rejilla


def _mix(pct):
    """Blanco -> azul segun el %."""
    a = max(0.0, min(1.0, pct / 100.0))
    r, g, b = (int(255 + (c - 255) * a) for c in BLUE)
    return f"#{r:02x}{g:02x}{b:02x}"


def _eur(x):
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _int(x):
    return f"{int(x):,}".replace(",", ".")


class PanelDirecto(ttk.Frame):
    def __init__(self, master, on_simular=None, interactivo=True, titulo=""):
        super().__init__(master)
        self.interactivo = interactivo
        self.titulo = titulo
        self.on_simular = on_simular   # se llama cuando se empieza a simular resultados
        self.sim = {}                  # partido (0-13) -> (signo, marcador) simulados
        self.sim15 = None              # goles del pleno simulados, p. ej. "21"
        self._datos = None             # (st, cols, pleno, hora) de la ultima actualizacion real
        cab = ttk.Frame(self)
        cab.pack(fill="x")
        self.lbl_cab = ttk.Label(cab, text="", font=BOLD)
        self.lbl_cab.pack(side="left")
        self.btn_sim = ttk.Button(cab, text="Quitar simulación", command=self.quitar_simulacion)
        self.lbl_ayuda = ttk.Label(self, text=("Para simular: toca un 1/X/2 o la casilla ✎ de «Simular» "
                                               "(el marcador real no cambia)." if interactivo else
                                               "Resultados reales."),
                                   foreground="#805ad5" if interactivo else "#555", font=("Segoe UI", 8))
        self.lbl_ayuda.pack(anchor="w")
        self.lbl_sub = ttk.Label(self, text="", foreground="#555")
        self.lbl_sub.pack(anchor="w", pady=(0, 4))

        self.grid_f = tk.Frame(self, bg="white", highlightthickness=1, highlightbackground="#cbd5e0")
        self.grid_f.pack(fill="x")
        heads = ["#", "Partido", "1", "X", "2", "Marcador", "", "Aciertan", "Simular"]
        for c, h in enumerate(heads):
            tk.Label(self.grid_f, text=h, font=BOLD, bg="#edf2f7").grid(row=0, column=c, sticky="nsew", padx=1, pady=1)
        self.cells = []
        self.fila_sel = None
        for i in range(15):
            row = []
            row.append(tk.Label(self.grid_f, text=str(i + 1), font=FONT, bg="white", width=2))
            row.append(tk.Label(self.grid_f, text="", font=FONT, bg="white", anchor="w", width=22))
            for _ in range(3):
                row.append(tk.Label(self.grid_f, text="", font=FONT, width=5, bg="white", bd=0, relief="flat"))
            row.append(tk.Label(self.grid_f, text="", font=BOLD, bg="white", width=6))
            row.append(tk.Label(self.grid_f, text="", font=("Segoe UI", 8), bg="white", width=9, fg="#555"))
            row.append(tk.Label(self.grid_f, text="", font=BOLD, bg="white", width=7))
            row.append(tk.Label(self.grid_f, text="", font=BOLD, bg="#faf5ff", fg=PURPLE, width=8))
            for c, w in enumerate(row):
                w.grid(row=i + 1, column=c, sticky="nsew", padx=1, pady=1)
            if interactivo:
                for k in range(3):
                    row[2 + k].bind("<Button-1>", lambda _e, i=i, k=k: self._tocar_signo(i, k))
                row[8].bind("<Button-1>", lambda _e, i=i: self._tocar_marcador(i))
                for w in row[2:5] + [row[8]]:
                    w.config(cursor="hand2")
            self.cells.append(row)
        self._crear_apuestas()

        self.lbl_graf = ttk.Label(self, text="Aciertos de tus columnas", font=BOLD)
        self.lbl_graf.pack(anchor="w", pady=(8, 0))
        self.canvas = tk.Canvas(self, height=130, bg="white", highlightthickness=1, highlightbackground="#cbd5e0")
        self.canvas.pack(fill="x")
        self.lbl_mejor = ttk.Label(self, text="", font=BOLD)
        self.lbl_mejor.pack(anchor="w", pady=(4, 0))

        ttk.Label(self, text="Premios", font=BOLD).pack(anchor="w", pady=(8, 0))
        self.prem_f = tk.Frame(self, bg="white", highlightthickness=1, highlightbackground="#cbd5e0")
        self.prem_f.pack(fill="x")
        self.prem_heads = ["Aciertos", "Acertantes", "Premio", "Tus columnas", "Cobras"]
        self.lbl_heads = []
        pos = (0, 1, 2, 4, 5)                  # la columna 3 es el premio máximo
        for c, h in zip(pos, self.prem_heads):
            w = tk.Label(self.prem_f, text=h, font=BOLD, bg="#edf2f7")
            w.grid(row=0, column=c, sticky="nsew", padx=1, pady=1)
            self.lbl_heads.append(w)
        self.lbl_max = tk.Label(self.prem_f, text="", font=BOLD, bg="#edf2f7", width=14)
        self.lbl_max.grid(row=0, column=3, sticky="nsew", padx=1, pady=1)
        self.prem, self.prem_max = [], {}
        for r, cat in enumerate((15, 14, 13, 12, 11, 10)):
            row = [tk.Label(self.prem_f, text="15 (pleno)" if cat == 15 else str(cat), font=FONT, bg="white", width=9)]
            row += [tk.Label(self.prem_f, text="", font=FONT, bg="white", width=w, anchor="e") for w in (11, 13, 11, 12)]
            for c, w in zip(pos, row):
                w.grid(row=r + 1, column=c, sticky="nsew", padx=1, pady=1)
            maxi = tk.Label(self.prem_f, text="", font=FONT, bg="white", anchor="e", width=14)
            maxi.grid(row=r + 1, column=3, sticky="nsew", padx=1, pady=1)
            self.prem_max[cat] = maxi
            self.prem.append((cat, row))
        self.lbl_total = tk.Label(self, text="", font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_total.pack(fill="x", pady=(6, 0))
        self.lbl_ahora = tk.Label(self, text="", font=FONT, fg="#4a5568", anchor="w", justify="left", wraplength=600)
        self.lbl_ahora.pack(fill="x")
        self.lbl_pleno = tk.Label(self, text="", font=BOLD, fg=RED, anchor="w", justify="left", wraplength=600)
        self.lbl_pleno.pack(fill="x")
        self.lbl_nota = ttk.Label(self, text="", foreground="#777", wraplength=600, font=("Segoe UI", 8))
        self.lbl_nota.pack(anchor="w", pady=(2, 0))

    # ------------------------------------------------------------------
    def mensaje(self, txt):
        self.lbl_cab.config(text=txt)

    # ------------------------------------------------------------------ apuestas ordenadas por aciertos
    def _crear_apuestas(self):
        """Rejilla junto a los partidos: cada columna vertical es una apuesta, las mejores primero."""
        self.ap_pag, self.ap_datos = 0, None
        col0 = 9
        nav = tk.Frame(self.grid_f, bg="#edf2f7")
        nav.grid(row=0, column=col0, columnspan=N_APUESTAS, sticky="nsew", padx=(10, 1), pady=1)
        izq = tk.Label(nav, text=" ‹ ", font=BOLD, bg="#edf2f7", fg=RED, cursor="hand2")
        izq.pack(side="left")
        izq.bind("<Button-1>", lambda _e: self._pagina(-1))
        der = tk.Label(nav, text=" › ", font=BOLD, bg="#edf2f7", fg=RED, cursor="hand2")
        der.pack(side="right")
        der.bind("<Button-1>", lambda _e: self._pagina(1))
        self.lbl_ap = tk.Label(nav, text="Apuestas", font=BOLD, bg="#edf2f7")
        self.lbl_ap.pack(side="left", expand=True)
        self.ap_cells, self.ap_cnt = [], []
        for i, row in enumerate(self.cells):
            for k in (0, 1, 5, 6, 7):
                row[k].bind("<Button-1>", lambda _e, i=i: self._marcar(i))
                row[k].config(cursor="hand2")
        for c in range(N_APUESTAS):
            pad = (10, 0) if c == 0 else 0
            fila = []
            for r in range(15):
                w = tk.Label(self.grid_f, text="", font=("Consolas", 9, "bold"), bg="white", width=3, cursor="hand2")
                w.grid(row=r + 1, column=col0 + c, sticky="nsew", padx=pad)
                w.bind("<Button-1>", lambda _e, r=r: self._marcar(r))
                fila.append(w)
            self.ap_cells.append(fila)
            w = tk.Label(self.grid_f, text="", font=BOLD, bg="#edf2f7", width=3)
            w.grid(row=16, column=col0 + c, sticky="nsew", padx=pad, pady=(2, 0))
            self.ap_cnt.append(w)

    def _marcar(self, i):
        """Toca una fila para marcarla (también sus apuestas); tocarla otra vez la desmarca."""
        anterior, self.fila_sel = self.fila_sel, None if self.fila_sel == i else i
        for n in {anterior, self.fila_sel} - {None}:
            bg = "#90cdf4" if n == self.fila_sel else "white"
            for k in (0, 1, 5, 6, 7):
                self.cells[n][k].config(bg=bg)
            for c in range(N_APUESTAS):
                self.ap_cells[c][n].config(bg=bg)

    def _pagina(self, paso):
        if self.ap_datos:
            self.ap_pag += paso
            self._pinta_apuestas()

    def _pinta_apuestas(self):
        cols, plist, signos, jugados, goles15, aciertos = self.ap_datos
        orden = sorted(range(len(cols)), key=lambda i: -aciertos[i])
        pags = max(1, math.ceil(len(cols) / N_APUESTAS))
        self.ap_pag = max(0, min(self.ap_pag, pags - 1))
        ini = self.ap_pag * N_APUESTAS
        trozo = orden[ini:ini + N_APUESTAS]
        self.lbl_ap.config(text=f"Apuestas {ini + 1}-{ini + len(trozo)} de {len(cols)}" if cols else "Apuestas")
        for c in range(N_APUESTAS):
            i = trozo[c] if c < len(trozo) else None
            for r in range(14):
                s = cols[i][r] if i is not None else ""
                color = "black" if i is None or not jugados[r] else GREEN if s == signos[r] else RED
                self.ap_cells[c][r].config(text=s, fg=color)
            q = plist[i] if i is not None else None
            color = "black" if len(goles15) != 2 or not q else GREEN if q == goles15 else RED
            self.ap_cells[c][14].config(text=f"{q[0]}-{q[1]}" if q else ("-" if i is not None else ""), fg=color,
                                        font=("Consolas", 7, "bold"))
            self.ap_cnt[c].config(text=str(aciertos[i]) if i is not None else "")

    # ------------------------------------------------------------------ simulacion
    @property
    def simulando(self):
        return bool(self.sim) or self.sim15 is not None

    def _empezar(self):
        if self.on_simular:
            self.on_simular()

    def _tocar_signo(self, i, k):
        if not self._datos or i == 14:
            if i == 14:
                self._tocar_marcador(14)
            return
        s = "1X2"[k]
        if self.sim.get(i, (None,))[0] == s:
            del self.sim[i]                      # tocar otra vez el mismo signo lo quita
        else:
            self.sim[i] = (s, "")
        self._empezar()
        self._repintar()

    def _tocar_marcador(self, i):
        if not self._datos:
            return
        f = self._datos[0]["filas"][i]
        txt = simpledialog.askstring(
            "Simular resultado", f"{f['local']} - {f['visitante']}\nMarcador (p. ej. 2-1, 0-0, M-1). "
            "Vacío = quitar la simulación de este partido:", parent=self)
        if txt is None:
            return
        txt = txt.strip().upper().replace(" ", "")
        if not txt:
            self.sim.pop(i, None)
            if i == 14:
                self.sim15 = None
            self._repintar()
            return
        m = re.fullmatch(r"(\d+|M)-(\d+|M)", txt)
        if not m:
            messagebox.showerror("Simular", "Escribe el marcador como 2-1.", parent=self)
            return
        a, b = m.group(1), m.group(2)
        if i == 14:
            g = lambda x: "M" if x == "M" or int(x) >= 3 else x
            self.sim15 = g(a) + g(b)
        else:
            na = 99 if a == "M" else int(a)
            nb = 99 if b == "M" else int(b)
            self.sim[i] = ("1" if na > nb else "X" if na == nb else "2", f"{a}-{b}")
        self._empezar()
        self._repintar()

    def quitar_simulacion(self):
        self.sim, self.sim15 = {}, None
        self._repintar()

    def _repintar(self):
        if self._datos:
            st, cols, pleno, hora = self._datos
            self._render(self._aplicar(st), cols, pleno, hora)
        if self.simulando:
            self.btn_sim.pack(side="left", padx=8)
        else:
            self.btn_sim.pack_forget()

    def _aplicar(self, st):
        if not self.simulando:
            return st
        filas = [dict(f) for f in st["filas"]]
        # el marcador real no se toca: solo cambia el signo que cuenta y se anota lo simulado aparte
        for i, (s, marc) in self.sim.items():
            filas[i].update(signo=s, sim=marc or s)
        if self.sim15 is not None:
            filas[14].update(goles=self.sim15, sim=f"{self.sim15[0]}-{self.sim15[1]}")
        return dict(st, filas=filas, estado=st["estado"] + " · CON SIMULACIÓN", simulacion=True, premios_reales={})

    def render(self, st, cols, pleno, hora):
        """Pinta la jornada; si hay resultados simulados se aplican encima de los reales."""
        self._datos = (st, cols, pleno, hora)
        total, escrutada = self._render(self._aplicar(st), cols, pleno, hora)
        if self.simulando:
            self.btn_sim.pack(side="left", padx=8)
        return total, escrutada

    def _render(self, st, cols, pleno, hora):
        """pleno: lista con el pleno de cada columna ('21', '00'... o None), o uno solo para todas."""
        plist = list(pleno) if isinstance(pleno, (list, tuple)) else [pleno] * len(cols)
        con_pleno = [p for p in plist if p]
        resumen = sorted({p: con_pleno.count(p) for p in con_pleno}.items(), key=lambda x: -x[1])
        filas = st["filas"]
        signos = [f["signo"] for f in filas[:14]]
        jugados = [s in ("1", "X", "2") for s in signos]
        n_jug = sum(jugados)
        en_directo = [(not f["fin"]) and f["marcador"] != "-" for f in filas]
        ncol = len(cols)
        temp = f"{st['temporada'] - 2001:02d}/{st['temporada'] - 2000:02d}"
        self.lbl_cab.config(text=(f"{self.titulo} · " if self.titulo else "") + f"Temporada {temp} · Jornada {st['jornada']} · {st['estado']}"
                                 + ("  ● EN DIRECTO" if st["directo"] else ""),
                            foreground=PURPLE if st.get("simulacion") else "black")
        self.lbl_sub.config(text=f"{ncol} columnas · {n_jug}/14 partidos con resultado · "
                                 f"recaudación {_eur(st['recaudacion'])}")

        for i, f in enumerate(filas):
            row = self.cells[i]
            row[1].config(text=f"{f['local'][:12]} - {f['visitante'][:12]}")
            if i < 14:
                pct = [100.0 * sum(1 for c in cols if c[i] == s) / ncol if ncol else 0.0 for s in "1X2"]
                for k, s in enumerate("1X2"):
                    cell = row[2 + k]
                    es_res = signos[i] == s
                    cell.config(text=f"{pct[k]:.0f}%" if ncol else s, bg=_mix(pct[k]) if ncol else "white",
                                fg="white" if pct[k] > 55 else "black",
                                relief="solid" if es_res else "flat", bd=2 if es_res else 0,
                                highlightthickness=0)
                if jugados[i] and ncol:
                    ac = pct["1X2".index(signos[i])]
                    color = GREEN if ac >= 50 else ORANGE if ac >= 20 else RED
                    row[7].config(text=f"{ac:.0f}%", fg=color)
                else:
                    row[7].config(text="", fg="black")
            else:
                for k in range(3):
                    row[2 + k].config(text="", bg="white", relief="flat", bd=0)
                g = f["goles"]
                if resumen:
                    top = resumen[0][0]
                    row[2].config(text=f"{top[0]}-{top[1]}" + ("…" if len(resumen) > 1 else ""), fg="black")
                    n_ok = sum(1 for q in plist if q and q == g) if len(g) == 2 else 0
                    row[7].config(text=(f"✔ {n_ok}" if n_ok else "✘") if len(g) == 2 else "", fg=GREEN if n_ok else RED)
                else:
                    row[2].config(text="sin pleno", fg=RED)
                    row[7].config(text="", fg="black")
            row[5].config(text=f["marcador"] if f["marcador"] != "-" else "",
                          fg=ORANGE if en_directo[i] else "black")
            row[6].config(text=f["minuto"], fg=ORANGE if en_directo[i] else "#555")
            if self.interactivo:
                row[8].config(text=f.get("sim") or "✎", fg=PURPLE if f.get("sim") else "#d6bcfa")

        # aciertos por columna
        goles15 = filas[14]["goles"]
        aciertos = [sum(1 for i in range(14) if jugados[i] and c[i] == signos[i]) for c in cols]
        self.ap_datos = (cols, plist, signos, jugados, goles15, aciertos)
        self._pinta_apuestas()
        # como en eduardolosilla: los partidos que faltan cuentan como acertados
        pendientes = 14 - n_jug
        pleno_pendiente = len(goles15) != 2
        hist = [0] * 16                       # posición 15: 14 aciertos + pleno al 15
        for a, q in zip(aciertos, plist):
            posible = a + pendientes
            if posible == 14 and q and (pleno_pendiente or q == goles15):
                posible = 15
            hist[posible] += 1
        self.lbl_graf.config(text="Aciertos de tus columnas" + (
            f" (posibles: {'el partido que falta cuenta como acertado' if pendientes == 1 else f'los {pendientes} partidos que faltan cuentan como acertados'})"
            if pendientes else ""))
        self._barras(hist)
        mejor = max(aciertos) if aciertos else 0
        media = sum(aciertos) / len(aciertos) if aciertos else 0
        pct = 100 * media / n_jug if n_jug else 0
        self.lbl_mejor.config(text=(f"Llevas un {pct:.0f} % de aciertos (media {media:.1f} de {n_jug}) · "
                                    f"mejor columna {mejor} de {n_jug} · puede llegar a {mejor + 14 - n_jug}")
                              if cols else "Sin columnas: genera o usa un archivo")

        # premios
        est = estimacion.estimar_desde_estado(st)
        escrutada = st["estado"] == "ESCRUTADA"
        est_max = None if escrutada else estimacion.estimar_desde_estado(st, "max")
        reales = st["premios_reales"]
        total = 0.0
        for cat, row in self.prem:
            if escrutada and cat in reales:
                na, pe = reales[cat][0] or 0, reales[cat][1]
            else:
                na, pe = est[cat]
            con15 = sum(1 for a, q in zip(aciertos, plist) if a == 14 and q and goles15 == q)
            if cat == 15:
                mias = con15
            elif cat == 14:
                mias = sum(1 for a in aciertos if a == 14) - con15
            else:
                mias = sum(1 for a in aciertos if a == cat)
            cobro = mias * pe
            total += cobro
            # con partidos por jugar, las columnas son las posibles (como la gráfica); lo que se
            # cobraría no se suma aquí porque no pueden salir todas a la vez: va en "Mejor posibilidad"
            ver = hist[cat] if pendientes or pleno_pendiente else mias
            hl = "#f0fff4" if ver else "white"
            vals = [_int(na), _eur(pe), str(ver) if ver else "",
                    "" if pendientes or pleno_pendiente or not mias else _eur(cobro)]
            for w, v in zip(row[1:], vals):
                w.config(text=v, bg=hl, font=BOLD if ver else FONT)
            row[0].config(bg=hl)
            self.prem_max[cat].config(text=_eur(est_max[cat][1]) if est_max else "", bg=hl)
        self.lbl_heads[2].config(text="Premio" if escrutada else "Premio mín.")
        self.lbl_max.config(text="" if escrutada else "Premio máx.")
        self.lbl_heads[3].config(text="Posibles" if pendientes or pleno_pendiente else "Tus columnas")
        gasto = ncol * 0.75
        bal = total - gasto
        if escrutada:
            self.lbl_total.config(text=f"Cobras: {_eur(total)}   (balance {'+' if bal >= 0 else ''}{_eur(bal)})",
                                  fg=GREEN if bal >= 0 else RED)
            self.lbl_ahora.config(text="")
        else:
            mt, mcol, mac, npend = estimacion.mejor_caso(st, cols, plist)
            mbal = mt - gasto
            etq = "Con la simulación, mejor posibilidad" if st.get("simulacion") else "Mejor posibilidad"
            self.lbl_total.config(
                text=f"{etq}: {_eur(mt)}   (balance {'+' if mbal >= 0 else ''}{_eur(mbal)})",
                fg=GREEN if mbal >= 0 else RED)
            detalle = (f"Si {'el partido que falta sale' if npend == 1 else f'los {npend} partidos que faltan salen'} como tu columna nº {mcol + 1} "
                       f"({cols[mcol]}): {mac} aciertos. " if mcol is not None and npend else "")
            self.lbl_ahora.config(text=detalle + f"Con lo que va hasta ahora (lo que falta, fallado): {_eur(total)}.")
        self.prem_heads_lbl = "reales" if escrutada else "estimados"
        self.lbl_nota.config(text=(f"Premios {'reales del escrutinio' if escrutada else 'estimados con el método de la web (aproximados)'}. "
                                   "Celdas: % de tus columnas con cada signo; recuadro = signo que va saliendo; "
                                   "naranja = partido en juego. "
                                   f"Actualizado {hora}."))
        if not resumen:
            self.lbl_pleno.config(text="El fichero no trae el pleno al 15: no se puede calcular el pleno al 15.", fg=RED)
        else:
            sin = len(plist) - len(con_pleno)
            txt = "Plenos al 15 jugados: " + ", ".join(f"{q[0]}-{q[1]} en {n} col." for q, n in resumen)
            self.lbl_pleno.config(text=txt + (f" · {sin} columnas sin pleno" if sin else ""), fg=RED if sin else "#2d3748")
        return total, escrutada

    def _barras(self, hist):
        """hist[0..14] = columnas con k aciertos; hist[15] = 14 aciertos + pleno al 15."""
        cv = self.canvas
        cv.delete("all")
        cv.update_idletasks()
        W = max(cv.winfo_width(), 460)
        H = 130
        n = len(hist)
        bw = (W - 20) / n
        top = max(hist) or 1
        for k, v in enumerate(hist):
            x0 = 10 + k * bw
            h = (H - 38) * v / top
            es15 = k == 15
            color = GOLD if es15 else GREEN if k >= 10 else BLUE_HEX if v else GRAY
            if v:
                cv.create_rectangle(x0 + 3, H - 20 - h, x0 + bw - 3, H - 20, fill=color, outline="")
                cv.create_text(x0 + bw / 2, H - 26 - h, text=str(v), font=("Segoe UI", 8))
            if es15:
                cv.create_line(x0, 6, x0, H - 4, fill="#cbd5e0", dash=(2, 2))
                txt, col = "15 (pleno)", "#b7791f"
            else:
                txt, col = str(k), "#2d3748"
            cv.create_text(x0 + bw / 2, H - 10, text=txt, fill=col,
                           font=("Segoe UI", 8, "bold" if k >= 10 else "normal"))


BLUE_HEX = "#{:02x}{:02x}{:02x}".format(*BLUE)
GOLD = "#d69e2e"
