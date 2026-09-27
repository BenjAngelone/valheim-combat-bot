"""La "cabeza" lenta: consulta a la IA local (Ollama) cada pocos segundos."""
import base64
import csv
import json
import os
import time
import urllib.request

import cv2
import numpy as np

import config as C
from hud import armar_imagen_ia

ACCIONES = ("atacar", "solo_bloquear", "comer")

PROMPT = """You control a Valheim character that is training combat skills against a weak enemy.
The image shows HUD crops: 'vida_y_comida' (red vertical health bar and food icons with minutes left),
'arma' (weapon slot; the white line under it is durability) and 'estamina' (yellow bar, hidden when full).
Pixel measurements: health={vida:.0%}, stamina={est:.0%}, weapon durability={arma:.0%}.
Choose ONE action:
- "atacar": health and stamina are fine, keep attacking and blocking.
- "solo_bloquear": stamina is low or the weapon is worn, only block.
- "comer": health is low or food timers are short.
Answer ONLY JSON: {{"accion": "atacar|solo_bloquear|comer", "razon": "few words"}}"""


def decidir_reglas(vida, est, arma):
    if vida < C.VIDA_PARAR:
        return "parar", "vida crítica"
    if vida < C.VIDA_COMER:
        return "comer", f"vida {vida:.0%}"
    if arma < C.ARMA_MIN:
        return "solo_bloquear", f"arma gastada {arma:.0%}"
    if est < C.ESTAMINA_MIN_ATAQUE:
        return "solo_bloquear", f"estamina {est:.0%}"
    return "atacar", "todo en orden"


def consultar_ia(png, vida, est, arma):
    cuerpo = {
        "model": C.MODELO_IA,
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_predict": 80},
        "messages": [{
            "role": "user",
            "content": PROMPT.format(vida=vida, est=est, arma=arma),
            "images": [base64.b64encode(png).decode()],
        }],
    }
    if C.IA_NUM_GPU is not None:
        cuerpo["options"]["num_gpu"] = C.IA_NUM_GPU
    req = urllib.request.Request(C.OLLAMA_URL, json.dumps(cuerpo).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=C.IA_TIMEOUT) as r:
        texto = json.loads(r.read())["message"]["content"]
    datos = json.loads(texto)
    accion = str(datos.get("accion", "")).strip().lower()
    if accion not in ACCIONES:
        raise ValueError(f"respuesta inválida: {texto[:80]}")
    return accion, str(datos.get("razon", ""))[:80], texto


def miniatura_b64(png, ancho=360):
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    f = ancho / img.shape[1]
    img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


def loop_cerebro(estado, fuente):
    nuevo = not os.path.exists(C.ARCHIVO_LOG)
    with open(C.ARCHIVO_LOG, "a", newline="", encoding="utf-8") as fh:
        log = csv.writer(fh)
        if nuevo:
            log.writerow(["hora", "vida", "estamina", "arma", "accion_ia", "accion_reglas",
                          "usada", "latencia_ms", "razon_ia"])
        while estado.corriendo:
            t_sig = time.time() + C.IA_INTERVALO
            vida, est, arma = estado.vida, estado.estamina, estado.arma
            reglas, razon_r = decidir_reglas(vida, est, arma)

            accion_ia, razon_ia, lat = None, "", None
            try:
                png = armar_imagen_ia(fuente)
                estado.ia_imagen = miniatura_b64(png)
                t0 = time.perf_counter()
                accion_ia, razon_ia, crudo = consultar_ia(png, vida, est, arma)
                lat = (time.perf_counter() - t0) * 1000
                estado.ia_respuesta = crudo
                estado.registrar_ia(lat, accion_ia == reglas)
            except Exception as e:  # sin Ollama, JSON roto, timeout...
                estado.ia_errores += 1
                estado.ia_respuesta = f"error: {e}"[:120]

            # decisión final: la seguridad manda siempre
            if reglas == "parar":
                final, fuente_txt, razon = "parar", "seguridad", razon_r
            elif estado.fuente == "ia" and accion_ia:
                final, fuente_txt, razon = accion_ia, "IA", razon_ia
            else:
                final, fuente_txt, razon = reglas, "reglas", razon_r

            estado.aplicar_decision(final)
            estado.decision_ia = accion_ia or "—"
            estado.decision_reglas = reglas
            estado.log(f"[{fuente_txt}] {final} · {razon}"
                       + (f" · {lat:.0f} ms" if lat else "")
                       + ("" if accion_ia is None or accion_ia == reglas else f"  (reglas: {reglas})"))
            log.writerow([time.strftime("%H:%M:%S"), f"{vida:.2f}", f"{est:.2f}", f"{arma:.2f}",
                          accion_ia or "", reglas, final, f"{lat:.0f}" if lat else "", razon_ia])
            fh.flush()

            while estado.corriendo and time.time() < t_sig:
                time.sleep(0.1)
