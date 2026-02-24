# Webcam Capture Server

Sistema di acquisizione immagini da webcam con GUI di configurazione e server socket TCP.
Permette a qualsiasi script Python esterno di richiedere una cattura immagine con una singola riga di codice.

---

## Struttura del progetto

```
webcam_capture_server.py     # Server principale con GUI
capture_client_example.py    # Esempio di client (come integrarlo nel tuo codice)
```

---

## Requisiti

- Python 3.8 o superiore
- Tkinter (incluso nella distribuzione standard di Python)

Installa le dipendenze con:

```bash
pip install opencv-python Pillow
```

---

## Avvio rapido

### 1 — Avvia il server

```bash
python webcam_capture_server.py
```

Si apre la finestra GUI. Segui questo ordine:

1. Seleziona la **camera** giusta dal menu a tendina (Webcam 0, 1, 2...)
2. Scegli la **risoluzione** desiderata (640×480 / 1280×720 / 1920×1080)
3. Regola i **parametri webcam** con gli slider (contrasto, saturazione, esposizione, focus)
4. Clicca **▶ Start Live View** per vedere l'anteprima in tempo reale
5. Clicca **✏ Seleziona Area sull'anteprima**, poi **trascina un rettangolo** direttamente sull'immagine e rilascia il mouse per confermare l'area di acquisizione
6. Verifica/modifica il campo **Directory Salvataggio**
7. Clicca **▶ Start Server** — lo stato diventa `● Online (porta 5005)`

### 2 — Testa senza client

Prima di coinvolgere il tuo codice, verifica che tutto funzioni:

- Scrivi un nome nel campo **Nome file** (es. `prova.jpg`)
- Clicca **📷 Cattura ora**
- Controlla che il file sia apparso nella directory di salvataggio

### 3 — Integra nel tuo codice Python

```python
import socket

def cattura(nome_file, porta=5005):
    with socket.socket() as s:
        s.connect(('127.0.0.1', porta))
        s.sendall(f'CAPTURE:{nome_file}\n'.encode())
        risposta = s.recv(1024).decode().strip()
    if risposta.startswith('OK:'):
        return risposta[3:]   # percorso completo del file salvato
    raise RuntimeError(risposta)

# Esempio di utilizzo
percorso = cattura('misura_001.jpg')
print(f'Immagine salvata in: {percorso}')
```

---

## Protocollo socket

La comunicazione avviene via **TCP su localhost**, porta `5005` (configurabile dalla GUI).
I comandi sono stringhe di testo terminati da `\n`.

| Comando | Risposta successo | Risposta errore |
|---|---|---|
| `CAPTURE:nome_file.jpg\n` | `OK:/percorso/completo/nome_file.jpg\n` | `ERROR:messaggio\n` |
| `STATUS\n` | `READY\n` | `NOT_READY:motivo\n` |

### Formati immagine supportati

Il formato è determinato dall'estensione del nome file passato al comando `CAPTURE`:

| Estensione | Formato |
|---|---|
| `.jpg` / `.jpeg` | JPEG compresso |
| `.png` | PNG lossless |
| `.bmp` | Bitmap |
| `.tiff` | TIFF |

### Percorsi supportati

```python
# Solo nome → salva nella directory configurata nella GUI
cattura('misura_001.jpg')

# Percorso assoluto → salva esattamente lì
cattura('C:/Risultati/misura_001.png')

# Sottocartella relativa alla directory del server
cattura('sessione_A/misura_001.jpg')
```

---

## Architettura interna

```
┌─────────────────────────────────────────────────────────┐
│                  webcam_capture_server.py               │
│                                                         │
│  [Grabber Thread]  cap.read() continuo → latest_frame  │
│                              ↓                          │
│  [GUI Thread]      Live View legge latest_frame         │
│                    (nessun blocco su cap.read)           │
│                              ↓                          │
│  [Server Thread]   Ascolta su TCP :5005                 │
│                    CAPTURE → legge latest_frame → salva │
└─────────────────────────────────────────────────────────┘
          ↑ comunica via socket TCP localhost
┌─────────────────────────────────────────────────────────┐
│              capture_client_example.py                  │
│              (o qualsiasi altro script Python)          │
└─────────────────────────────────────────────────────────┘
```

### Thread e thread-safety

Il server usa tre thread separati che condividono l'accesso alla webcam in modo sicuro:

- **Grabber Thread** — legge continuamente da `cap.read()` e aggiorna `latest_frame` protetto da `frame_lock`
- **GUI Thread** (Tkinter) — il Live View copia `latest_frame` ogni 50ms (~20fps display), gli slider aggiornano i parametri webcam tramite `cam_lock`
- **Server Thread** — ascolta connessioni socket; ogni richiesta `CAPTURE` viene gestita in un sotto-thread dedicato che copia `latest_frame`

I due lock (`cam_lock` e `frame_lock`) garantiscono che non ci siano race condition.

---

## Parametri webcam

Tutti i parametri sono regolabili in tempo reale dagli slider nella GUI senza riavviare nulla:

| Parametro | Range | Note |
|---|---|---|
| Contrasto | 0 – 10 | |
| Saturazione | 0 – 200 | |
| Esposizione | -13 – 0 | Valori negativi = esposizione manuale |
| Focus | 0 – 255 | L'autofocus viene disabilitato all'avvio |

---

## Selezione area di acquisizione

L'area (ROI — Region of Interest) si seleziona **direttamente sull'anteprima webcam**:

1. Clicca **✏ Seleziona Area sull'anteprima** (il Live View si avvia automaticamente se non è attivo)
2. Il cursore diventa una **croce**
3. **Trascina** per disegnare il rettangolo — viene mostrato in blu in tempo reale
4. **Rilascia il mouse** per confermare — il rettangolo diventa verde e le coordinate vengono mostrate nel pannello sinistro

Le coordinate vengono automaticamente convertite dalla risoluzione di display alla risoluzione reale del frame (es. 1920×1080).

Per tornare alla cattura dell'intero frame, clicca **Rimuovi Area**.

---

## Note e limitazioni

- Il server accetta connessioni **solo da localhost** (`127.0.0.1`) per motivi di sicurezza. Per abilitare connessioni di rete modificare `'127.0.0.1'` in `'0.0.0.0'` nella funzione `start_socket_server`.
- Il server gestisce una richiesta per volta (connessioni sequenziali). Per uso intensivo con molte richieste simultanee valutare una coda.
- Su alcune webcam i parametri di focus/esposizione potrebbero non essere supportati dal driver — vengono ignorati silenziosamente.
- OpenCV su Windows usa **DirectShow** (`cv2.CAP_DSHOW`) per evitare ritardi di inizializzazione.

---

## Licenza

MIT — libero utilizzo, modifica e distribuzione.
