"""Modelo B: % probables + correccion con puntos (ver puntos_comun.py). --param forma=6D --param valor=0"""
from strategies.puntos_comun import Base


class Strategy(Base):
    modelo = "B"
