# Webcam Capture Server

Sistema di acquisizione immagini da webcam con GUI di configurazione e server socket TCP.
Permette a qualsiasi script Python esterno di catturare una o più aree dell'immagine con una singola riga di codice.
Supporta opzionalmente l'invio di allarmi A-code sul bus CAN tramite interfaccia Vector.

---

## Struttura del progetto

```
webcam_capture_server.py   # Server principale con GUI
webcam_client.py           # Modulo client da importare nel tuo codice
alarm_can_sender.py        # Modulo CAN opzionale (solo se si usa la funzione allarmi)
CVT.dbc                    # File DBC dei messaggi CAN (fornito separatamente)
esempio_utilizzo.py        # Esempi pratici di utilizzo
```

`alarm_can_sender.py` e `CVT.dbc` sono **opzionali**: se non presenti, il server funziona normalmente senza la sezione CAN.

---

## Requisiti

- Python 3.8 o superiore
- Tkinter (incluso nella distribuzione standard di Python)

```bash
pip install opencv-python Pillow
```

Per la funzionalità CAN (opzionale):

```bash
pip install python-can cantools
```

Inoltre: driver XL Vector installato (già presente se CANalyzer/CANoe è installato sul PC).

---

## Avvio rapido

### 1 — Avvia il server

```bash
python webcam_capture_server.py
```

L'applicazione si apre automaticamente **a schermo intero**.

> Su Linux/Mac, se lo schermo intero non funziona, sostituire `self.root.state("zoomed")` con `self.root.attributes("-zoomed", True)` nel sorgente.

Segui questo ordine nella GUI:

1. Seleziona la **camera** dal menu a tendina (Webcam 0, 1, 2...)
2. Scegli la **risoluzione** (640×480 / 1280×720 / 1920×1080)
3. Regola i **parametri webcam** con gli slider (contrasto, saturazione, esposizione, focus)
4. Clicca **▶ Start Live View** per vedere l'anteprima in tempo reale
5. Configura le **aree di acquisizione** (vedi sezione dedicata)
6. Se necessario, configura la **Correzione Prospettica**
7. Se necessario, configura il **CAN Alarm Sender** (vedi sezione dedicata)
8. Verifica il campo **Directory Salvataggio**
9. Clicca **▶ Start Server** → lo stato diventa `● Online (porta 5005)`
10. Testa con il bottone **Cattura ora** prima di usare il client

### 2 — Importa nel tuo codice

Copia `webcam_client.py` nella cartella del tuo progetto, poi:

```python
from webcam_client import cattura

percorso = cattura(area_id=1, nome_file="misura.jpg")
```

Niente altro. Il file salvato si trova nel percorso restituito.

---

## Aree di acquisizione

Le aree si disegnano direttamente sull'anteprima Live View:

1. Clicca **+ Aggiungi Area**
2. Tieni premuto il tasto sinistro del mouse sull'anteprima e trascina per disegnare il rettangolo
3. Rilascia per confermare → l'area viene aggiunta con ID progressivo (Area 1, Area 2, ...)
4. Opzionale: scegli la **rotazione** (0°/90°/180°/270°) prima di aggiungere

Per rimuovere un'area: selezionala nella lista e clicca **− Rimuovi**.

Il client usa l'ID numerico (`area_id=1`, `area_id=2`, ...) per specificare quale area catturare.

---

## Correzione Prospettica

Se la camera non è perfettamente perpendicolare allo schermo, l'immagine risulterà deformata (trapezoidale). La correzione prospettica raddrizza automaticamente ogni cattura prima del ritaglio ROI.

```
Camera inclinata:          Dopo correzione:

 ╱──────────────╲          ┌──────────────┐
╱                ╲    →    │              │
╲                ╱         │              │
 ╲______________╱          └──────────────┘

   (trapezio)               (rettangolo)
```

### Come configurarla

