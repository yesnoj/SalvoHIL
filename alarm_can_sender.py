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

Nomi messaggi e segnali verificati su:
    SpecialtyCVT_VB1_RevC7.dbc
    SpecialtyCVT_VB2_RevC7.dbc
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
#  ALARM_DICT
#  Tutti i nomi msg/sig verificati contro SpecialtyCVT_VB1_RevC7.dbc e VB2.
#  Formato singolo:   {"msg": "...", "sig": "...", "val": N}
#  Formato multiplo:  {"signals": [{"msg":..., "sig":..., "val":N}, ...]}
# ─────────────────────────────────────────────────────────────────────────────
ALARM_DICT = {

    # ── Level 0-a / 0-b  (BLU popup) ─────────────────────────────────────────
    "A001": {"msg": "PB_UCM_Status1_27",  "sig": "TransmWarnSts",           "val": 4},
    "A002": {"msg": "PB_UCM_Status1_27",  "sig": "TransmWarnSts",           "val": 12},
    "A005": {"msg": "PB_UCM_Status1_27",  "sig": "TransmWarnSts",           "val": 3},
    "A006": {"msg": "PB_UCM_Status1_27",  "sig": "TransmWarnSts",           "val": 1},
    "A007": {"msg": "PB_UCM_Status1_27",  "sig": "TransmWarnSts",           "val": 2},
    "A029": {"msg": "PB_WARNINGS2_27",    "sig": "PTO_OutSeatWarn",         "val": 1},

    # ── Level 1  (ROSSO + STOP + Critical Buzzer) ─────────────────────────────
    "A101": {"msg": "PB_WARNINGS1_27",    "sig": "DrvlOilPrsWarn",          "val": 2},
    "A102": {"msg": "PB_WARNINGS1_27",    "sig": "DrvlOilTempWarn",         "val": 4},
    "A103": {"msg": "PB_EDC2BC_00",       "sig": "EngOverTempPreWaiting",   "val": 2},
    "A104": {"msg": "PB_EDC2BC_00",       "sig": "EngOilPrsLo",             "val": 1},
    "A105": {"msg": "PB_ENG06_00",        "sig": "EmergRstart",             "val": 1},
    "A106": {"msg": "PB_ENG06_00",        "sig": "EmergRstart",             "val": 2},
    "A107": {"msg": "PB_ENG06_00",        "sig": "EmergRstart",             "val": 3},
    "A108": {"signals": [
        {"msg": "DPFC1_00", "sig": "AT_DPF_Sts",          "val": 2},
        {"msg": "DPFC1_00", "sig": "AT_DPF_ActvRegenSts", "val": 0},
    ]},
    "A109": {"msg": "PB_WARNINGS1_27",    "sig": "HydrostatTransmOilPrsWarn", "val": 2},

    # ── Level 2  (ROSSO + Critical Buzzer) ───────────────────────────────────
    "A202": {"msg": "PB_WARNINGS1_27",    "sig": "DrvlOilTempWarn",         "val": 4},
    "A203": {"msg": "PB_EDC2BC_00",       "sig": "EngOverTempPreWaiting",   "val": 2},
    "A204": {"msg": "PB_EDC2BC_00",       "sig": "EngOilPrsLo",             "val": 1},
    "A205": {"signals": [
        {"msg": "PB_ENG06_00", "sig": "CmplntModeStrongInduc", "val": 1},
        {"msg": "PB_ENG06_00", "sig": "DEF_Lev",               "val": 3},
    ]},
    "A206": {"signals": [
        {"msg": "PB_ENG06_00", "sig": "CmplntModeStrongInduc", "val": 2},
        {"msg": "PB_ENG06_00", "sig": "DEF_Qual",              "val": 3},
    ]},
    "A210": {"signals": [
        {"msg": "PB_ENG06_00", "sig": "CmplntModeStrongInduc", "val": 0},
        {"msg": "PB_ENG06_00", "sig": "DEF_TechFail",          "val": 3},
    ]},
    "A220": {"msg": "PB_WARNINGS1_27",    "sig": "DrvlOilPrsWarn",          "val": 2},
    "A221": {"msg": "PB_WARNINGS3_27",    "sig": "SteerLoPrsWarn",          "val": 1},

    # ── Level 3  (ARANCIONE + Non-Critical Buzzer) ───────────────────────────
    "A302": {"msg": "PB_EDC2BC_00",       "sig": "WaterInFuel",             "val": 1},
    "A303": {"msg": "FPTO_24",            "sig": "PTO_SysSts",              "val": 1},
    "A304": {"msg": "PB_WARNINGS2_27",    "sig": "PTO_AntistlPrev",         "val": 1},
    "A305": {"signals": [
        {"msg": "PB_ENG06_00", "sig": "CmplntModeStrongInduc", "val": 0},
        {"msg": "PB_ENG06_00", "sig": "DEF_TechFail",          "val": 2},
    ]},
    "A306": {"signals": [
        {"msg": "PB_ENG06_00", "sig": "CmplntModeStrongInduc", "val": 0},
        {"msg": "PB_ENG06_00", "sig": "DEF_Lev",               "val": 1},
    ]},
    "A307": {"signals": [
        {"msg": "PB_ENG06_00", "sig": "CmplntModeStrongInduc", "val": 0},
        {"msg": "PB_ENG06_00", "sig": "DEF_Qual",              "val": 1},
    ]},
    "A308": {"msg": "PB_ENG06_00",        "sig": "ValidnSts",               "val": 1},
    "A309": {"msg": "PB_ENG06_00",        "sig": "ValidnSts",               "val": 2},
    "A321": {"msg": "PB_EGR_Inducement_00","sig": "EGR_DPF_OpInducSev",    "val": 1},
    "A322": {"msg": "PB_WARNINGS4_27",    "sig": "CAT4_ModClogFilt",        "val": 1},
    "A323": {"msg": "PB_WARNINGS4_27",    "sig": "CAT4_FiltSaturtnAlrm",    "val": 1},
    "A324": {"msg": "PB_WARNINGS4_27",    "sig": "DoorOpend_orCabAirLeak",  "val": 1},
    "A329": {"msg": "PB_WARNINGS2_27",    "sig": "PBrakeManActvReqWarn",    "val": 1},
    "A330": {"msg": "PB_WARNINGS1_27",    "sig": "HydrostatTransmFiltClogWarn", "val": 1},
    "A331": {"msg": "PB_WARNINGS1_27",    "sig": "HydrostatTransmOilPrsWarn",   "val": 1},
    "A332": {"msg": "PB_WARNINGS1_27",    "sig": "DrvlOilTempWarn",         "val": 2},
    "A333": {"msg": "PB_UCM_Status1_27",  "sig": "VehImmobztnSts",          "val": 1},
    "A334": {"msg": "PB_WARNINGS1_27",    "sig": "DrvlOilPrsWarn",          "val": 1},
    "A335": {"msg": "PB_EDC2BC_00",       "sig": "EngOverTempPreWaiting",   "val": 1},
    "A336": {"msg": "PB_WARNINGS2_27",    "sig": "TurnPTO_OFF_Warn",        "val": 1},
    "A337": {"msg": "PB_WARNINGS2_27",    "sig": "PTO_CnflctWarn",          "val": 1},
    "A338": {"msg": "PB_WARNINGS2_27",    "sig": "PTO_OverloadPopup",       "val": 1},
    "A339": {"msg": "PB_WARNINGS1_27",    "sig": "AirBrakeLoPrsWarn",       "val": 1},
    "A340": {"msg": "PB_WARNINGS4_27",    "sig": "PTSS_MalfunWarn",         "val": 1},
    "A341": {"msg": "PB_WARNINGS2_27",    "sig": "FSUS_CalibrReqrdWarn",    "val": 1},
    "A348": {"msg": "PB_WARNINGS4_27",    "sig": "PTSS_MisuseWarning",      "val": 1},

    # ── Level 4  (ARANCIONE + No Buzzer) ─────────────────────────────────────
    "A401": {"msg": "PB_ENG06_00",        "sig": "ClogAirFiltSts",          "val": 1},
    "A402": {"msg": "PB_UserSet_27",      "sig": "Altern_1Warn",            "val": 1},
    "A414": {"msg": "PB_WARNINGS4_27",    "sig": "ServWarn",                "val": 1},

    # ── Level 5  (BLU + Single Beep) ─────────────────────────────────────────
    "A501": {"msg": "DPFC1_00",           "sig": "DPF_ActvRegenInhInhSw",   "val": 1},
    "A502": {"msg": "PB_WARNINGS3_27",    "sig": "CRPM_AutoFunctWarn",      "val": 1},
    "A503": {"msg": "PB_WARNINGS3_27",    "sig": "CRPM_AutoFunctWarn",      "val": 2},
}

