"""Configuración del bot. Todo lo ajustable está acá.

Las coordenadas están en base 1920x1080 (medidas sobre tu video).
Si jugás a otra resolución se escalan solas, pero conviene correr
calibrar.py y revisar la imagen que genera.
"""

# ---------------------------------------------------------------- pantalla
BASE_W, BASE_H = 1920, 1080
MONITOR = 1                     # 1 = monitor principal (mss)
TITULO_VENTANA = "valheim"      # solo manda teclas si esta ventana está al frente

# Zonas (x1, y1, x2, y2)
ZONA_ENEMIGO = (840, 380, 1100, 560)   # donde se detecta el golpe del enemigo
ZONA_VIDA = (100, 780, 112, 1000)      # franja vertical de la barra roja
VIDA_BASE_Y = 997                      # borde inferior de la barra roja
ZONA_GRABAR = (600, 250, 1320, 1000)   # lo que filma --grabar (enemigo + jugador + estamina)
ZONA_ESTAMINA =(840, 926, 1080, 938)  # franja horizontal de la barra amarilla
ZONA_ARMA = (112, 98, 182, 104)        # barrita blanca de durabilidad (slot 2)

# Recortes que se le mandan a la IA (se pegan en una sola imagen)
RECORTES_IA = {
    "vida_y_comida": (45, 800, 210, 1000),
    "arma": (110, 40, 185, 110),
    "estamina": (880, 915, 1040, 950),
}

# Tamaños "llenos" para pasar de píxeles a porcentaje
ESTAMINA_ANCHO_LLENO = 111   # px; si no se ve la barra = 100 %
ARMA_ANCHO_LLENO = 52        # px con el arma nueva
VIDA_ALTO_LLENO = 0          # px de la barra con vida llena; 0 = autocalibrar (máximo visto)

# ---------------------------------------------------------------- combate (OpenCV)
FPS_COMBATE = 60             # vueltas por segundo del detector
UMBRAL_MOVIMIENTO = 3.0      # movimiento del enemigo (sin contar pasto) que dispara el bloqueo
# textos flotantes del juego (DetectorCombate, calibrado con etiquetas.mp4)
ZONA_TEXTOS = (740, 280, 1180, 780)  # alrededor del jugador: "Blocked", números rojos y de daño
UMBRAL_BLOCKED = 0.5         # parecido con la plantilla "Blocked" (sin texto: <0.33, con texto: 0.6-1.0)
UMBRAL_CUPULA = 13.0         # cuánto se aclara la zona tras el bloqueo = parry (bloqueo 0-11.9, parry 13.4-18.2)
CUPULA_BASE_ATRAS = 0.35     # s antes del "Blocked" que se toman como brillo base
CUPULA_VENTANA = 0.45        # s para esperar la cúpula antes de decidir "bloqueo normal"
TEXTO_REFRACTARIO = 0.9      # s: el mismo texto flotando no cuenta dos veces
ATURDIDO_SEG = 2.0           # s tras un parry en que tu golpe cuenta como potenciado
BLOQUEO_DURACION = 0.70      # s que se mantiene el bloqueo tras detectar movimiento
BLOQUEO_MAX = 2.5            # s máximos de bloqueo seguido antes de dejar lugar a un ataque
ESTRATEGIA_BLOQUEO = "reactivo"  # "reactivo" (bloquea al detectar) o "mantener" (siempre apretado, sin atacar)

ATAQUE_INTERVALO = 1.2       # s mínimos entre ataques propios
CONTRAATAQUE_RETRASO = 0.25  # s después de bloquear un golpe para contraatacar
CALMA_ANTES_DE_ATACAR = 0.5  # s sin movimiento del enemigo para atacar "en frío"
ATAQUE_MAX_ESPERA = 4.0      # si pasa esto sin atacar, ataca igual (enemigo que no para de moverse)
IGNORAR_TRAS_ATAQUE = 0.35   # s que se ignora el movimiento causado por tu propio golpe

TECLA_COMIDA = "6"           # slot de la barra rápida con comida (None = no come)
COMER_COOLDOWN = 60          # s mínimos entre comidas

# ---------------------------------------------------------------- IA (Ollama)
OLLAMA_URL = "http://localhost:11434/api/chat"
MODELO_IA = "moondream"      # entra en 3 GB. Alternativas: "llava-phi3", "qwen2.5vl:3b"
IA_INTERVALO = 6.0           # s entre consultas
IA_TIMEOUT = 40              # s
IA_NUM_GPU = 0           # None = Ollama decide; 0 = todo en CPU (si Valheim se traba)
FUENTE_DECISION = "ia"       # "ia" o "reglas" (se cambia en vivo con F9)

# ---------------------------------------------------------------- reglas y seguridad
VIDA_PARAR = 0.20            # por debajo: el bot se pausa y suelta todo (manda siempre)
VIDA_COMER = 0.50
ESTAMINA_MIN_ATAQUE = 0.35
ARMA_MIN = 0.15              # por debajo: deja de atacar para no romper el arma

# ---------------------------------------------------------------- teclas del bot
TECLA_PAUSA = "f8"
TECLA_FUENTE = "f9"
TECLA_SALIR = "f10"

# ---------------------------------------------------------------- panel
PANEL_SIEMPRE_ENCIMA = True
PANEL_REFRESCO_MS = 250
ARCHIVO_LOG = "sesion_log.csv"
