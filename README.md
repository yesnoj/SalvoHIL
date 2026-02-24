# Webcam Capture Server

Sistema di acquisizione immagini da webcam con GUI di configurazione e server socket TCP.
Permette a qualsiasi script Python esterno di richiedere la cattura di una o più aree dell'immagine con una singola riga di codice.

---

## Struttura del progetto

```
webcam_capture_server.py     # Server principale con GUI
capture_client_example.py    # Esempio di client con tutti i casi d'uso
```

---

## Requisiti

- Python 3.8 o superiore
- Tkinter (incluso nella distribuzione standard di Python)

```bash
pip install opencv-python Pillow
```

---

## Avvio

```bash
python webcam_capture_server.py
```

L'applicazione si apre automaticamente **a schermo intero**.

> Su Linux/Mac, se lo schermo intero non funziona, sostituire `self.root.state("zoomed")` con `self.root.attributes("-zoomed", True)` nel sorgente.

---

## Configurazione guidata

Segui questo ordine nella GUI:

1. Seleziona la **camera** dal menu a tendina (Webcam 0, 1, 2...)
2. Scegli la **risoluzione** (640×480 / 1280×720 / 1920×1080)
3. Regola i **parametri webcam** con gli slider (contrasto, saturazione, esposizione, focus)
4. Clicca **▶ Start Live View** per vedere l'anteprima in tempo reale
5. Configura le **aree di acquisizione** (vedi sezione dedicata)
6. Verifica il campo **Directory Salvataggio**
7. Clicca **▶ Start Server** → lo stato diventa `● Online (porta 5005)`
8. Testa con il bottone **📷 Cattura ora** prima di usare il client

---

## Aree di acquisizione

È possibile definire un numero illimitato di aree indipendenti, ognuna con il proprio ID numerico e rotazione.

### Come aggiungere un'area

1. Scegli la **Rotazione** dal menu (`0°` / `90°` / `180°` / `270°`) — verrà applicata al momento del salvataggio
2. Clicca **✏ Aggiungi Area**
3. Il cursore diventa una **croce** sull'anteprima
4. **Trascina** per disegnare il rettangolo → rettangolo blu in tempo reale
5. **Rilascia** per confermare → il rettangolo diventa verde con il numero area

L'ID viene assegnato automaticamente in sequenza (1, 2, 3...).  
Ogni area mostra sull'anteprima: `Area 1  90deg  320x240`

### Gestione aree

| Azione | Come |
|---|---|
| Aggiungere | ✏ Aggiungi Area + disegna sull'anteprima |
| Rimuovere una | Seleziona dalla lista → 🗑 Rimuovi |
| Rimuovere tutte | Rimuovi tutte le aree |
| Rotazione | Scelta prima di aggiungere l'area (per area) |

---

## Protocollo socket

Comunicazione via **TCP su localhost**, porta `5005` (configurabile dalla GUI).  
Comandi in testo terminati da `\n`.

| Comando | Risposta successo | Risposta errore |
|---|---|---|
| `CAPTURE:area_id:nome_file.jpg\n` | `OK:/percorso/completo/file.jpg\n` | `ERROR:messaggio\n` |
| `STATUS\n` | `READY:aree=[1, 2, 3]\n` | `NOT_READY:motivo\n` |

### Formati immagine supportati

Il formato è determinato dall'estensione del nome file:

| Estensione | Formato |
|---|---|
| `.jpg` / `.jpeg` | JPEG compresso |
| `.png` | PNG lossless |
| `.bmp` | Bitmap |
| `.tiff` | TIFF |

---

## Integrazione nel tuo codice Python

### Funzione minima da copiare

```python
import socket

def cattura(area_id, nome_file, porta=5005):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        s.connect(('127.0.0.1', porta))
        s.sendall(f'CAPTURE:{area_id}:{nome_file}\n'.encode())
        risposta = s.recv(1024).decode().strip()
    if risposta.startswith('OK:'):
        return risposta[3:]   # percorso completo del file salvato
    raise RuntimeError(f"Errore dal server: {risposta}")
```