# A301 non è nel dizionario: attivato da tensione hardware (<9V), non simulabile via CAN.
# A335 richiede RPM>500 oltre al segnale CAN: il segnale viene inviato ma la condizione
#       RPM deve essere soddisfatta nel veicolo per visualizzare il warning.


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
        self._active_alarm = None   # dict con i dati dell'allarme attivo
        logging.info(
            f"AlarmCanSender pronto — DBC:{dbc_path}  CH:{channel}  app:{app_name}"
        )

    # ─────────────────────── metodi privati ───────────────────────────────────

    def _send_one_signal(self, msg_name, sig_name, value):
        """
        Codifica e invia un singolo frame CAN con un segnale impostato al valore
        specificato (tutti gli altri segnali del messaggio = 0).
        """
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

    def _send_alarm_signals(self, entry, value_override=None):
        """
        Invia tutti i segnali associati a un allarme.
        Supporta sia la forma singola {msg, sig, val} che la forma
        multi-segnale {signals: [{msg, sig, val}, ...]}.

        Se value_override è fornito (tipicamente 0 per il clear), sostituisce
        tutti i val originali.
        """
        if "signals" in entry:
            for s in entry["signals"]:
                v = value_override if value_override is not None else s["val"]
                self._send_one_signal(s["msg"], s["sig"], v)
        else:
            v = value_override if value_override is not None else entry["val"]
            self._send_one_signal(entry["msg"], entry["sig"], v)

    def _clear_active(self):
        """Azzera tutti i segnali dell'allarme correntemente attivo."""
        e = self._active_alarm
        self._send_alarm_signals(e, value_override=0)
        logging.info(f"Allarme {e['id']} cancellato (segnali → 0)")
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
        True  se alarm_id è nel dizionario e il/i frame sono stati inviati
        False se alarm_id è sconosciuto
        """
        alarm_id = alarm_id.upper().strip()
        entry = ALARM_DICT.get(alarm_id)
        if entry is None:
            logging.warning(f"Allarme sconosciuto: {alarm_id}")
            return False

        if self._active_alarm is not None:
            self._clear_active()

        self._send_alarm_signals(entry)
        self._active_alarm = {**entry, "id": alarm_id}
        logging.info(f"Allarme {alarm_id} attivato")
        return True

    def clear_alarm(self):
        """
        Azzera i segnali CAN dell'ultimo allarme attivato.

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

    @staticmethod
    def list_todo():
        """A301 non è nel dizionario: attivato da tensione hardware (<9V), non simulabile via CAN."""
        return ["A301"]

# ─────────────────────────────────────────────
#  Test standalone
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import time
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    print("=== Test AlarmCanSender ===")
    print(f"Allarmi totali: {len(AlarmCanSender.list_alarms())}")
    print(f"TODO da verificare in DBC: {AlarmCanSender.list_todo()}")

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
