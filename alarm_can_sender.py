"""
alarm_can_sender.py  —  SalvoHIL
==================================
Gestisce l'invio di allarmi A-code sul bus CAN tramite interfaccia Vector.

Dipendenze:
    pip install python-can cantools
    + driver XL Vector (già presente con CANalyzer/CANoe)

Uso diretto:
    from alarm_can_sender import AlarmCanSender
    sender = AlarmCanSender(dbc_path="CVT.dbc", channel=0, app_name="SalvoHIL")
    sender.show_alarm("A101")
    sender.clear_alarm()
    sender.shutdown()

Test standalone:
    python alarm_can_sender.py
"""

import threading
import logging
from pathlib import Path

try:
    import can
    import cantools
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False
    logging.warning("python-can o cantools non installati. Funzionalita CAN disabilitata.")


# ─────────────────────────────────────────────────────────────────────────────
#  Dizionario A-code → segnale CAN
#
#  Struttura: { alarm_id: {msg: nome_messaggio_DBC, sig: nome_segnale_DBC, val: valore} }
#
#  IMPORTANTE: msg e sig devono corrispondere ai nomi ESATTI nel file .dbc
#  (case-sensitive). Verificare con CANdb++ prima del deploy.
#  Il valore 0 viene usato automaticamente dal metodo clear_alarm().
# ─────────────────────────────────────────────────────────────────────────────
ALARM_DICT = {
    # ── Livello 0-a  BLU / safety buzzer (azione sicurezza richiesta) ─────────
    "A001": {"msg": "PB_UCM_Status1_27",  "sig": "ParkBrakeWarn",       "val": 1},
    "A002": {"msg": "PB_UCM_Status1_27",  "sig": "ParkBrakeActWarn",    "val": 1},
    "A029": {"msg": "PB_UCM_Status1_27",  "sig": "PTOWarnSts",          "val": 1},
    # ── Livello 0-b  BLU / action required (azione operatore richiesta) ───────
    "A005": {"msg": "PB_UCM_Status1_27",  "sig": "RlsHBWarn",           "val": 1},
    "A006": {"msg": "PB_UCM_Status1_27",  "sig": "NeutralWarn",         "val": 1},
    "A007": {"msg": "PB_UCM_Status1_27",  "sig": "ClutchWarn",          "val": 1},
    # ── Livello 1  ROSSO + "STOP" / Critical Buzzer / Red Stop Lamp ──────────
    "A101": {"msg": "PB_Warnings1_27",    "sig": "DrvlOilPrsWarn",      "val": 2},
    "A102": {"msg": "PB_Warnings1_27",    "sig": "DrvlOilTmpWarn",      "val": 2},
    "A103": {"msg": "PB_Warnings1_27",    "sig": "EngCoolTmpHiWarn",    "val": 2},
    "A104": {"msg": "PB_Warnings1_27",    "sig": "EngOilPrsWarn",       "val": 2},
    "A105": {"msg": "PB_Warnings1_27",    "sig": "EngOilTmpWarn",       "val": 2},
    "A106": {"msg": "PB_Warnings1_27",    "sig": "HydOilTmpWarn",       "val": 2},
    "A107": {"msg": "PB_Warnings1_27",    "sig": "TransmOilTmpWarn",    "val": 2},
    "A108": {"msg": "PB_Warnings1_27",    "sig": "AirFltrWarn",         "val": 2},
    "A109": {"msg": "PB_Warnings1_27",    "sig": "ChrgSysWarn",         "val": 2},
    # ── Livello 2  ROSSO / Critical Buzzer / Red Stop Lamp ───────────────────
    "A202": {"msg": "PB_Warnings1_27",    "sig": "TransmWarnSts",       "val": 4},
    "A203": {"msg": "PB_Warnings1_27",    "sig": "TransmWarnSts",       "val": 8},
    "A204": {"msg": "PB_Warnings2_27",    "sig": "FuelLvlWarn",         "val": 2},
    "A205": {"msg": "PB_Warnings2_27",    "sig": "DEFLvlWarn",          "val": 2},
    "A210": {"msg": "PB_Warnings2_27",    "sig": "BrakeSysWarn",        "val": 2},
    "A221": {"msg": "PB_Warnings2_27",    "sig": "SteerSysWarn",        "val": 2},
    # ── Livello 3  ARANCIONE / Non-Critical Buzzer / Amber Lamp ──────────────
    "A301": {"msg": "PB_Warnings1_27",    "sig": "DrvlOilPrsWarn",      "val": 1},
    "A302": {"msg": "PB_Warnings1_27",    "sig": "DrvlOilTmpWarn",      "val": 1},
    "A303": {"msg": "PB_Warnings1_27",    "sig": "EngCoolTmpHiWarn",    "val": 1},
    "A304": {"msg": "PB_Warnings1_27",    "sig": "EngOilPrsWarn",       "val": 1},
    "A305": {"msg": "PB_Warnings1_27",    "sig": "EngOilTmpWarn",       "val": 1},
    "A306": {"msg": "PB_Warnings1_27",    "sig": "HydOilTmpWarn",       "val": 1},
    "A307": {"msg": "PB_Warnings1_27",    "sig": "TransmOilTmpWarn",    "val": 1},
    "A308": {"msg": "PB_Warnings1_27",    "sig": "AirFltrWarn",         "val": 1},
    "A309": {"msg": "PB_Warnings1_27",    "sig": "ChrgSysWarn",         "val": 1},
    "A340": {"msg": "PB_Warnings2_27",    "sig": "FuelLvlWarn",         "val": 1},
    "A341": {"msg": "PB_Warnings2_27",    "sig": "DEFLvlWarn",          "val": 1},
    "A348": {"msg": "PB_Warnings2_27",    "sig": "AdBlueQualWarn",      "val": 1},
    # ── Livello 4  ARANCIONE / no buzzer ─────────────────────────────────────
    "A401": {"msg": "PB_Warnings3_27",    "sig": "ServiceWarn",         "val": 1},
    "A402": {"msg": "PB_Warnings3_27",    "sig": "ServiceOverdueWarn",  "val": 1},
    "A414": {"msg": "PB_Warnings3_27",    "sig": "FilterMaintWarn",     "val": 1},
    # ── Livello 5  BLU / single beep ─────────────────────────────────────────
    "A501": {"msg": "PB_Warnings3_27",    "sig": "InfoWarn1",           "val": 1},
    "A502": {"msg": "PB_Warnings3_27",    "sig": "InfoWarn2",           "val": 1},
    "A503": {"msg": "PB_Warnings3_27",    "sig": "InfoWarn3",           "val": 1},
}


