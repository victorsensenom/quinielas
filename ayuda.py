"""Ayuda del programa: visita guiada paso a paso y explicaciones al pasar el ratón.

La visita resalta cada parte de la ventana con un recuadro rojo y un globo con la explicación
(Anterior / Siguiente / Saltar). Se abre sola la primera vez y luego con el botón «? Ayuda».
"""
import json
import os
import tkinter as tk

import rutas

CARPETA = rutas.CARPETA
VISTO = os.path.join(CARPETA, "ayuda.json")
ROJO, AZUL = "#e53e3e", "#1a365d"


def ya_vista(nombre):
    try:
        with open(VISTO, encoding="utf-8") as f:
            return bool(json.load(f).get(nombre))
    except (OSError, ValueError):
        return False


def marcar_vista(nombre):
    try:
        with open(VISTO, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d[nombre] = True
    try:
        with open(VISTO, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


class Tooltip:
    """Explicación corta que aparece al dejar el ratón sobre un control."""

    def __init__(self, widget, texto, espera=600):
        self.w, self.texto, self.espera = widget, texto, espera
        self.id = self.tip = None
        widget.bind("<Enter>", self._programar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")
        widget.bind("<ButtonPress>", self._ocultar, add="+")

    def _programar(self, _e=None):
        self._ocultar()
        self.id = self.w.after(self.espera, self._mostrar)

    def _mostrar(self):
        x = self.w.winfo_rootx() + 10
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tk.Toplevel(self.w)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=self.texto, justify="left", bg="#fffbea", fg="#1a202c", relief="solid", bd=1,
                 font=("Segoe UI", 9), wraplength=320, padx=6, pady=4).pack()
        self.tip.wm_geometry(f"+{x}+{y}")

    def _ocultar(self, _e=None):
        if self.id:
            self.w.after_cancel(self.id)
            self.id = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


def avisos(pares):
    """pares: [(widget, texto)]: pone una explicación al pasar el ratón por cada control."""
    for w, t in pares:
        if w is not None:
            Tooltip(w, t)


class Visita:
    """Visita guiada. pasos: [(objetivo, título, texto)]; objetivo es un widget, una lista de
    widgets (se resalta lo que ocupan juntos) o una función que devuelve uno de los dos."""

    def __init__(self, ventana, pasos, al_terminar=None):
        self.v, self.pasos, self.al_terminar = ventana, pasos, al_terminar
        self.n = 0
        self.marco = []
        self.globo = None
        ventana.update_idletasks()
        self._paso(0)

    # -------------------------------------------------------------- dibujo
    def _caja(self, objetivo):
        if callable(objetivo):
            objetivo = objetivo()
        ws = objetivo if isinstance(objetivo, (list, tuple)) else [objetivo]
        ws = [w for w in ws if w is not None and w.winfo_exists() and w.winfo_ismapped()]
        if not ws:
            return None
        x0 = min(w.winfo_rootx() for w in ws)
        y0 = min(w.winfo_rooty() for w in ws)
        x1 = max(w.winfo_rootx() + w.winfo_width() for w in ws)
        y1 = max(w.winfo_rooty() + w.winfo_height() for w in ws)
        return x0 - 4, y0 - 4, x1 + 4, y1 + 4

    def _borrar(self):
        for t in self.marco:
            t.destroy()
        self.marco = []
        if self.globo:
            self.globo.destroy()
            self.globo = None

    def _recuadro(self, x0, y0, x1, y1, g=3):
        for (x, y, w, h) in ((x0, y0, x1 - x0, g), (x0, y1 - g, x1 - x0, g), (x0, y0, g, y1 - y0), (x1 - g, y0, g, y1 - y0)):
            t = tk.Toplevel(self.v)
            t.wm_overrideredirect(True)
            t.attributes("-topmost", True)
            t.configure(bg=ROJO)
            t.wm_geometry(f"{max(w, 1)}x{max(h, 1)}+{x}+{y}")
            self.marco.append(t)

    def _paso(self, n):
        self._borrar()
        paso = 1 if n >= self.n else -1
        caja = None
        while 0 <= n < len(self.pasos):                  # lo que no se ve en pantalla se salta
            caja = self._caja(self.pasos[n][0])
            if caja:
                break
            n += paso
        if caja is None:
            return self.cerrar() if n >= len(self.pasos) else self._paso(self.n) if n < 0 and self.n else self.cerrar()
        objetivo, titulo, texto = self.pasos[n]
        self.n = n
        self._recuadro(*caja)

        g = self.globo = tk.Toplevel(self.v)
        g.wm_overrideredirect(True)
        g.attributes("-topmost", True)
        g.configure(bg=ROJO)
        caja_g = tk.Frame(g, bg="white", padx=14, pady=10)
        caja_g.pack(padx=2, pady=2)
        tk.Label(caja_g, text=titulo, font=("Segoe UI", 11, "bold"), bg="white", fg=AZUL, anchor="w").pack(fill="x")
        tk.Label(caja_g, text=texto, font=("Segoe UI", 10), bg="white", fg="#1a202c", justify="left",
                 wraplength=360, anchor="w").pack(fill="x", pady=(4, 10))
        pie = tk.Frame(caja_g, bg="white")
        pie.pack(fill="x")
        tk.Label(pie, text=f"{n + 1} de {len(self.pasos)}", bg="white", fg="#718096", font=("Segoe UI", 9)).pack(side="left")
        ultimo = n == len(self.pasos) - 1
        tk.Button(pie, text="Terminar" if ultimo else "Siguiente ›", command=lambda: self._paso(self.n + 1),
                  bg="#2b6cb0", fg="white", relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
                  cursor="hand2").pack(side="right")
        if n:
            tk.Button(pie, text="‹ Anterior", command=lambda: self._paso(self.n - 1), relief="flat", bg="#edf2f7",
                      font=("Segoe UI", 9), padx=8, cursor="hand2").pack(side="right", padx=6)
        if not ultimo:
            tk.Button(pie, text="Saltar", command=self.cerrar, relief="flat", bg="white", fg="#718096",
                      font=("Segoe UI", 9, "underline"), cursor="hand2").pack(side="right", padx=6)
        g.bind("<Escape>", lambda _e: self.cerrar())
        g.update_idletasks()
        # globo debajo de lo resaltado; si no cabe, encima; siempre dentro de la pantalla
        gw, gh = g.winfo_reqwidth(), g.winfo_reqheight()
        sw, sh = self.v.winfo_screenwidth(), self.v.winfo_screenheight()
        x0, y0, x1, y1 = caja
        x = min(max(8, x0), sw - gw - 8)
        y = y1 + 10 if y1 + 10 + gh < sh - 40 else max(8, y0 - gh - 10)
        if y0 - gh - 10 < 8 and y1 + 10 + gh >= sh - 40:                 # ni debajo ni encima: al lado
            x, y = (x1 + 10, max(8, y0)) if x1 + 10 + gw < sw else (max(8, x0 - gw - 10), max(8, y0))
        g.wm_geometry(f"{gw}x{gh}+{int(x)}+{int(y)}")
        g.update_idletasks()
        g.lift()
        g.focus_force()

    def cerrar(self):
        self._borrar()
        if self.al_terminar:
            self.al_terminar()
