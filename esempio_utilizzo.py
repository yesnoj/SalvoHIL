"""
esempio_utilizzo.py
====================
Interfaccia a menù per testare le funzionalità di webcam_client.py

Esegui:
    python esempio_utilizzo.py
"""

import os
import time
from webcam_client import cattura, stato_server, mostra_allarme, cancella_allarme, lista_allarmi

# ─────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────

def chiedi_area():
    raw = input("  ID area da catturare [default 1]: ").strip()
    return int(raw) if raw else 1

def chiedi_attesa():
    raw = input("  Attesa dopo invio CAN in secondi [default 2]: ").strip()
    try:
        return float(raw) if raw else 2.0
    except ValueError:
        return 2.0

def chiedi_cartella(default_name):
    default = os.path.join(os.path.expanduser("~"), "Desktop", default_name)
    raw = input(f"  Cartella di salvataggio [{default}]: ").strip()
    cartella = raw if raw else default
    os.makedirs(cartella, exist_ok=True)
    return cartella

def separatore():
    print("-" * 50)

def pausa():
    input("\n  Premi INVIO per tornare al menù...")

# ─────────────────────────────────────────────
#  Verifica server all'avvio
# ─────────────────────────────────────────────

def verifica_server():
    print("Verifico connessione al server...", end=" ", flush=True)
    pronto, msg = stato_server()
    if pronto:
        print(f"OK  ({msg})")
        return True
    else:
        print(f"ERRORE\n  {msg}")
        print("  Avvia webcam_capture_server.py e clicca 'Start Server'.")
        return False

# ─────────────────────────────────────────────
#  Test 1 — Cattura singola
# ─────────────────────────────────────────────

def test_cattura_singola():
    separatore()
    print("TEST 1 — Cattura singola")
    separatore()
    area_id = chiedi_area()
    nome    = input("  Nome file [default: cattura.jpg]: ").strip() or "cattura.jpg"
    try:
        percorso = cattura(area_id=area_id, nome_file=nome)
        print(f"\n  OK  Salvata: {percorso}")
    except Exception as e:
        print(f"\n  ERRORE: {e}")
    pausa()

# ─────────────────────────────────────────────
#  Test 2 — Cattura più aree
# ─────────────────────────────────────────────

def test_cattura_aree():
    separatore()
    print("TEST 2 — Cattura più aree in sequenza")
    separatore()
    raw = input("  ID aree separate da virgola [default: 1,2,3]: ").strip()
    try:
        aree = [int(x.strip()) for x in raw.split(",")] if raw else [1, 2, 3]
    except ValueError:
        print("  Input non valido.")
        pausa()
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    for area_id in aree:
        nome = f"area{area_id}_{ts}.jpg"
        try:
            percorso = cattura(area_id=area_id, nome_file=nome)
            print(f"  OK  Area {area_id} -> {percorso}")
        except RuntimeError as e:
            print(f"  SKIP Area {area_id} -> {e}")
    pausa()

# ─────────────────────────────────────────────
#  Test 3 — Acquisizione periodica
# ─────────────────────────────────────────────

def test_periodico():
    separatore()
    print("TEST 3 — Acquisizione periodica")
    separatore()
    area_id    = chiedi_area()
    raw_n      = input("  Numero di acquisizioni [default 5]: ").strip()
    raw_t      = input("  Intervallo in secondi [default 2]: ").strip()
    n          = int(raw_n) if raw_n else 5
    intervallo = float(raw_t) if raw_t else 2.0

    for i in range(1, n + 1):
        nome = f"periodica_{i:03d}_{time.strftime('%H%M%S')}.jpg"
        try:
            percorso = cattura(area_id=area_id, nome_file=nome)
            print(f"  [{i}/{n}] OK  {percorso}")
        except Exception as e:
            print(f"  [{i}/{n}] ERRORE: {e}")
        if i < n:
            time.sleep(intervallo)
    pausa()

# ─────────────────────────────────────────────
#  Test 4 — Lista allarmi
# ─────────────────────────────────────────────

def test_lista_allarmi():
    separatore()
    print("TEST 4 — Lista allarmi CAN disponibili")
    separatore()
    try:
        allarmi = lista_allarmi()
        print(f"  Totale: {len(allarmi)}\n")
        for i, a in enumerate(allarmi):
            print(f"  {a}", end="\n" if (i + 1) % 10 == 0 else "  ")
        print()
    except RuntimeError as e:
        print(f"  ERRORE: {e}")
    pausa()

# ─────────────────────────────────────────────
#  Test 5 — Allarme singolo + cattura
# ─────────────────────────────────────────────

def test_allarme_singolo():
    separatore()
    print("TEST 5 — Attiva un allarme e cattura")
    separatore()

    try:
        allarmi = lista_allarmi()
    except RuntimeError as e:
        print(f"  ERRORE CAN non disponibile: {e}")
        pausa()
        return

    print(f"  Allarmi disponibili: {allarmi}\n")
    alarm_id = input("  Alarm ID (es. A101): ").strip().upper()
    if alarm_id not in allarmi:
        print(f"  '{alarm_id}' non trovato nel dizionario.")
        pausa()
        return

    area_id = chiedi_area()
    attesa  = chiedi_attesa()
    nome    = input(f"  Nome file [default: {alarm_id}.png]: ").strip() or f"{alarm_id}.png"

    try:
        print(f"\n  -> Invio allarme {alarm_id} sul CAN...")
        mostra_allarme(alarm_id)
        print(f"  -> Attendo {attesa}s...")
        time.sleep(attesa)
        percorso = cattura(area_id=area_id, nome_file=nome)
        print(f"  OK  Catturata: {percorso}")
        cancella_allarme()
        print("  OK  Allarme cancellato")
    except RuntimeError as e:
        print(f"  ERRORE: {e}")
        try:
            cancella_allarme()
        except Exception:
            pass
    pausa()

