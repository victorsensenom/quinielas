"""valor_ev: columnas que maximizan el VALOR ESPERADO (premio esperado), no los aciertos.

Para cada una de las 3^14 columnas se calcula EV(c) = suma sobre categorias (14/15, 13, 12, 11,
10) de P(categoria) x premio esperado, con el modelo de strategies/valor_model.py:
probabilidad real = % probables (mezclada un 10 % con LAE, calibrado), rivales = % LAE
(lo que juega el publico) y premio = fondo de la categoria / (rivales + 1), neto de impuestos,
calibrado con jornadas anteriores.

Seleccion: greedy con diversificacion (``valor_model.select_ev``):
    ganancia(c) = EV(c) - delta * sum_{r a distancia <= 2} p(r) * min(V(c, r), mejor_ya(r))
delta = 0 -> las n columnas de mayor EV; delta = 1 -> cada resultado solo cuenta una vez.

Parametros (--param):
    delta   (0..1, def. 0.5)  diversificacion
    n       columnas (def. presupuesto / precio)
    ev_min  si el EV estimado por euro de la jornada es menor, no se juega (def. sin umbral)
    ev_alto, n_alto  si EV/euro >= ev_alto se juegan n_alto columnas (requiere --budget suficiente)
    cand    candidatos para el greedy (def. 3000 columnas de mayor EV)
Pleno al 15: marcador mas probable segun % probables de goles (data/pleno15.csv).
"""
import math

from engine.reduce import to_columnset

from strategies import valor_model as vm


def _opt(x, cast=float):
    if x is None or (isinstance(x, str) and x.lower() in ("", "none")):
        return None
    return cast(x)


class Strategy:
    def __init__(self, delta=0.5, n=None, ev_min=None, ev_alto=None, n_alto=None, cand=3000, alpha=vm.ALPHA):
        self.delta = float(delta)
        self.n = _opt(n, int)
        self.ev_min = _opt(ev_min)
        self.ev_alto = _opt(ev_alto)
        self.n_alto = _opt(n_alto, int)
        self.cand = int(cand)
        self.alpha = float(alpha)
        self.log = []          # (temporada, jornada, ev_euro, columnas jugadas)

    def generate(self, info, history, budget_eur):
        price = info.precio_apuesta
        kmax = int(math.floor(budget_eur / price + 1e-9))
        n = min(self.n or kmax, kmax)
        if n <= 0:
            return []
        n_hi = min(self.n_alto, kmax) if (self.ev_alto is not None and self.n_alto) else n
        m = vm.JornadaModel(info, history, alpha=self.alpha)
        sel = vm.select_ev(m, max(n, n_hi), self.delta, self.cand)
        base = sel[:n]
        ev_euro = float(m.EV[base].sum()) / (len(base) * price)
        k = n
        if self.ev_min is not None and ev_euro < self.ev_min:
            k = 0
        elif self.ev_alto is not None and ev_euro >= self.ev_alto:
            k = n_hi
        self.log.append((info.temporada, info.jornada, ev_euro, k))
        if k == 0:
            return []
        return to_columnset(sel[:k], m.pleno)
