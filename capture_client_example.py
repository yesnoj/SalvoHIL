"""
capture_client_example.py
==========================
Esempio di client per webcam_capture_server.py

PROTOCOLLO:
  CAPTURE:area_id:nome_file\n  →  OK:/percorso/completo\n  oppure  ERROR:messaggio\n
  STATUS\n                      →  READY:aree=[1,2,...]\n  oppure  NOT_READY:motivo\n
"""

import socket
import os
import time


# ─────────────────────────────────────────────
#  Funzione principale da copiare nel tuo codice
# ─────────────────────────────────────────────

def cattura(area_id, nome_file, porta=5005):
    """
    Richiede al server di catturare l'area specificata e salvarla come nome_file.

    Parametri:
        area_id  (int) : ID dell'area da catturare (come configurato nella GUI del server)
        nome_file (str): Nome del file di destinazione.
                         - Solo nome:          'misura.jpg'        → salvato nella dir del server
                         - Percorso assoluto:  'C:/Foto/misura.jpg' → salvato esattamente lì
                         - Sottocartella:      'sessione1/misura.jpg'
                         Il formato è determinato dall'estensione: .jpg .png .bmp .tiff
        porta    (int) : Porta TCP del server (default 5005)

    Ritorna:
        str: percorso completo del file salvato

    Eccezioni:
        RuntimeError: se il server risponde con un errore
        ConnectionRefusedError: se il server non è in ascolto
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        s.connect(('127.0.0.1', porta))
        s.sendall(f'CAPTURE:{area_id}:{nome_file}\n'.encode())
        risposta = s.recv(1024).decode().strip()

    if risposta.startswith('OK:'):
        return risposta[3:]   # percorso completo del file salvato
    raise RuntimeError(f"Errore dal server: {risposta}")


def stato_server(porta=5005):
    """
    Controlla se il server è pronto e restituisce le aree configurate.

    Ritorna:
        (bool, str): (True, 'READY:aree=[1,2]') oppure (False, 'NOT_READY:motivo')
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(('127.0.0.1', porta))
            s.sendall(b'STATUS\n')
            risposta = s.recv(1024).decode().strip()
        return risposta.startswith('READY'), risposta
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
#  Esempi di utilizzo
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Esempio Client Webcam Capture Server ===\n")

    # ── 1. Verifica connessione ───────────────────────────────────────────────
    print("Verifico connessione al server...")
    pronto, msg = stato_server()
    if not pronto:
        print(f"[ERRORE] Server non pronto: {msg}")
        print("Avvia webcam_capture_server.py, configura le aree e clicca 'Start Server'")
        exit(1)
    print(f"[OK] {msg}\n")

    # ── 2. Cattura singola area ───────────────────────────────────────────────
    print("--- Esempio 1: cattura singola ---")
    try:
        percorso = cattura(area_id=1, nome_file="misura_area1.jpg")
        print(f"  [OK] Area 1 salvata in: {percorso}")
    except Exception as e:
        print(f"  [ERRORE] {e}")

    print()

    # ── 3. Cattura più aree in sequenza ──────────────────────────────────────
    print("--- Esempio 2: cattura tutte le aree ---")
    aree_da_catturare = [1, 2, 3]   # ← modifica con gli ID che hai configurato

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    for area_id in aree_da_catturare:
        nome = f"campione_area{area_id}_{timestamp}.jpg"
        try:
            percorso = cattura(area_id=area_id, nome_file=nome)
            print(f"  [OK] Area {area_id} → {percorso}")
        except RuntimeError as e:
            print(f"  [SKIP] Area {area_id} → {e}")   # es. area non configurata

    print()

    # ── 4. Cattura in un percorso specifico ──────────────────────────────────
    print("--- Esempio 3: percorso assoluto e formato PNG ---")
    cartella = os.path.join(os.path.expanduser("~"), "Desktop", "misurazioni")
    os.makedirs(cartella, exist_ok=True)

    try:
        nome_png = os.path.join(cartella, f"area1_{timestamp}.png")
        percorso = cattura(area_id=1, nome_file=nome_png)
        print(f"  [OK] Salvato come PNG in: {percorso}")
    except Exception as e:
        print(f"  [ERRORE] {e}")

    print()

    # ── 5. Loop acquisizione continua ────────────────────────────────────────
    print("--- Esempio 4: acquisizione periodica (5 volte, ogni 2 secondi) ---")
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
