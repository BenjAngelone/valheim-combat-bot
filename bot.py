"""Bot de entrenamiento para Valheim: OpenCV bloquea en tiempo real, la IA local decide.

Uso:
    python bot.py                     # juego real (arranca en PAUSA: F8 para empezar)
    python bot.py --video clip.mp4    # prueba con un video, sin tocar teclado ni mouse
Teclas: F8 pausa/reanuda · F9 IA/reglas · F10 salir
"""
import argparse
import collections
import os
import threading
import time

import config as C
from brain import loop_cerebro
from hud import DetectorCombate, DetectorGolpe, FuentePantalla, FuenteVideo, LectorHUD


# ============================================================ estado compartido
class Estado:
    def __init__(self):
        self.lock = threading.Lock()
        self.corriendo = True
        self.pausado = True
        self.ventana_ok = True
        self.fuente = C.FUENTE_DECISION
        self.modo = "solo_bloquear"          # lo que decidió la cabeza
        self.comer_pendiente = False
        self.ultima_comida = 0.0
        # lecturas del HUD
        self.vida, self.vida_px, self.estamina, self.arma = 1.0, 0, 1.0, 1.0
        self.est_visible = False
        # rendimiento
        self.fps_combate, self.ms_combate, self.ms_hud = 0.0, 0.0, 0.0
        self.movimiento = collections.deque([0.0] * 180, maxlen=180)
        self.marcas_bloqueo = collections.deque([0] * 180, maxlen=180)
        # contadores
        self.bloqueos = self.reacciones = self.ataques = self.comidas = self.contras = self.parrys = 0
        self.t_bloqueo = self.t_parry = self.t_contra = 0.0  # time.time() del último bloqueo / parry / contra
        self.golpes = self.aciertos = 0       # golpes recibidos sin bloquear / golpes tuyos que entraron
        self.t_golpe = 0.0
        self.cupula = 0.0                     # aclarado del último bloqueo (parry si pasa UMBRAL_CUPULA)
        # IA
        self.ia_consultas = self.ia_errores = self.ia_acuerdos = 0
        self.ia_lat_ultima, self.ia_lat_total = 0.0, 0.0
        self.ia_imagen = None
        self.ia_respuesta = "—"
        self.decision_ia = self.decision_reglas = "—"
        self.logs = collections.deque(maxlen=200)

    def log(self, txt):
        linea = f"{time.strftime('%H:%M:%S')}  {txt}"
        with self.lock:
            self.logs.append(linea)
        if os.environ.get("BOT_ECO"):
            print(linea, flush=True)

    def registrar_ia(self, lat, acuerdo):
        self.ia_consultas += 1
        self.ia_lat_ultima = lat
        self.ia_lat_total += lat
        self.ia_acuerdos += int(acuerdo)

    def aplicar_decision(self, accion):
        if accion == "parar":
            if not self.pausado:
                self.pausado = True
                self.log("⚠ SEGURIDAD: vida crítica, bot en pausa (F8 para seguir)")
            return
        if accion == "comer":
            if C.TECLA_COMIDA and time.time() - self.ultima_comida > C.COMER_COOLDOWN:
                self.comer_pendiente = True
            self.modo = "solo_bloquear"
        else:
            self.modo = accion


# ============================================================ teclado y mouse
class Controles:
    def __init__(self, simulado):
        self.simulado = simulado
        self.bloqueando = False
        if not simulado:
            import pydirectinput
            pydirectinput.PAUSE = 0
            pydirectinput.FAILSAFE = False
            self.pdi = pydirectinput

    def ventana_activa(self):
        if self.simulado or os.name != "nt":
            return True
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, buf, n + 1)
        return buf.value.strip().lower() == C.TITULO_VENTANA  # exacto: "valheim_bot" en VS Code no cuenta

    def bloqueo(self, on):
        if on == self.bloqueando:
            return
        self.bloqueando = on
        if not self.simulado:
            (self.pdi.mouseDown if on else self.pdi.mouseUp)(button="right")

    def atacar(self):
        if not self.simulado:
            self.pdi.mouseDown(button="left")
            time.sleep(0.05)
            self.pdi.mouseUp(button="left")

    def tecla(self, k):
        if not self.simulado:
            self.pdi.press(k)

    def soltar_todo(self):
        self.bloqueo(False)