1. Avvia il Live View
2. Clicca **Seleziona 4 angoli** nella sezione "Correzione Prospettica"
3. Il cursore diventa una croce — clicca i 4 angoli dello schermo **nell'ordine**:
   - **↖ Top-Left** (angolo in alto a sinistra)
   - **↗ Top-Right** (angolo in alto a destra)
   - **↘ Bottom-Right** (angolo in basso a destra)
   - **↙ Bottom-Left** (angolo in basso a sinistra)
4. Ogni punto viene marcato con un cerchio colorato sull'anteprima
5. Al 4° punto la matrice viene calcolata automaticamente e l'anteprima si raddrizza in tempo reale

Lo stato diventa `● Attiva → output 1280x720px` e da quel momento tutte le catture vengono corrette.

---

## CAN Alarm Sender (opzionale)

Permette di attivare allarmi A-code sul display fisico del veicolo via bus CAN, coordinando l'invio del segnale con la cattura della webcam.

### Prerequisiti

1. `alarm_can_sender.py` nella stessa cartella di `webcam_capture_server.py`
2. `pip install python-can cantools`
3. Driver XL Vector installato (VN1630 / VN1640 o compatibile)
4. File `.dbc` con la definizione dei messaggi CAN

### Configurazione nella GUI

La sezione **CAN Alarm Sender** appare automaticamente nella barra sinistra solo se `alarm_can_sender.py` è presente nella cartella. Se il modulo non c'è, la sezione non viene mostrata e il server funziona normalmente.

1. Clicca **...** per aprire il file picker e selezionare il file `.dbc`
2. Imposta il **canale** Vector (0 = CH1 in CANalyzer/CANoe)
3. Clicca **⚡ Connetti CAN** → lo stato diventa `● Connesso CH0 (38 allarmi)`

Il CAN è indipendente dal server webcam: puoi connettere/disconnettere senza toccare la webcam.

### Test standalone del modulo CAN

Prima di usare il sistema completo, verifica che il bus funzioni:

```bash
python alarm_can_sender.py
```

Il programma chiede il percorso del DBC e il canale, invia un allarme di prova e lo cancella dopo 3 secondi.

---

## API client — `webcam_client.py`

### `cattura(area_id, nome_file, porta=5005)`

Cattura l'area specificata e salva il file.

| Parametro | Tipo | Descrizione |
|---|---|---|
| `area_id` | int | ID dell'area configurata nella GUI |
| `nome_file` | str | Nome file (`"misura.jpg"`) o percorso assoluto (`"C:/foto/img.png"`). Il formato dipende dall'estensione (`.jpg`, `.png`, `.bmp`, `.tiff`) |
| `porta` | int | Porta TCP del server (default: `5005`) |

**Ritorna:** `str` — percorso completo del file salvato

**Eccezioni:**
- `RuntimeError` — il server ha risposto con errore (area inesistente, webcam offline...)
- `ConnectionRefusedError` — il server non è in ascolto
- `TimeoutError` — nessuna risposta entro 10 secondi

---

### `stato_server(porta=5005)`

Verifica se il server è raggiungibile e pronto.

```python
from webcam_client import stato_server

pronto, msg = stato_server()
if pronto:
    print(msg)   # es. "READY:aree=[1, 2, 3]"
else:
    print(f"Non disponibile: {msg}")
```

---

### `mostra_allarme(alarm_id, porta=5005)`

Attiva un allarme A-code sul display fisico via CAN.

| Parametro | Tipo | Descrizione |
|---|---|---|
| `alarm_id` | str | Codice allarme, es. `"A101"`. Case-insensitive. |
| `porta` | int | Porta TCP del server (default: `5005`) |

**Ritorna:** `str` — risposta del server es. `"OK:shown:A101"`

**Eccezioni:** `RuntimeError` se l'alarm_id è sconosciuto o il CAN non è connesso.

Se c'era già un allarme attivo, viene azzerato automaticamente prima di inviare il nuovo.

---

### `cancella_allarme(porta=5005)`

Azzera il segnale CAN dell'ultimo allarme attivato. Non solleva eccezioni se non c'era nessun allarme attivo.

