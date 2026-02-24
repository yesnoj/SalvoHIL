"""
capture_client_example.py
==========================
Esempio di come il software esterno deve richiamare webcam_capture_server.py
per acquisire un'immagine.

UTILIZZO:
---------
1. Avvia prima webcam_capture_server.py e configura webcam + area + server
2. Usa le funzioni di questo modulo nel tuo codice Python

INSTALLAZIONE DIPENDENZE (solo per webcam_capture_server.py):
    pip install opencv-python Pillow
"""

import socket
import time


# ─────────────────────────────────────────────
#  Configurazione connessione
# ─────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5005           # deve corrispondere alla porta settata nel server
TIMEOUT_SECONDS = 10         # timeout per la risposta del server


# ─────────────────────────────────────────────
#  Funzioni di interfaccia
# ─────────────────────────────────────────────
def capture_image(filename: str, host: str = SERVER_HOST, port: int = SERVER_PORT) -> str:
    """
    Richiede al server di acquisire un frame e salvarlo con il nome indicato.

    Args:
        filename:   Nome file (es. "misura_001.jpg") o percorso assoluto.
                    Se è un percorso relativo, viene salvato nella directory
                    configurata nel server.
        host:       Indirizzo del server (default: localhost)
        port:       Porta del server (default: 5005)

    Returns:
        Il percorso completo dell'immagine salvata (stringa).

    Raises:
        ConnectionRefusedError: Se il server non è in ascolto.
        TimeoutError:           Se il server non risponde entro il timeout.
        RuntimeError:           Se il server risponde con un errore.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(TIMEOUT_SECONDS)
        s.connect((host, port))
        s.sendall(f"CAPTURE:{filename}\n".encode())

        # Ricevi la risposta
        data = b""
        while b"\n" not in data:
            chunk = s.recv(1024)
            if not chunk:
                break
            data += chunk

    response = data.decode(errors="replace").strip()

    if response.startswith("OK:"):
        return response[3:]   # percorso del file salvato
    elif response.startswith("ERROR:"):
        raise RuntimeError(f"Server error: {response[6:]}")
    else:
        raise RuntimeError(f"Risposta inattesa: {response!r}")


def check_server_ready(host: str = SERVER_HOST, port: int = SERVER_PORT) -> bool:
    """
    Verifica se il server è pronto (webcam aperta + area configurata).

    Returns:
        True se pronto, False altrimenti.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((host, port))
            s.sendall(b"STATUS\n")
            data = s.recv(1024)
        response = data.decode(errors="replace").strip()
        return response == "READY"
    except Exception:
        return False


# ─────────────────────────────────────────────
#  Esempio di utilizzo completo
# ─────────────────────────────────────────────
def esempio_utilizzo():
    """
    Dimostra come usare il client nel tuo codice di elaborazione.
    Sostituisci questa funzione con la tua logica applicativa.
    """

    print("=== Esempio Client Webcam Capture ===\n")

    # 1. Verifica che il server sia pronto
    print("Verifico connessione al server...")
    if not check_server_ready():
        print("[ERRORE] Server non raggiungibile o non configurato.")
        print("         Assicurati che webcam_capture_server.py sia avviato")
        print("         e che webcam + area siano configurate prima di premere 'Start Server'.")
        return

    print("[OK] Server pronto!\n")

    # 2. Esempio: ciclo di acquisizioni con nome dinamico
    for i in range(3):
        # Genera un nome dinamico (timestamp + indice)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"campione_{i+1:03d}_{timestamp}.jpg"

        print(f"Acquisizione {i+1}/3 → {filename}")

        try:
            saved_path = capture_image(filename)
            print(f"  ✅ Salvata in: {saved_path}")

        except ConnectionRefusedError:
            print("  ❌ Server non in ascolto. Uscita.")
            break
        except RuntimeError as e:
            print(f"  ❌ Errore: {e}")
        except Exception as e:
            print(f"  ❌ Eccezione: {e}")

        # Pausa tra acquisizioni (simula l'elaborazione del software esterno)
        if i < 2:
            time.sleep(1.0)

    print("\n=== Fine esempio ===")


# ─────────────────────────────────────────────
#  Versione minima da integrare nel tuo codice
# ─────────────────────────────────────────────
def integrazione_minima_esempio():
    """
    Versione compatta da copiare nel tuo software.
    """
    import socket

    def cattura(nome_file, porta=5005):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect(('127.0.0.1', porta))
            s.sendall(f'CAPTURE:{nome_file}\n'.encode())
            risposta = s.recv(1024).decode().strip()
        if risposta.startswith('OK:'):
            return risposta[3:]
        raise RuntimeError(risposta)

    # Nel tuo workflow:
    # percorso = cattura("misura_pannello_001.jpg")
    # ... elabora l'immagine in percorso ...


if __name__ == "__main__":
    esempio_utilizzo()
