from pathlib import Path

class Constants:
    DATA_PORTS = [27117, 27118, 27119]
    BASE_DIR = Path(__file__).resolve().parent.parent
    LAB_DIR = BASE_DIR / "replica_lab"
    NODES = [
        {"name": "nodo1", "port": 27117, "cfg": LAB_DIR / "cfg" / "nodo1.cfg"},
        {"name": "nodo2", "port": 27118, "cfg": LAB_DIR / "cfg" / "nodo2.cfg"},
        {"name": "nodo3", "port": 27119, "cfg": LAB_DIR / "cfg" / "nodo3.cfg"},
        {"name": "arbitro", "port": 27120, "cfg": LAB_DIR / "cfg" / "arb.cfg"},
    ]