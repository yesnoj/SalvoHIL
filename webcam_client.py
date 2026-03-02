"""
webcam_client.py
================
Modulo client per webcam_capture_server.py

Importa questo file nel tuo codice per catturare immagini dalla webcam
e gestire gli allarmi sul display fisico via CAN:

    from webcam_client import cattura, stato_server
    from webcam_client import mostra_allarme, cancella_allarme, lista_allarmi

Requisiti:
    - webcam_capture_server.py deve essere in esecuzione
    - Il server deve avere almeno un'area configurata
    - Il server deve essere avviato (pulsante "Start Server")
    - Per i comandi alarm: alarm_can_sender.py nella stessa cartella del server
                           + python-can, cantools, driver XL Vector installati
"""

import socket


# ─────────────────────────────────────────────
#  Helper interno
# ─────────────────────────────────────────────
def _send_command(command, porta=5005):
    """Invia un comando al server e ritorna la risposta grezza (senza \\n finale)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        s.connect(('127.0.0.1', porta))
        s.sendall(f'{command}\n'.encode())
        risposta = s.recv(4096).decode().strip()
    return risposta


# ─────────────────────────────────────────────
#  Cattura immagini
# ─────────────────────────────────────────────
def cattura(area_id, nome_file, porta=5005):
    """
    Richiede al server di catturare l'area specificata e salvarla come nome_file.

    Parametri:
        area_id   (int) : ID dell'area da catturare (come configurato nella GUI del server)
        nome_file (str) : Nome o percorso del file di destinazione.
                            'misura.jpg'              → salvato nella dir configurata nel server
                            'C:/Foto/misura.jpg'      → percorso assoluto
                            'sessione1/misura.jpg'    → sottocartella relativa alla dir server
                          Formato determinato dall'estensione: .jpg .png .bmp .tiff
        porta     (int) : Porta TCP del server (default 5005)

    Ritorna:
        str : percorso completo del file salvato

    Eccezioni:
        RuntimeError        : il server ha risposto con un errore (area inesistente, webcam offline...)
        ConnectionRefusedError : il server non è in ascolto sulla porta indicata
        TimeoutError        : il server non ha risposto entro 10 secondi
    """
    risposta = _send_command(f'CAPTURE:{area_id}:{nome_file}', porta)
    if risposta.startswith('OK:'):
        return risposta[3:]
    raise RuntimeError(f"Errore dal server: {risposta}")


def stato_server(porta=5005):
    """
    Controlla se il server è raggiungibile e pronto.

    Parametri:
        porta (int) : Porta TCP del server (default 5005)

    Ritorna:
        (bool, str) : (True,  'READY:aree=[1, 2, 3]')  se il server è pronto
                      (False, 'NOT_READY:motivo')       se non è pronto
                      (False, 'messaggio errore')       se non raggiungibile
    """
    try:
        risposta = _send_command('STATUS', porta)
        return risposta.startswith('READY'), risposta
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
#  Gestione allarmi CAN
# ─────────────────────────────────────────────
def mostra_allarme(alarm_id, porta=5005):
    """
    Attiva l'allarme A-code specificato sul display fisico via CAN.

    Il server invia il segnale CAN corrispondente all'alarm_id e mantiene
    il segnale attivo fino alla chiamata di cancella_allarme().
    Se c'era già un allarme attivo, viene azzerato automaticamente prima
    di inviare il nuovo.

    Parametri:
        alarm_id (str) : Codice allarme A-code, es. "A101", "A202", "A301".
                         Case-insensitive.
        porta    (int) : Porta TCP del server (default 5005)

    Ritorna:
        str : risposta del server es. "OK:shown:A101"

    Eccezioni:
        RuntimeError : alarm_id sconosciuto, CAN non inizializzato o server non raggiungibile

    Esempio AutomationDesk:
        mostra_allarme("A101")
        time.sleep(2.0)
        path = cattura(1, "alarm_A101.png")
        cancella_allarme()
    """
    risposta = _send_command(f'SHOW_ALARM:{alarm_id}', porta)
    if not risposta.startswith('OK'):
        raise RuntimeError(f"mostra_allarme({alarm_id}) fallito: {risposta}")
    return risposta


def cancella_allarme(porta=5005):
    """
    Azzera il segnale CAN dell'ultimo allarme attivato con mostra_allarme().

    Non solleva eccezioni se non c'era nessun allarme attivo.

    Parametri:
        porta (int) : Porta TCP del server (default 5005)
    """
    _send_command('CLEAR_ALARM', porta)


def lista_allarmi(porta=5005):
    """
    Ritorna la lista degli A-code supportati dal server.

    Utile per verificare quali codici sono disponibili prima di eseguire
    un test, o per enumerarli in AutomationDesk.

    Parametri:
        porta (int) : Porta TCP del server (default 5005)

    Ritorna:
        list[str] : es. ['A001', 'A002', 'A005', ..., 'A503']
                    Lista vuota se il modulo CAN non è disponibile.
    """
    try:
        risposta = _send_command('LIST_ALARMS', porta)
        if risposta.startswith('OK:'):
            return risposta[3:].split(',')
    except Exception:
        pass
    return []
