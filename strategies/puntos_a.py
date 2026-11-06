"""Modelo A: puntos propios sin cuotas (ver puntos_comun.py). --param forma=6D --param valor=0"""
from strategies.puntos_comun import Base


class Strategy(Base):
    modelo = "A"
