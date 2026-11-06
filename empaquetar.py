"""Crea la versión para Windows sin Python: dist/Quiniela/Quiniela.exe y Quiniela-windows.zip.

Uso:  python -m pip install pyinstaller numpy   y luego   python empaquetar.py
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(AQUI, "dist")
TRABAJO = os.path.join(AQUI, "build")


def main():
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", "Quiniela",
                    "--icon", os.path.join(AQUI, "icono.ico"), "--distpath", DIST, "--workpath", TRABAJO,
                    "--specpath", TRABAJO, os.path.join(AQUI, "quiniela_app.py")], check=True, cwd=AQUI)
    destino = os.path.join(DIST, "Quiniela")
    # junto al .exe: iconos y pesos de la tabla de puntos (lo demás lo crea o descarga el programa)
    for f in ("icono.png", "icono.ico", "LICENSE"):
        shutil.copy2(os.path.join(AQUI, f), destino)
    os.makedirs(os.path.join(destino, "data", "ligas"), exist_ok=True)
    for f in ("puntos_pesos.json", "puntos_config.json"):
        shutil.copy2(os.path.join(AQUI, "data", "ligas", f), os.path.join(destino, "data", "ligas"))
    with open(os.path.join(destino, "LEEME.txt"), "w", encoding="utf-8") as fh:
        fh.write("PROGRAMA DE LA QUINIELA\r\n\r\nDoble clic en Quiniela.exe. No hace falta instalar nada.\r\n"
                 "La primera vez descarga datos de las ligas (tarda un poco). Necesita internet.\r\n"
                 "Tus apuestas se guardan en la carpeta mis_apuestas, junto al programa.\r\n\r\n"
                 "Guía completa: https://github.com/victorsensenom/quinielas\r\n"
                 "La quiniela es un juego de azar: juega solo lo que estés dispuesto a perder. +18.\r\n")
    zip_base = os.path.join(DIST, "Quiniela-windows")
    shutil.make_archive(zip_base, "zip", DIST, "Quiniela")
    print("Listo:", destino, "y", zip_base + ".zip")


if __name__ == "__main__":
    main()
