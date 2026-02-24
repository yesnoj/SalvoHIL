"""
esempio_utilizzo.py
====================
Esempi pratici di utilizzo di webcam_client.py

Esegui questo file per vedere tutti i casi d'uso:
    python esempio_utilizzo.py

Oppure copia il singolo esempio che ti serve nel tuo codice.
"""

import os
import time
from webcam_client import cattura, stato_server


# ─────────────────────────────────────────────
#  Verifica connessione al server
# ─────────────────────────────────────────────
print("=== Esempi utilizzo Webcam Client ===\n")

print("Verifico connessione al server...")
pronto, msg = stato_server()
if not pronto:
    print(f"[ERRORE] Server non pronto: {msg}")
    print("Avvia webcam_capture_server.py, configura le aree e clicca 'Start Server'")
    exit(1)
print(f"[OK] {msg}\n")


# ─────────────────────────────────────────────
#  Esempio 1 — Cattura singola
# ─────────────────────────────────────────────
print("--- Esempio 1: cattura singola ---")

percorso = cattura(area_id=1, nome_file="misura_area1.jpg")
print(f"  [OK] Area 1 salvata in: {percorso}")


# ─────────────────────────────────────────────
#  Esempio 2 — Cattura più aree in sequenza
# ─────────────────────────────────────────────
print("\n--- Esempio 2: cattura più aree ---")

timestamp = time.strftime("%Y%m%d_%H%M%S")
aree_da_catturare = [1, 2, 3]   # ← modifica con gli ID che hai configurato nel server

for area_id in aree_da_catturare:
    nome = f"campione_area{area_id}_{timestamp}.jpg"
    try:
        percorso = cattura(area_id=area_id, nome_file=nome)
        print(f"  [OK] Area {area_id} → {percorso}")
    except RuntimeError as e:
        print(f"  [SKIP] Area {area_id} → {e}")   # area non configurata nel server


# ─────────────────────────────────────────────
#  Esempio 3 — Percorso assoluto e formato PNG
# ─────────────────────────────────────────────
print("\n--- Esempio 3: percorso assoluto e formato PNG ---")

cartella = os.path.join(os.path.expanduser("~"), "Desktop", "misurazioni")
os.makedirs(cartella, exist_ok=True)

percorso = cattura(
    area_id=1,
    nome_file=os.path.join(cartella, f"area1_{timestamp}.png")
)
print(f"  [OK] Salvato come PNG in: {percorso}")


# ─────────────────────────────────────────────
#  Esempio 4 — Acquisizione periodica
# ─────────────────────────────────────────────
print("\n--- Esempio 4: acquisizione periodica (5 volte, ogni 2 secondi) ---")

for i in range(1, 6):
    nome = f"periodica_{i:03d}_{time.strftime('%H%M%S')}.jpg"
    try:
        percorso = cattura(area_id=1, nome_file=nome)
        print(f"  [{i}/5] Salvata: {percorso}")
    except Exception as e:
        print(f"  [{i}/5] Errore: {e}")
    if i < 5:
        time.sleep(2)


print("\n=== Fine esempi ===")
