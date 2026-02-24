# Webcam Capture Server

Sistema di acquisizione immagini da webcam con GUI di configurazione e server socket TCP.
Permette a qualsiasi script Python esterno di catturare una o più aree dell'immagine con una singola riga di codice.

---

## Struttura del progetto

```
webcam_capture_server.py   # Server principale con GUI
webcam_client.py           # Modulo client da importare nel tuo codice
esempio_utilizzo.py        # Esempi pratici di utilizzo
```

---

## Requisiti

- Python 3.8 o superiore
- Tkinter (incluso nella distribuzione standard di Python)

```bash
pip install opencv-python Pillow
```

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
6. Verifica il campo **Directory Salvataggio**
7. Clicca **▶ Start Server** → lo stato diventa `● Online (porta 5005)`
8. Testa con il bottone **📷 Cattura ora** prima di usare il client

### 2 — Importa nel tuo codice

Copia `webcam_client.py` nella cartella del tuo progetto, poi:

```python
from webcam_client import cattura

percorso = cattura(area_id=1, nome_file="misura.jpg")
```

Niente altro. Il file salvato si trova nel percorso restituito.

---

## Aree di acquisizione

È possibile definire un numero illimitato di aree indipendenti, ognuna con il proprio **ID numerico** e **rotazione**.

### Come aggiungere un'area

1. Scegli la **Rotazione** dal menu (`0°` / `90°` / `180°` / `270°`) — verrà applicata al salvataggio
2. Clicca **✏ Aggiungi Area**
3. Il cursore diventa una **croce** sull'anteprima
4. **Trascina** per disegnare il rettangolo → rettangolo blu in tempo reale
5. **Rilascia** per confermare → il rettangolo diventa verde con il numero area

L'ID viene assegnato automaticamente in sequenza (1, 2, 3...).

### Gestione aree

| Azione | Come |
|---|---|
| Aggiungere | ✏ Aggiungi Area + disegna sull'anteprima |
| Rimuovere una | Seleziona dalla lista → 🗑 Rimuovi |
| Rimuovere tutte | Rimuovi tutte le aree |
| Rotazione | Scelta prima di aggiungere (per area, indipendente) |

---

## Utilizzo di `webcam_client.py`

### `cattura(area_id, nome_file, porta=5005)`

Cattura l'area specificata e salva il file.

```python
from webcam_client import cattura

# Solo nome file → salvato nella directory configurata nel server
percorso = cattura(1, "misura.jpg")

# Percorso assoluto → salvato esattamente lì
percorso = cattura(2, "C:/Risultati/misura.png")

# Sottocartella relativa alla directory del server
percorso = cattura(3, "sessione_A/misura.jpg")
```

**Parametri:**

| Parametro | Tipo | Descrizione |
|---|---|---|
| `area_id` | int | ID dell'area (come configurato nella GUI) |
| `nome_file` | str | Nome file o percorso. Il formato dipende dall'estensione (`.jpg`, `.png`, `.bmp`, `.tiff`) |
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

### Esempi completi

Vedi `esempio_utilizzo.py` per tutti i casi d'uso, oppure eseguilo direttamente:

```bash
python esempio_utilizzo.py
```

---

## Protocollo socket

La comunicazione avviene via **TCP su localhost**, porta `5005`.  
Comandi in testo terminati da `\n`.

| Comando | Risposta successo | Risposta errore |
|---|---|---|
| `CAPTURE:area_id:nome_file\n` | `OK:/percorso/completo\n` | `ERROR:messaggio\n` |
| `STATUS\n` | `READY:aree=[1, 2]\n` | `NOT_READY:motivo\n` |

---

## Architettura interna

```
┌──────────────────────────────────────────────────────────────┐
│                  webcam_capture_server.py                    │
│                                                              │
│  [Grabber Thread]  cap.read() continuo → latest_frame       │
│                              ↓                               │
│  [GUI Thread]      Live View ~20fps, selezione aree mouse   │
│                              ↓                               │
│  [Server Thread]   TCP 127.0.0.1:5005                       │
│                    CAPTURE:id:file → crop → rotazione → salva│
└──────────────────────────────────────────────────────────────┘
                    ↑ TCP localhost
┌──────────────────────────────────────────────────────────────┐
│  webcam_client.py                                            │
│  cattura(area_id, nome_file)  ←── importato dal tuo codice  │
└──────────────────────────────────────────────────────────────┘
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

---

## Licenza

MIT — libero utilizzo, modifica e distribuzione.
