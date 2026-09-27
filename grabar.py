"""Graba ejemplos etiquetados a mano para calibrar golpe / bloqueo / parry / potenciado.

    python grabar.py
Jugá vos (el bot NO tiene que estar corriendo). Apretá la tecla de lo que vas a hacer:
    F4  golpes sin bloquear (dejá que el T.W.I.G. te pegue)
    F6  bloqueos normales (escudo arriba desde antes del golpe)
    F7  parrys (levantá el escudo justo antes del golpe)
    F8  parry + ataque potenciado (parry y enseguida atacás)
    F9  nada / pausa de etiqueta
    F10 terminar
Solo graba mientras Valheim está al frente. Genera etiquetas.mp4 y etiquetas.csv.
"""
import csv
import ctypes
import time

import cv2
import mss
import numpy as np
from pynput import keyboard

import config as C
from hud import LectorHUD

ETIQUETAS = {keyboard.Key.f4: "golpe", keyboard.Key.f6: "bloqueo", keyboard.Key.f7: "parry",
             keyboard.Key.f8: "potenciado", keyboard.Key.f9: ""}
FPS = 30


def valheim_al_frente():
    u = ctypes.windll.user32
    h = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(h, buf, 256)
    return buf.value.strip().lower() == C.TITULO_VENTANA


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    estado = {"etiqueta": "", "seguir": True}

    def on_press(k):
        if k == keyboard.Key.f10:
            estado["seguir"] = False
            return False
        if k in ETIQUETAS:
            estado["etiqueta"] = ETIQUETAS[k]
            print(f"{time.strftime('%H:%M:%S')}  etiqueta: {estado['etiqueta'] or '(nada)'}", flush=True)

    keyboard.Listener(on_press=on_press, daemon=True).start()

    x1, y1, x2, y2 = C.ZONA_GRABAR
    lector = LectorHUD()
    with mss.mss() as s:
        mon = s.monitors[C.MONITOR]
        caja = {"left": mon["left"] + x1, "top": mon["top"] + y1, "width": x2 - x1, "height": y2 - y1}
        vx1, vy1, vx2, vy2 = C.ZONA_VIDA
        caja_vida = {"left": mon["left"] + vx1, "top": mon["top"] + vy1, "width": vx2 - vx1, "height": vy2 - vy1}
        vid = cv2.VideoWriter("etiquetas.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (x2 - x1, y2 - y1))
        with open("etiquetas.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["cuadro", "t", "etiqueta", "vida_px"])
            print("Listo. Poné Valheim al frente y usá F4 y F6-F9 para etiquetar, F10 para terminar.", flush=True)
            n, t0 = 0, time.perf_counter()
            while estado["seguir"]:
                ti = time.perf_counter()
                if valheim_al_frente():
                    img = np.asarray(s.grab(caja))[:, :, :3]
                    _, vida_px = lector.vida(np.asarray(s.grab(caja_vida))[:, :, :3].copy())
                    vid.write(np.ascontiguousarray(img))
                    w.writerow([n, f"{ti - t0:.3f}", estado["etiqueta"], vida_px])
                    n += 1
                espera = 1 / FPS - (time.perf_counter() - ti)
                if espera > 0:
                    time.sleep(espera)
        vid.release()
    print(f"Guardado: etiquetas.mp4 / etiquetas.csv ({n} cuadros)")


if __name__ == "__main__":
    main()