class AlarmCanSender:
    """
    Invia allarmi A-code sul bus CAN tramite interfaccia Vector (VN1630/VN1640).

    Il bus rimane aperto per tutta la sessione: nessuna latenza di riapertura
    tra show_alarm() e clear_alarm(). Thread-safe tramite Lock interno.

    Parametri
    ----------
    dbc_path  : percorso al file .dbc con la definizione dei messaggi
    channel   : canale Vector 0-based  (0 = CH1 in CANalyzer)
    app_name  : nome app nel driver XL Vector (deve corrispondere alla configurazione)
    bitrate   : bitrate in bps (default 250 000)
    """

    def __init__(self, dbc_path, channel=0, app_name="SalvoHIL", bitrate=250_000):
        if not CAN_AVAILABLE:
            raise RuntimeError("Installare: pip install python-can cantools")

        path = Path(dbc_path)
        if not path.exists():
            raise FileNotFoundError(f"DBC non trovato: {dbc_path}")

        self._db = cantools.database.load_file(str(path))

        # Parametri bus allineati a FinalDTC_PaddleOCR.py / create_can_bus()
        self._bus = can.interface.Bus(
            interface="vector",
            channel=channel,
            app_name=app_name,
            bitrate=bitrate,
            fd=False,
            receive_own_messages=False,
            transmit_buffer_size=32,
            receive_buffer_size=512,
            bitrate_switch=False,
            single_handle=True,
            timing=None,
        )

        self._lock         = threading.Lock()
        self._active_alarm = None   # dict con {msg, sig, val, id} dell'allarme attivo
        logging.info(
            f"AlarmCanSender pronto — DBC:{dbc_path}  CH:{channel}  app:{app_name}"
        )

    # ─────────────────────── metodi privati ───────────────────────────────────

    def _send_signal(self, msg_name, sig_name, value):
        """Codifica e invia un singolo segnale CAN (tutti gli altri segnali = 0)."""
        msg_def = self._db.get_message_by_name(msg_name)
        data = {s.name: 0 for s in msg_def.signals}
        data[sig_name] = value
        encoded = msg_def.encode(data)
        frame = can.Message(
            arbitration_id = msg_def.frame_id,
            data           = encoded,
            is_extended_id = (msg_def.frame_id > 0x7FF),
        )
        with self._lock:
            self._bus.send(frame)
        logging.debug(
            f"CAN TX  {msg_name}.{sig_name}={value}  "
            f"ID=0x{msg_def.frame_id:X}  "
            f"data=[{' '.join(f'{b:02X}' for b in encoded)}]"
        )

    def _clear_active(self):
        """Azzera il segnale dell'allarme correntemente attivo."""
        e = self._active_alarm
        self._send_signal(e["msg"], e["sig"], 0)
        logging.info(f"Allarme {e['id']} cancellato (segnale → 0)")
        self._active_alarm = None

    # ─────────────────────── API pubblica ─────────────────────────────────────

    def show_alarm(self, alarm_id):
        """
        Attiva l'allarme specificato sul display fisico via CAN.

        Se c'era già un allarme attivo, lo azzera prima di inviare il nuovo.

        Parametri
        ----------
        alarm_id : str — codice A-code, es. "A101". Case-insensitive.

        Ritorna
        -------
        True  se alarm_id è nel dizionario e il frame è stato inviato
        False se alarm_id è sconosciuto
        """
        alarm_id = alarm_id.upper().strip()
        entry = ALARM_DICT.get(alarm_id)
        if entry is None:
            logging.warning(f"Allarme sconosciuto: {alarm_id}")
            return False

        if self._active_alarm is not None:
            self._clear_active()

        self._send_signal(entry["msg"], entry["sig"], entry["val"])
        self._active_alarm = {**entry, "id": alarm_id}
        logging.info(f"Allarme {alarm_id} attivato")
        return True

    def clear_alarm(self):
        """
        Azzera il segnale CAN dell'ultimo allarme attivato.

        Ritorna
        -------
        True  se c'era un allarme attivo (e lo ha azzerato)
        False se non c'era nessun allarme attivo
        """
        if self._active_alarm is None:
            logging.info("clear_alarm: nessun allarme attivo")
            return False
        self._clear_active()
        return True

    def shutdown(self):
        """
        Azzera l'eventuale allarme attivo e chiude il bus CAN.
        Viene chiamato automaticamente da webcam_capture_server._on_close().
        """
        if self._active_alarm is not None:
            self._clear_active()
        self._bus.shutdown()
        logging.info("AlarmCanSender: bus CAN chiuso.")

    @staticmethod
    def list_alarms():
        """Ritorna la lista ordinata di tutti gli A-code supportati."""
        return sorted(ALARM_DICT.keys())