# ─────────────────────────────────────────────
#  Test 6 — Ciclo per livello
# ─────────────────────────────────────────────

LIVELLI = {
    "0": (["A001", "A002", "A005", "A006", "A007", "A029"],
          "Level 0  BLU popup"),
    "1": (["A101", "A102", "A103", "A104", "A105", "A106", "A107", "A108", "A109"],
          "Level 1  ROSSO + STOP"),
    "2": (["A202", "A203", "A204", "A205", "A206", "A210", "A220", "A221"],
          "Level 2  ROSSO"),
    "3": (["A302", "A303", "A304", "A305", "A306", "A307", "A308", "A309",
           "A321", "A322", "A323", "A324", "A329", "A330", "A331", "A332",
           "A333", "A334", "A335", "A336", "A337", "A338", "A339", "A340",
           "A341", "A348"],
          "Level 3  ARANCIONE + buzzer"),
    "4": (["A401", "A402", "A414"],
          "Level 4  ARANCIONE no buzzer"),
    "5": (["A501", "A502", "A503"],
          "Level 5  BLU + beep"),
}

def test_ciclo_livello():
    separatore()
    print("TEST 6 — Ciclo allarmi per livello")
    separatore()
    print("  Livelli disponibili:")
    for k, (allarmi, desc) in sorted(LIVELLI.items()):
        print(f"    [{k}]  {desc}  ({len(allarmi)} allarmi)")

    scelta = input("\n  Scegli livello (0-5): ").strip()
    if scelta not in LIVELLI:
        print("  Scelta non valida.")
        pausa()
        return

    allarmi, desc = LIVELLI[scelta]
    area_id  = chiedi_area()
    attesa   = chiedi_attesa()
    cartella = chiedi_cartella(f"alarm_level{scelta}")

    print(f"\n  Avvio ciclo: {len(allarmi)} allarmi -> {cartella}\n")
    ok = ko = 0
    for alarm_id in allarmi:
        print(f"  -> {alarm_id}", end="  ", flush=True)
        try:
            mostra_allarme(alarm_id)
            time.sleep(attesa)
            nome_file = os.path.join(cartella, f"{alarm_id}_{time.strftime('%H%M%S')}.png")
            cattura(area_id=area_id, nome_file=nome_file)
            cancella_allarme()
            time.sleep(0.5)
            print("OK")
            ok += 1
        except Exception as e:
            print(f"ERRORE  ({e})")
            ko += 1
            try:
                cancella_allarme()
            except Exception:
                pass

    print(f"\n  Completato: {ok} OK  {ko} errori")
    print(f"  Immagini in: {cartella}")
    pausa()

# ─────────────────────────────────────────────
#  Test 7 — Ciclo TUTTI gli allarmi
# ─────────────────────────────────────────────

def test_ciclo_completo():
    separatore()
    print("TEST 7 — Ciclo completo di TUTTI gli allarmi")
    separatore()

    try:
        allarmi = lista_allarmi()
    except RuntimeError as e:
        print(f"  ERRORE CAN non disponibile: {e}")
        pausa()
        return

    print(f"  Allarmi da eseguire: {len(allarmi)}")
    conferma = input("  Confermi? (s/N): ").strip().lower()
    if conferma != "s":
        print("  Annullato.")
        pausa()
        return

    area_id  = chiedi_area()
    attesa   = chiedi_attesa()
    cartella = chiedi_cartella("alarm_full_test")

    print(f"\n  Avvio ciclo completo -> {cartella}\n")
    ok = ko = 0
    for alarm_id in allarmi:
        print(f"  -> {alarm_id}", end="  ", flush=True)
        try:
            mostra_allarme(alarm_id)
            time.sleep(attesa)
            nome_file = os.path.join(cartella, f"{alarm_id}.png")
            cattura(area_id=area_id, nome_file=nome_file)
            cancella_allarme()
            time.sleep(0.5)
            print("OK")
            ok += 1
        except Exception as e:
            print(f"ERRORE  ({e})")
            ko += 1
            try:
                cancella_allarme()
            except Exception:
                pass

    print(f"\n  Completato: {ok} OK  {ko} errori")
    print(f"  Immagini in: {cartella}")
    pausa()

# ─────────────────────────────────────────────
#  Menù principale
# ─────────────────────────────────────────────

MENU = [
    ("1", "Cattura singola",                   test_cattura_singola),
    ("2", "Cattura piu aree in sequenza",       test_cattura_aree),
    ("3", "Acquisizione periodica",             test_periodico),
    ("4", "Lista allarmi CAN disponibili",      test_lista_allarmi),
    ("5", "Attiva un allarme e cattura",        test_allarme_singolo),
    ("6", "Ciclo allarmi per livello",          test_ciclo_livello),
    ("7", "Ciclo TUTTI gli allarmi",            test_ciclo_completo),
    ("0", "Esci",                               None),
]

def stampa_menu():
    print("\n" + "=" * 50)
    print("  WEBCAM CAPTURE CLIENT  -  Menu di test")
    print("=" * 50)
    for chiave, etichetta, _ in MENU:
        print(f"  [{chiave}]  {etichetta}")
    print("=" * 50)

def main():
    if not verifica_server():
        return

    while True:
        stampa_menu()
        scelta = input("\n  Scelta: ").strip()

        if scelta == "0":
            print("\n  Uscita.\n")
            break

        trovato = False
        for chiave, _, funzione in MENU:
            if scelta == chiave and funzione is not None:
                print()
                funzione()
                trovato = True
                break

        if not trovato:
            print("  Scelta non valida. Riprova.")

if __name__ == "__main__":
    main()