---

### `lista_allarmi(porta=5005)`

Ritorna la lista degli A-code supportati dal server.

```python
alarms = lista_allarmi()
# → ['A001', 'A002', 'A005', 'A006', ..., 'A503']
```

---

### Esempio workflow completo (AutomationDesk)

```python
from webcam_client import cattura, mostra_allarme, cancella_allarme
import time

# 1. Attiva allarme sul display fisico
mostra_allarme("A101")

# 2. Attendi aggiornamento display
time.sleep(2.0)

# 3. Cattura l'area di interesse
percorso = cattura(1, "alarm_A101.png")

# 4. Analisi OCR / colori sull'immagine...

# 5. Reset
cancella_allarme()
```

---

## Protocollo socket

La comunicazione avviene via **TCP su localhost**, porta `5005`.
Comandi in testo terminati da `\n`.

| Comando | Risposta successo | Risposta errore |
|---|---|---|
| `CAPTURE:area_id:nome_file\n` | `OK:/percorso/completo\n` | `ERROR:messaggio\n` |
| `STATUS\n` | `READY:aree=[1, 2]\n` | `NOT_READY:motivo\n` |
| `SHOW_ALARM:A101\n` | `OK:shown:A101\n` | `ERROR:messaggio\n` |
| `CLEAR_ALARM\n` | `OK:cleared\n` | `ERROR:messaggio\n` |
| `LIST_ALARMS\n` | `OK:A001,A002,...\n` | `ERROR:messaggio\n` |

---

## Architettura interna

```
┌────────────────────────────────────────────────────────────────┐
│                   webcam_capture_server.py                     │
│                                                                │
│  [Grabber Thread]   cap.read() continuo → latest_frame        │
│                               ↓                                │
│  [GUI Thread]       Live View ~20fps, selezione aree mouse    │
│                               ↓                                │
│  [Server Thread]    TCP 127.0.0.1:5005                        │
│                     CAPTURE / STATUS / SHOW_ALARM / ...       │
│                               ↓                                │
│  [AlarmCanSender]   Bus Vector CAN → display fisico           │
│                     (presente solo se alarm_can_sender.py      │
│                      è nella cartella e CAN è connesso)        │
└────────────────────────────────────────────────────────────────┘
                     ↑ TCP localhost
┌────────────────────────────────────────────────────────────────┐
│  webcam_client.py                                              │
│  cattura() · stato_server()                                    │
│  mostra_allarme() · cancella_allarme() · lista_allarmi()      │
│  ←── importato nel tuo codice / AutomationDesk                │
└────────────────────────────────────────────────────────────────┘
```

I lock `cam_lock` e `frame_lock` garantiscono thread-safety tra Grabber, GUI e Server.

---

## Parametri webcam

Tutti regolabili in tempo reale dagli slider senza riavviare:

| Parametro | Range | Note |
|---|---|---|
| Contrasto | 0 – 10 | |
| Saturazione | 0 – 200 | |
| Esposizione | -13 – 0 | Valori negativi = manuale |
| Focus | 0 – 255 | Autofocus disabilitato all'avvio |

---

## Note operative

- Il server accetta connessioni solo da **localhost** per sicurezza. Per connessioni di rete modificare `'127.0.0.1'` in `'0.0.0.0'` in `start_socket_server`.
- La **rotazione** è configurata per area nella GUI e applicata automaticamente al salvataggio — il client non deve fare nulla di speciale.
- Le **sottocartelle** nel percorso file vengono create automaticamente.
- OpenCV usa **DirectShow** (`cv2.CAP_DSHOW`) su Windows per evitare ritardi di inizializzazione.
- I nomi `msg` e `sig` in `ALARM_DICT` dentro `alarm_can_sender.py` devono corrispondere esattamente ai nomi nel file `.dbc` (case-sensitive). Verificare con CANdb++ prima del deploy.

---

## Licenza

MIT — libero utilizzo, modifica e distribuzione.