# ─────────────────────────────────────────────
#  Test standalone
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import time
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    print("=== Test AlarmCanSender ===")

    if not CAN_AVAILABLE:
        print("ERRORE: python-can o cantools non installati.")
        print("Eseguire: pip install python-can cantools")
        sys.exit(1)

    dbc = input("Percorso file DBC (es. CVT.dbc): ").strip() or "CVT.dbc"
    ch  = input("Canale Vector 0-based (0=CH1) [default 0]: ").strip()
    ch  = int(ch) if ch else 0

    try:
        sender = AlarmCanSender(dbc_path=dbc, channel=ch, app_name="SalvoHIL")
    except Exception as e:
        print(f"ERRORE inizializzazione bus: {e}")
        sys.exit(1)

    print(f"Bus aperto. Allarmi disponibili: {len(AlarmCanSender.list_alarms())}")
    alarm = input("Alarm ID da testare (es. A101) [default A101]: ").strip().upper() or "A101"

    print(f"\n→ SHOW_ALARM:{alarm}")
    ok = sender.show_alarm(alarm)
    if ok:
        print(f"  OK — allarme {alarm} inviato. Verifica il display fisico.")
        print("  Attendo 3 secondi...")
        time.sleep(3)
        print("→ CLEAR_ALARM")
        sender.clear_alarm()
        print("  OK — segnale azzerato.")
    else:
        print(f"  ERRORE — allarme {alarm} non trovato nel dizionario.")

    sender.shutdown()
    print("\nTest completato.")
