"""Saca una captura, dibuja las zonas y muestra lo que lee OpenCV.

    python calibrar.py                 # captura la pantalla en 3 segundos (poné Valheim al frente)
    python calibrar.py --video clip.mp4 --seg 10
Genera calibracion.png y calibracion_ia.png. Si un recuadro no cae sobre su barra,
corregí las coordenadas en config.py.
"""
import argparse
import time

import cv2

import config as C
from hud import DetectorGolpe, LectorHUD, armar_imagen_ia


class Captura:
    def __init__(self, img):
        self.img = img

    def grab(self, z):
        return self.img[z[1]:z[3], z[0]:z[2]].copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video")
    ap.add_argument("--seg", type=float, default=0)
    a = ap.parse_args()

    if a.video:
        cap = cv2.VideoCapture(a.video)
        cap.set(cv2.CAP_PROP_POS_MSEC, a.seg * 1000)
        ok, img = cap.read()
    else:
        import mss
        import numpy as np
        print("Capturando en 3 segundos...")
        time.sleep(3)
        with mss.mss() as s:
            img = np.asarray(s.grab(s.monitors[C.MONITOR]))[:, :, :3].copy()
    img = cv2.resize(img, (C.BASE_W, C.BASE_H))
    f = Captura(img)

    lec = LectorHUD()
    vida, px = lec.vida(f.grab(C.ZONA_VIDA))
    est, vis = lec.estamina(f.grab(C.ZONA_ESTAMINA))
    arma = lec.arma(f.grab(C.ZONA_ARMA))
    print(f"vida: {px} px (poné VIDA_ALTO_LLENO={px} si ahora tenés la vida llena)")
    print(f"estamina: {est:.0%} {'(barra oculta = llena)' if not vis else ''}")
    print(f"arma: {arma:.0%}")

    out = img.copy()
    zonas = [(C.ZONA_ENEMIGO, (60, 60, 255), "enemigo"), (C.ZONA_TEXTOS, (255, 255, 255), "textos"), (C.ZONA_VIDA, (200, 120, 255), "vida"),
             (C.ZONA_ESTAMINA, (0, 230, 255), "estamina"), (C.ZONA_ARMA, (255, 200, 80), "arma")]
    for (x1, y1, x2, y2), col, n in zonas:
        cv2.rectangle(out, (x1, y1), (x2, y2), col, 2)
        cv2.putText(out, n, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
    cv2.imwrite("calibracion.png", out)
    with open("calibracion_ia.png", "wb") as fh:
        fh.write(armar_imagen_ia(f))
    print("Guardé calibracion.png y calibracion_ia.png")


if __name__ == "__main__":
    main()
