"""
webcam_client.py
================
Modulo client per webcam_capture_server.py

Importa questo file nel tuo codice per catturare immagini dalla webcam:

    from webcam_client import cattura, stato_server

Requisiti:
    - webcam_capture_server.py deve essere in esecuzione
    - Il server deve avere almeno un'area configurata
    - Il server deve essere avviato (pulsante "Start Server")
"""

import socket


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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        s.connect(('127.0.0.1', porta))
        s.sendall(f'CAPTURE:{area_id}:{nome_file}\n'.encode())
        risposta = s.recv(1024).decode().strip()

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
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(('127.0.0.1', porta))
            s.sendall(b'STATUS\n')
            risposta = s.recv(1024).decode().strip()
        return risposta.startswith('READY'), risposta
    except Exception as e:
        return False, str(e)