# ============================================================ grabación para calibrar
class Grabador:
    """Filma ZONA_GRABAR con los eventos del bot encima + CSV por cuadro (grabacion.mp4/.csv)."""

    def __init__(self, segundos):
        import csv
        import cv2
        self.cv2 = cv2
        x1, y1, x2, y2 = C.ZONA_GRABAR
        self.tam = ((x2 - x1) // 2, (y2 - y1) // 2)
        self.vid = cv2.VideoWriter("grabacion.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 25, self.tam)
        self.fh = open("grabacion.csv", "w", newline="", encoding="utf-8")
        self.csv = csv.writer(self.fh)
        self.csv.writerow(["cuadro", "t", "mov", "cupula", "estamina", "vida", "escudo", "evento"])
        self.segundos, self.t0, self.n = segundos, None, 0

    def cuadro(self, img, estado, mov, cupula, escudo, evento):
        """Devuelve False cuando terminó."""
        ahora = time.perf_counter()
        if self.t0 is None:
            self.t0 = ahora
            estado.log(f"🎥 grabando {self.segundos:.0f} s…")
        t = ahora - self.t0
        cv2 = self.cv2
        f = cv2.resize(img, self.tam, interpolation=cv2.INTER_AREA)
        txt = f"#{self.n} t={t:5.2f} mov={mov:4.1f} cup={cupula:4.1f} est={estado.estamina:.0%}"
        cv2.putText(f, txt, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        if escudo:
            cv2.putText(f, "ESCUDO", (6, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 200, 255), 1, cv2.LINE_AA)
        if evento:
            cv2.putText(f, evento.upper(), (6, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 255, 80), 2, cv2.LINE_AA)
        self.vid.write(f)
        self.csv.writerow([self.n, f"{t:.3f}", f"{mov:.2f}", f"{cupula:.2f}", f"{estado.estamina:.3f}",
                           f"{estado.vida:.3f}", int(escudo), evento])
        self.n += 1
        if t >= self.segundos:
            self.cerrar()
            estado.log(f"🎥 grabación lista: {self.n} cuadros")
            return False
        return True

    def cerrar(self):
        if self.vid is not None:
            self.vid.release()
            self.fh.close()
            self.vid = None


def recorte(img, base, zona):
    """Saca `zona` de una captura `img` que empieza en la esquina de `base`."""
    return img[zona[1] - base[1]:zona[3] - base[1], zona[0] - base[0]:zona[2] - base[0]]


def union(*zonas):
    return (min(z[0] for z in zonas), min(z[1] for z in zonas),
            max(z[2] for z in zonas), max(z[3] for z in zonas))


# ============================================================ loops
def loop_hud(estado, fuente):
    lector = LectorHUD()
    while estado.corriendo:
        t0 = time.perf_counter()
        estado.vida, estado.vida_px = lector.vida(fuente.grab(C.ZONA_VIDA))
        estado.estamina, estado.est_visible = lector.estamina(fuente.grab(C.ZONA_ESTAMINA))
        estado.arma = lector.arma(fuente.grab(C.ZONA_ARMA))
        estado.ms_hud = (time.perf_counter() - t0) * 1000
        time.sleep(0.1)


def loop_combate(estado, fuente, ctrl, grab=None):
    """Reflejos: movimiento del enemigo -> levanta escudo; textos del juego -> bloqueo/parry -> contraataque."""
    det, textos = DetectorGolpe(), DetectorCombate()
    periodo = 1 / C.FPS_COMBATE
    bloq_desde = bloq_hasta = ultimo_ataque = ultimo_mov = ignorar_hasta = 0.0
    contra_en = None  # momento programado para contraatacar
    vueltas, t_fps = 0, time.perf_counter()
    # una sola captura por vuelta (cada grab de mss cuesta ~15 ms)
    zonas = [C.ZONA_ENEMIGO, C.ZONA_TEXTOS] + ([C.ZONA_GRABAR] if grab else [])
    base = union(*zonas)
    while estado.corriendo:
        t0 = time.perf_counter()
        img = fuente.grab(base)
        mov = det.medir(recorte(img, base, C.ZONA_ENEMIGO), t0)
        eventos = textos.medir(recorte(img, base, C.ZONA_TEXTOS), t0)
        ahora = time.perf_counter()
        amenaza = mov > C.UMBRAL_MOVIMIENTO and ahora > ignorar_hasta
        marca = 0
        evento = ",".join(eventos)

        # lo que muestra el juego se cuenta siempre (también en pausa, si jugás vos)
        for ev in eventos:
            if ev in ("bloqueo", "parry"):
                estado.bloqueos += 1
                estado.t_bloqueo = time.time()
                marca = 1
                if ev == "parry":
                    estado.parrys += 1
                    estado.t_parry = time.time()
                    estado.log(f"✨ parry (cúpula +{textos.cupula:.0f})")
                contra_en = ahora + C.CONTRAATAQUE_RETRASO
            elif ev == "golpe":
                estado.golpes += 1
                estado.t_golpe = time.time()
                estado.log("💥 golpe recibido sin bloquear")
            elif ev == "potenciado":
                estado.aciertos += 1
                estado.contras += 1
                estado.t_contra = time.time()
                estado.log("⚡ ataque potenciado (enemigo aturdido por el parry)")
            elif ev == "dano":
                estado.aciertos += 1
        estado.cupula = textos.cupula

        estado.ventana_ok = ctrl.ventana_activa()
        if estado.pausado or not estado.ventana_ok:
            ctrl.soltar_todo()
            contra_en = None
        elif estado.comer_pendiente:
            ctrl.soltar_todo()
            ctrl.tecla(C.TECLA_COMIDA)
            estado.comer_pendiente = False
            estado.ultima_comida = time.time()
            estado.comidas += 1
            estado.log(f"🍖 come (tecla {C.TECLA_COMIDA})")
        else:
            if amenaza:
                ultimo_mov = ahora

            puede_atacar = (C.ESTRATEGIA_BLOQUEO == "reactivo" and estado.modo == "atacar"
                            and estado.estamina >= C.ESTAMINA_MIN_ATAQUE
                            and ahora - ultimo_ataque > C.ATAQUE_INTERVALO)
            es_contra = contra_en is not None and ahora >= contra_en
            quiere_atacar = puede_atacar and (
                es_contra                                                     # contraataque
                or ahora - ultimo_mov > C.CALMA_ANTES_DE_ATACAR               # enemigo quieto
                or ahora - ultimo_ataque > C.ATAQUE_MAX_ESPERA                # no esperar para siempre
                or (ctrl.bloqueando and ahora - bloq_desde > C.BLOQUEO_MAX))

            if quiere_atacar:
                ctrl.bloqueo(False)
                ctrl.atacar()
                estado.ataques += 1
                marca = 2
                evento = ",".join(filter(None, [evento, "contra" if es_contra else "ataque"]))
                ultimo_ataque, contra_en = ahora, None
                ignorar_hasta = time.perf_counter() + C.IGNORAR_TRAS_ATAQUE
            elif C.ESTRATEGIA_BLOQUEO == "mantener":
                ctrl.bloqueo(True)
            else:
                if amenaza:
                    if not ctrl.bloqueando:
                        bloq_desde = ahora
                        estado.reacciones += 1
                        evento = evento or "reaccion"
                    bloq_hasta = ahora + C.BLOQUEO_DURACION
                    ctrl.bloqueo(True)
                elif ctrl.bloqueando and ahora > bloq_hasta:
                    ctrl.bloqueo(False)
                    ignorar_hasta = ahora + 0.25  # bajar el escudo también genera movimiento

        if grab and not estado.pausado and estado.ventana_ok:
            if not grab.cuadro(recorte(img, base, C.ZONA_GRABAR), estado, mov, textos.cupula,
                               ctrl.bloqueando, evento):
                grab = None
        estado.movimiento.append(mov)
        estado.marcas_bloqueo.append(marca)
        estado.ms_combate = (time.perf_counter() - t0) * 1000
        vueltas += 1
        if ahora - t_fps >= 1:
            estado.fps_combate = vueltas / (ahora - t_fps)
            vueltas, t_fps = 0, ahora
        espera = periodo - (time.perf_counter() - t0)
        if espera > 0:
            time.sleep(espera)
    ctrl.soltar_todo()
    if grab:
        grab.cerrar()


def escuchar_teclas(estado):
    try:
        from pynput import keyboard
    except ImportError:
        estado.log("pynput no instalado: sin teclas rápidas")
        return
    k_pausa, k_fuente, k_salir = (getattr(keyboard.Key, t) for t in
                                  (C.TECLA_PAUSA, C.TECLA_FUENTE, C.TECLA_SALIR))

    def on_press(k):
        if k == k_pausa:
            estado.pausado = not estado.pausado
            estado.log("⏸ pausa" if estado.pausado else "▶ activo")
        elif k == k_fuente:
            estado.fuente = "reglas" if estado.fuente == "ia" else "ia"
            estado.log(f"decide: {estado.fuente}")
        elif k == k_salir:
            estado.corriendo = False
            return False

    keyboard.Listener(on_press=on_press, daemon=True).start()


# ============================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="probar con un video en vez de la pantalla (no manda teclas)")
    ap.add_argument("--sin-panel", action="store_true")
    ap.add_argument("--segundos", type=float, default=0, help="cortar solo después de N segundos")
    ap.add_argument("--grabar", type=float, default=0, metavar="SEG",
                    help="filmar SEG segundos de combate (grabacion.mp4/.csv) para calibrar")
    a = ap.parse_args()

    if os.name == "nt":  # que mss y Tk usen píxeles reales aunque Windows escale al 125 %
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    fuente = FuenteVideo(a.video) if a.video else FuentePantalla()
    estado = Estado()
    ctrl = Controles(simulado=bool(a.video))
    if a.video:
        estado.pausado = False
        estado.log(f"modo prueba con video: {a.video} (sin teclado/mouse)")
    else:
        estado.log("listo · poné Valheim al frente y apretá F8")

    hilos = [threading.Thread(target=loop_hud, args=(estado, fuente), daemon=True),
             threading.Thread(target=loop_combate, daemon=True,
                              args=(estado, fuente, ctrl, Grabador(a.grabar) if a.grabar else None)),
             threading.Thread(target=loop_cerebro, args=(estado, fuente), daemon=True)]
    for h in hilos:
        h.start()
    escuchar_teclas(estado)

    t_fin = time.time() + a.segundos if a.segundos else None

    def debe_seguir():
        if t_fin and time.time() > t_fin:
            estado.corriendo = False
        if a.video and fuente.terminado:
            estado.corriendo = False
        return estado.corriendo

    try:
        if a.sin_panel:
            while debe_seguir():
                time.sleep(0.2)
        else:
            from panel import Panel
            Panel(estado, debe_seguir).run()
    except KeyboardInterrupt:
        pass
    estado.corriendo = False
    time.sleep(0.3)
    ctrl.soltar_todo()
    print(f"Fin · reacciones {estado.reacciones} · golpes bloqueados {estado.bloqueos} · ataques {estado.ataques} · comidas {estado.comidas} · "
          f"consultas IA {estado.ia_consultas} (errores {estado.ia_errores})")


if __name__ == "__main__":
    main()