### Esempi di utilizzo

```python
# Cattura area 1 → salvata nella directory configurata nella GUI
percorso = cattura(1, 'misura.jpg')

# Cattura area 2 → salvata in percorso assoluto
percorso = cattura(2, 'C:/Risultati/misura.png')

# Cattura area 3 → in sottocartella relativa alla dir del server
percorso = cattura(3, 'sessione_A/misura.jpg')

# Cattura più aree in sequenza
import time
timestamp = time.strftime("%Y%m%d_%H%M%S")
for area_id in [1, 2, 3]:
    cattura(area_id, f'area{area_id}_{timestamp}.jpg')
```

### Verifica stato server prima di catturare

```python
import socket

def stato_server(porta=5005):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(('127.0.0.1', porta))
            s.sendall(b'STATUS\n')
            risposta = s.recv(1024).decode().strip()
        return risposta.startswith('READY'), risposta
    except Exception as e:
        return False, str(e)

pronto, msg = stato_server()
if pronto:
    print(f"Server pronto, {msg}")   # es. READY:aree=[1, 2, 3]
else:
    print(f"Server non disponibile: {msg}")
```

---

## Architettura interna

```
┌─────────────────────────────────────────────────────────────┐
│                  webcam_capture_server.py                   │
│                                                             │
│  [Grabber Thread]  cap.read() continuo → latest_frame      │
│                              ↓                              │
│  [GUI Thread]      Live View legge latest_frame  (~20fps)  │
│                    Selezione aree via mouse sull'anteprima  │
│                              ↓                              │
│  [Server Thread]   Ascolta su TCP 127.0.0.1:5005           │
│                    CAPTURE:id:file → latest_frame           │
│                             → crop ROI → rotazione → salva │
└─────────────────────────────────────────────────────────────┘
                    ↑ TCP localhost
┌─────────────────────────────────────────────────────────────┐
│         capture_client_example.py  (o tuo script)          │
│         cattura(area_id=1, nome_file='misura.jpg')         │
└─────────────────────────────────────────────────────────────┘
```

### Thread e thread-safety

| Thread | Ruolo |
|---|---|
| **Grabber** | Legge continuamente da `cap.read()`, aggiorna `latest_frame` via `frame_lock` |
| **GUI (Tkinter)** | Live view a ~20fps, gestione slider e selezione aree via mouse |
| **Server** | Ascolta su socket TCP; ogni richiesta viene gestita in un sotto-thread |

I lock `cam_lock` (accesso webcam) e `frame_lock` (lettura/scrittura `latest_frame`) garantiscono l'assenza di race condition. Live View e Server possono girare contemporaneamente senza conflitti.

---

## Parametri webcam

Tutti regolabili in tempo reale dagli slider senza riavviare:

| Parametro | Range | Note |
|---|---|---|
| Contrasto | 0 – 10 | |
| Saturazione | 0 – 200 | |
| Esposizione | -13 – 0 | Valori negativi = esposizione manuale |
| Focus | 0 – 255 | Autofocus disabilitato all'avvio |

---

## Note operative

- Il server accetta connessioni **solo da localhost** per sicurezza. Per connessioni di rete modificare `'127.0.0.1'` in `'0.0.0.0'` in `start_socket_server`.
- La **rotazione** è configurata per area nella GUI e viene applicata automaticamente al momento del salvataggio — il client non deve fare nulla di speciale.
- Su alcune webcam focus ed esposizione manuale potrebbero non essere supportati dal driver — vengono ignorati silenziosamente.
- OpenCV usa **DirectShow** (`cv2.CAP_DSHOW`) su Windows per evitare ritardi di inizializzazione.
- Le sottocartelle nel percorso file vengono create automaticamente se non esistono.

---

## Licenza

MIT — libero utilizzo, modifica e distribuzione.
