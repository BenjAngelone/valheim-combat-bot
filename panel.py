"""Panel liviano en Tkinter (viene con Python, sin dependencias extra)."""
import time
import tkinter as tk

import config as C

INDICADOR_SEG = 1.2  # cuánto queda prendido el indicador verde
BG, CARD, TXT, MUTED = "#15171c", "#1e2128", "#e6e6e6", "#8a8f98"
ROJO, AMARILLO, AZUL, VERDE, NARANJA = "#e0524f", "#e8c547", "#6aa9ff", "#5bc07a", "#f0934a"
FUENTE = ("Segoe UI", 10)
MONO = ("Consolas", 9)


class Panel:
    def __init__(self, estado, debe_seguir):
        self.e, self.debe_seguir = estado, debe_seguir
        self.r = tk.Tk()
        self.r.title(f"Valheim · IA ({C.MODELO_IA})")
        self.r.configure(bg=BG)
        # borde derecho: a la izquierda tapa la barra de vida, en el centro al enemigo
        self.r.geometry(f"400x900+{self.r.winfo_screenwidth() - 410}+150")
        self.r.attributes("-topmost", C.PANEL_SIEMPRE_ENCIMA)
        self.r.protocol("WM_DELETE_WINDOW", self._cerrar)
        self._foto = None
        self._img_ultima = None

        self.lbl_estado = self._label(self.r, "", ("Segoe UI", 13, "bold"), pady=(10, 0))
        self._label(self.r, f"IA: {C.MODELO_IA}", ("Segoe UI", 11, "bold"), fg=AZUL)
        self.lbl_modo = self._label(self.r, "", FUENTE, fg=MUTED)

        # indicador de bloqueo / contraataque: se prende en verde unos instantes
        self.lbl_golpe = tk.Label(self.r, text="", font=("Segoe UI", 12, "bold"), height=2)
        self.lbl_golpe.pack(fill="x", padx=10, pady=(6, 0))

        c = self._card("Personaje")
        self.barras = {n: self._barra(c, n, col) for n, col in
                       (("Vida", ROJO), ("Estamina", AMARILLO), ("Arma", AZUL))}

        c = self._card("Detector de golpes (OpenCV)")
        self.cv_mov = tk.Canvas(c, width=360, height=60, bg=BG, highlightthickness=0)
        self.cv_mov.pack(pady=(2, 4))
        self.lbl_combate = self._label(c, "", MONO, anchor="w")

        c = self._card("IA local")
        self.cv_img = tk.Label(c, bg=CARD)
        self.cv_img.pack(pady=2)
        self.lbl_ia = self._label(c, "", MONO, anchor="w")
        self.lbl_crudo = self._label(c, "", ("Consolas", 8), fg=MUTED, anchor="w", wrap=360)

        c = self._card("Registro")
        self.txt = tk.Text(c, height=12, width=58, bg=BG, fg=TXT, font=("Consolas", 8),
                           relief="flat", wrap="none")
        self.txt.pack(fill="x")

        self._label(self.r, f"{C.TECLA_PAUSA.upper()} pausa · {C.TECLA_FUENTE.upper()} IA/reglas · "
                    f"{C.TECLA_SALIR.upper()} salir", ("Segoe UI", 8), fg=MUTED, pady=(4, 8))

    # ---------------------------------------------------------- helpers de UI
    def _label(self, padre, texto, font, fg=TXT, anchor="center", pady=0, wrap=0):
        bg = padre.cget("bg")
        l = tk.Label(padre, text=texto, font=font, fg=fg, bg=bg, anchor=anchor,
                     justify="left", wraplength=wrap)
        l.pack(fill="x", pady=pady, padx=2)
        return l

    def _card(self, titulo):
        f = tk.Frame(self.r, bg=CARD, padx=10, pady=6)
        f.pack(fill="x", padx=10, pady=5)
        tk.Label(f, text=titulo.upper(), font=("Segoe UI", 8, "bold"), fg=MUTED, bg=CARD,
                 anchor="w").pack(fill="x")
        return f

    def _barra(self, padre, nombre, color):
        fila = tk.Frame(padre, bg=CARD)
        fila.pack(fill="x", pady=2)
        tk.Label(fila, text=nombre, width=8, anchor="w", font=FUENTE, fg=TXT, bg=CARD).pack(side="left")
        cv = tk.Canvas(fila, width=230, height=12, bg=BG, highlightthickness=0)
        cv.pack(side="left")
        rect = cv.create_rectangle(0, 0, 0, 12, fill=color, width=0)
        lbl = tk.Label(fila, text="", width=5, anchor="e", font=FUENTE, fg=TXT, bg=CARD)
        lbl.pack(side="left")
        return cv, rect, lbl

    def _set_barra(self, nombre, frac, extra=""):
        cv, rect, lbl = self.barras[nombre]
        cv.coords(rect, 0, 0, 230 * max(0.0, min(1.0, frac)), 12)
        lbl.config(text=f"{frac:.0%}{extra}")

    # ---------------------------------------------------------- refresco
    def _refrescar(self):
        if not self.debe_seguir():
            self.r.destroy()
            return
        e = self.e
        if e.pausado:
            self.lbl_estado.config(text="⏸  EN PAUSA", fg=NARANJA)
        elif not e.ventana_ok:
            self.lbl_estado.config(text="…  esperando ventana de Valheim", fg=NARANJA)
        else:
            self.lbl_estado.config(text="●  ENTRENANDO", fg=VERDE)
        self.lbl_modo.config(text=f"modo: {e.modo}  ·  decide: {e.fuente}\nbloqueo: {C.ESTRATEGIA_BLOQUEO}")

        ahora = time.time()
        if ahora - e.t_contra < INDICADOR_SEG:
            self.lbl_golpe.config(text="⚡ ATAQUE POTENCIADO", bg=VERDE, fg=BG)
        elif ahora - e.t_parry < INDICADOR_SEG:
            self.lbl_golpe.config(text="✨ PARRY", bg=VERDE, fg=BG)
        elif ahora - e.t_bloqueo < INDICADOR_SEG:
            self.lbl_golpe.config(text="🛡 BUEN BLOQUEO", bg=VERDE, fg=BG)
        elif ahora - e.t_golpe < INDICADOR_SEG:
            self.lbl_golpe.config(text="💥 GOLPE RECIBIDO", bg=ROJO, fg=BG)
        else:
            self.lbl_golpe.config(text=f"bloqueos {e.bloqueos} · parrys {e.parrys} · potenciados {e.contras}"
                                       f" · recibidos {e.golpes}", bg=CARD, fg=MUTED)

        self._set_barra("Vida", e.vida)
        self._set_barra("Estamina", e.estamina, "" if e.est_visible else "*")
        self._set_barra("Arma", e.arma)

        # gráfico de movimiento con umbral y marcas de bloqueo
        cv = self.cv_mov
        cv.delete("all")
        mov, marcas = list(e.movimiento), list(e.marcas_bloqueo)
        tope = max(C.UMBRAL_MOVIMIENTO * 3, max(mov) if mov else 1)
        paso = 360 / max(1, len(mov) - 1)
        y = lambda v: 58 - 54 * min(v, tope) / tope
        yu = y(C.UMBRAL_MOVIMIENTO)
        cv.create_line(0, yu, 360, yu, fill=NARANJA, dash=(3, 3))
        pts = [c for i, v in enumerate(mov) for c in (i * paso, y(v))]
        if len(pts) >= 4:
            cv.create_line(*pts, fill=AZUL)
        for i, m in enumerate(marcas):
            if m:
                cv.create_line(i * paso, 0, i * paso, 60, fill=VERDE if m == 1 else ROJO)
        self.lbl_combate.config(text=(
            f"reacciones {e.reacciones} · bloqueados {e.bloqueos} · ataques {e.ataques} · aciertos {e.aciertos}\n"
            f"comidas {e.comidas}  (verde=bloqueo, rojo=ataque)\n"
            f"cúpula último bloqueo +{e.cupula:.0f} (parry desde +{C.UMBRAL_CUPULA:.0f})\n"
            f"loop {e.fps_combate:.0f} fps · {e.ms_combate:.1f} ms · HUD {e.ms_hud:.1f} ms"))

        # IA
        if e.ia_imagen and e.ia_imagen is not self._img_ultima:
            self._img_ultima = e.ia_imagen
            self._foto = tk.PhotoImage(data=e.ia_imagen)
            self.cv_img.config(image=self._foto)
        n = max(1, e.ia_consultas)
        self.lbl_ia.config(text=(
            f"IA: {e.decision_ia:<14} reglas: {e.decision_reglas}\n"
            f"latencia {e.ia_lat_ultima:5.0f} ms · prom {e.ia_lat_total / n:5.0f} ms\n"
            f"consultas {e.ia_consultas} · errores {e.ia_errores} · "
            f"acuerdo {100 * e.ia_acuerdos / n:3.0f}%"))
        self.lbl_crudo.config(text=f"{C.MODELO_IA}: {e.ia_respuesta}")

        with e.lock:
            lineas = list(e.logs)[-12:]
        self.txt.delete("1.0", "end")
        self.txt.insert("end", "\n".join(lineas))

        self.r.after(C.PANEL_REFRESCO_MS, self._refrescar)

    def _cerrar(self):
        self.e.corriendo = False

    def run(self):
        self._refrescar()
        self.r.mainloop()
