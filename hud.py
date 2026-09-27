"""Captura de pantalla y lectura del HUD con OpenCV (rápido, sin IA)."""
import threading
import time

import cv2
import numpy as np

import config as C


# ============================================================ fuentes de imagen
class FuentePantalla:
    """Captura regiones de la pantalla con mss (un objeto mss por hilo)."""

    def __init__(self):
        import mss
        self._mss = mss
        self._local = threading.local()
        with mss.mss() as s:
            mon = s.monitors[C.MONITOR]
        self.mon = mon
        self.sx = mon["width"] / C.BASE_W
        self.sy = mon["height"] / C.BASE_H

    def _sct(self):
        if not hasattr(self._local, "sct"):
            self._local.sct = self._mss.mss()
        return self._local.sct

    def grab(self, zona):
        x1, y1, x2, y2 = zona
        box = {
            "left": self.mon["left"] + int(x1 * self.sx),
            "top": self.mon["top"] + int(y1 * self.sy),
            "width": max(1, int((x2 - x1) * self.sx)),
            "height": max(1, int((y2 - y1) * self.sy)),
        }
        img = np.asarray(self._sct().grab(box))[:, :, :3]  # BGRA -> BGR
        if self.sx != 1 or self.sy != 1:  # todo se analiza en base 1920x1080
            img = cv2.resize(img, (x2 - x1, y2 - y1), interpolation=cv2.INTER_AREA)
        return img


