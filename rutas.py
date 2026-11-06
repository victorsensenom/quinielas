"""Carpeta del programa: donde están (o se guardan) datos, apuestas, ficheros generados e iconos.

Si el programa se ejecuta como Quiniela.exe (empaquetado con PyInstaller), es la carpeta del .exe;
si se ejecuta con Python, la carpeta de estos ficheros .py.
"""
import os
import sys

CONGELADO = getattr(sys, "frozen", False)
CARPETA = os.path.dirname(sys.executable) if CONGELADO else os.path.dirname(os.path.abspath(__file__))