class FuenteVideo:
    """Reproduce un video en tiempo real para probar sin el juego (modo --video)."""

    def __init__(self, ruta):
        self.cap = cv2.VideoCapture(ruta)
        if not self.cap.isOpened():
            raise SystemExit(f"No pude abrir el video: {ruta}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.frame = None
        self.terminado = False
        self._lock = threading.Lock()
        self._leer()
        threading.Thread(target=self._loop, daemon=True).start()

    def _leer(self):
        ok, f = self.cap.read()
        if not ok:
            self.terminado = True
            return
        if f.shape[1] != C.BASE_W:
            f = cv2.resize(f, (C.BASE_W, C.BASE_H))
        with self._lock:
            self.frame = f

    def _loop(self):
        t0 = time.perf_counter()
        n = 0
        while not self.terminado:
            n += 1
            espera = t0 + n / self.fps - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            self._leer()

    def grab(self, zona):
        x1, y1, x2, y2 = zona
        with self._lock:
            return self.frame[y1:y2, x1:x2].copy()


# ============================================================ lectores del HUD
class LectorHUD:
    def __init__(self):
        self.vida_max_px = C.VIDA_ALTO_LLENO or 0

    def vida(self, img):
        """Devuelve (fraccion, px). img = recorte de ZONA_VIDA."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        rojo = ((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 150)
        filas = np.where(rojo.mean(1) > 0.5)[0]
        if len(filas) == 0:
            return 0.0, 0
        tope = C.ZONA_VIDA[1] + filas.min()
        px = C.VIDA_BASE_Y - tope + 1
        if not C.VIDA_ALTO_LLENO:
            self.vida_max_px = max(self.vida_max_px, px)  # autocalibración
        return min(1.0, px / max(1, self.vida_max_px)), px

    def estamina(self, img):
        """Devuelve (fraccion, visible). La barra se oculta cuando está llena."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        amarillo = (hsv[..., 0] > 20) & (hsv[..., 0] < 35) & (hsv[..., 1] > 120) & (hsv[..., 2] > 170)
        cols = np.where(amarillo.mean(0) > 0.5)[0]
        if len(cols) == 0:
            return 1.0, False
        ancho = cols.max() - cols.min() + 1
        return min(1.0, ancho / C.ESTAMINA_ANCHO_LLENO), True

    def arma(self, img):
        """Fracción de durabilidad (barra blanca; cuenta también amarillo/rojo si cambia de color)."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        blanco = (hsv[..., 1] < 60) & (hsv[..., 2] > 200)
        color = (hsv[..., 1] > 120) & (hsv[..., 2] > 170) & ((hsv[..., 0] < 35) | (hsv[..., 0] > 170))
        cols = np.where((blanco | color).mean(0) > 0.5)[0]
        return min(1.0, len(cols) / C.ARMA_ANCHO_LLENO)


class DetectorGolpe:
    """Movimiento en la zona del enemigo, ignorando el pasto (verde) que se mueve con el viento.

    Compara contra un frame de hace >= 50 ms, así el valor no depende de los FPS de captura.
    """

    def __init__(self, ventana=0.05):
        self.ventana = ventana
        self.hist = []  # (t, gris, mascara_pasto)

    def medir(self, img, t):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        pasto = (hsv[..., 0] > 30) & (hsv[..., 0] < 90) & (hsv[..., 1] > 60)
        g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        ref = None
        while self.hist and t - self.hist[0][0] >= self.ventana:
            ref = self.hist.pop(0)  # el más nuevo de los que ya tienen >= 50 ms
        if ref is not None:
            self.hist.insert(0, ref)
        self.hist.append((t, g, pasto))
        if ref is None:
            return 0.0
        d = cv2.absdiff(g, ref[1]).astype(np.float32)
        d[pasto & ref[2]] = 0  # era pasto y sigue siendo pasto: no cuenta
        return float(d.mean())


class DetectorCombate:
    """Lee los textos flotantes del juego alrededor del jugador (ZONA_TEXTOS).

    - "Blocked: X" blanco       -> el golpe pegó en el arma/escudo (bloqueo)
    - bloqueo + cúpula que aclara toda la zona -> parry
    - número rojo sin "Blocked" -> golpe recibido sin bloquear
    - número blanco (tu daño)   -> golpe tuyo que entró; si el enemigo está aturdido por un parry: potenciado
    """

    def __init__(self):
        import collections
        import os
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantillas")
        self.tpl_blocked = cv2.imread(os.path.join(base, "blocked.png"), cv2.IMREAD_GRAYSCALE)
        self.tpl_twig = cv2.imread(os.path.join(base, "twig.png"), cv2.IMREAD_GRAYSCALE)
        self.brillos = collections.deque(maxlen=90)       # (t, brillo medio) para la base de la cúpula
        self.t_blocked = self.t_rojo = self.t_blanco = -9.0
        self.bloqueo_pend = None                          # (t, base) esperando saber si es parry
        self.rojo_pend = None                             # t de un número rojo aún sin clasificar
        self.t_parry = -9.0
        self.cupula = 0.0                                 # último aclarado medido (para el panel)
        self.pos_blocked = (0, 0, -9.0)                   # dónde y cuándo se vio el "Blocked" (para taparlo)

    @staticmethod
    def _componentes(mascara, alto=(7, 22), ancho=(3, 18), area=12):
        n, _, st, _ = cv2.connectedComponentsWithStats(mascara, 8)
        return [tuple(st[k][:4]) for k in range(1, n)
                if alto[0] <= st[k][3] <= alto[1] and ancho[0] <= st[k][2] <= ancho[1] and st[k][4] >= area]

    @staticmethod
    def _hay_numero(ds):
        """≥3 dígitos alineados: misma altura y renglón, separados como letras (los brillos quedan desparramados)."""
        for a in ds:
            fila = sorted((b for b in ds if abs(b[1] - a[1]) <= 2 and abs(b[3] - a[3]) <= 2
                           and 0 <= b[0] - a[0] <= 45), key=lambda b: b[0])
            if len(fila) >= 3:
                pasos = [q[0] - p[0] for p, q in zip(fila, fila[1:])]
                if all(5 <= d <= 16 for d in pasos) and fila[-1][0] + fila[-1][2] - fila[0][0] >= 20:
                    return True
        return False

    def _match(self, gris, tpl):
        r = cv2.matchTemplate(gris, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, pos = cv2.minMaxLoc(r)
        return mx, pos

    def medir(self, img, t):
        """Devuelve la lista de eventos nuevos en este cuadro."""
        eventos = []
        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        brillo = float(gris[20:420, 20:420].mean())  # cúpula: centro de la zona (alrededor del jugador)

        # --- "Blocked"
        sb, (bx, by) = self._match(gris, self.tpl_blocked)
        hay_blocked = sb > C.UMBRAL_BLOCKED
        if hay_blocked:
            if t - self.t_blocked > C.TEXTO_REFRACTARIO:
                viejos = [b for (tt, b) in self.brillos if tt <= t - C.CUPULA_BASE_ATRAS]
                self.bloqueo_pend = (t, viejos[-1] if viejos else brillo)
                self.rojo_pend = None  # el rojo de este golpe es daño que pasa el bloqueo, no un golpe limpio
            self.t_blocked = t
        if sb > 0.36:  # también mientras se desvanece o queda cortado en el borde
            self.pos_blocked = (bx, by, t)
        self.brillos.append((t, brillo))

        # --- ¿el bloqueo pendiente es parry? (la cúpula aclara toda la zona)
        if self.bloqueo_pend:
            t0, base = self.bloqueo_pend
            self.cupula = max(self.cupula if t - t0 > 0 else 0.0, brillo - base)
            if brillo - base >= C.UMBRAL_CUPULA:
                eventos.append("parry")
                self.t_parry, self.bloqueo_pend = t, None
            elif t - t0 > C.CUPULA_VENTANA:
                eventos.append("bloqueo")
                self.bloqueo_pend = None

        # --- números rojos (daño recibido): rojo puro, no el naranja del escudo
        rojo = (((h <= 4) | (h >= 174)) & (s >= 190) & (v >= 120)).astype(np.uint8)
        digitos_rojos = [d for d in self._componentes(rojo) if 0.35 <= d[2] / d[3] <= 1.3]
        if len(digitos_rojos) >= 2:
            if t - self.t_rojo > C.TEXTO_REFRACTARIO and t - self.t_blocked > C.TEXTO_REFRACTARIO:
                self.rojo_pend = t
            self.t_rojo = t
        if self.rojo_pend is not None:
            if t - self.t_blocked <= C.TEXTO_REFRACTARIO:
                self.rojo_pend = None            # apareció el "Blocked": era un bloqueo
            elif t - self.rojo_pend > 0.25:
                eventos.append("golpe")
                self.rojo_pend = None

        # --- números blancos (tu daño), tapando la etiqueta T.W.I.G. y el "Blocked"
        blanco = ((s < 60) & (v > 225)).astype(np.uint8)
        st, (tx, ty) = self._match(gris, self.tpl_twig)
        if st > 0.6:
            blanco[max(0, ty - 25):ty + 28, max(0, tx - 15):tx + 80] = 0
        px, py, pt = self.pos_blocked
        if t - pt <= 0.5:  # "Blocked: 0" sube flotando: tapar una franja generosa
            blanco[max(0, py - 30):py + 30, max(0, px - 15):px + 120] = 0
        numero = self._hay_numero(self._componentes(blanco, alto=(7, 16), ancho=(3, 12)))
        if numero:
            if t - self.t_blanco > C.TEXTO_REFRACTARIO:
                eventos.append("potenciado" if t - self.t_parry <= C.ATURDIDO_SEG else "dano")
            self.t_blanco = t
        return eventos


# ============================================================ imagen para la IA
def armar_imagen_ia(fuente, escala=2):
    """Pega los recortes del HUD en una sola imagen chica (PNG bytes)."""
    partes = []
    for nombre, zona in C.RECORTES_IA.items():
        img = cv2.resize(fuente.grab(zona), None, fx=escala, fy=escala, interpolation=cv2.INTER_NEAREST)
        cv2.putText(img, nombre, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        partes.append(img)
    alto = max(p.shape[0] for p in partes)
    partes = [cv2.copyMakeBorder(p, 0, alto - p.shape[0], 0, 6, cv2.BORDER_CONSTANT) for p in partes]
    lienzo = np.hstack(partes)
    ok, png = cv2.imencode(".png", lienzo)
    return png.tobytes()
