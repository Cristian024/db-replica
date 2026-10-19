from bson.codec_options import CodecOptions
from bson.objectid import ObjectId
from pymongo import MongoClient, ReadPreference
from pymongo.errors import PyMongoError
from pathlib import Path
from utils.constants import Constants
from utils.functions import simplify_docs, port_open
import os
import subprocess
import time

MONGOD_EXE = Path(r"C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe")

MONGO_USER = "root"
MONGO_PASSWORD = "password"
AUTH_DB = "admin"
REPL_SET = "RP"
DB_NAME = "prueba"
COLLECTION_NAME = "usuarios"

URI = (
    f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}"
    "@localhost:27117,localhost:27118,localhost:27119/"
    f"?replicaSet={REPL_SET}&authSource={AUTH_DB}"
    "&retryWrites=true&w=2&wtimeoutMS=8000"
)

class MongoManager:
    def __init__(self):
        self.client = MongoClient(
            URI,
            serverSelectionTimeoutMS=4000,
            connectTimeoutMS=4000,
            socketTimeoutMS=10000,
            appname="CRUD-Replicas",
        )
        self.db = self.client[DB_NAME]
        self.collection = self.db[COLLECTION_NAME]
        self._direct = {}

    def direct(self, port, with_auth=True):
        key = (port, with_auth)
        if key not in self._direct:
            if with_auth:
                uri = (
                    f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@127.0.0.1:{port}/"
                    f"?authSource={AUTH_DB}&directConnection=true"
                )
                read_preference = ReadPreference.SECONDARY_PREFERRED
            else:
                uri = f"mongodb://127.0.0.1:{port}/?directConnection=true"
                read_preference = ReadPreference.PRIMARY
            self._direct[key] = MongoClient(
                uri,
                serverSelectionTimeoutMS=1200,
                connectTimeoutMS=1200,
                socketTimeoutMS=2000,
                read_preference=read_preference,
                appname=f"CRUD-Direct-{port}",
            )
        return self._direct[key]

    def hello(self):
        return self.client.admin.command("hello")

    def list_users(self):
        return list(self.collection.find().sort("nombre", 1))

    def insert_user(self, nombre, apellido):
        result = self.collection.insert_one({"nombre": nombre, "apellido": apellido})
        return result.inserted_id

    def update_user(self, user_id, nombre, apellido):
        result = self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"nombre": nombre, "apellido": apellido}},
        )
        return result.modified_count

    def delete_user(self, user_id):
        return self.collection.delete_one({"_id": ObjectId(user_id)}).deleted_count

    def read_secondary(self):
        collection = self.collection.with_options(
            read_preference=ReadPreference.SECONDARY_PREFERRED
        )
        return list(collection.find().sort("nombre", 1))

    def read_each_node(self):
        result = {}
        for port in Constants.DATA_PORTS:
            try:
                collection = self.direct(port)[DB_NAME][COLLECTION_NAME]
                docs = list(collection.find().sort("nombre", 1))
                result[str(port)] = {
                    "ok": True,
                    "cantidad": len(docs),
                    "documentos": simplify_docs(docs),
                }
            except Exception as exc:
                result[str(port)] = {"ok": False, "error": str(exc)}
        return result

    def status_each_node(self):
        result = {}
        for node in Constants.NODES:
            port = node["port"]
            try:
                with_auth = port != 27120
                admin_db = self.direct(port, with_auth).get_database(
                    "admin",
                    codec_options=CodecOptions(
                        unicode_decode_error_handler="replace"
                    ),
                )
                status = admin_db.command("replSetGetStatus")
                result[str(port)] = {"ok": True, "status": status}
            except Exception as exc:
                result[str(port)] = {"ok": False, "error": str(exc)}
        return result

    def nodes_status(self):
        statuses = []
        for node in Constants.NODES:
            info = {
                "name": node["name"],
                "port": node["port"],
                "role": "APAGADO",
                "primary": None,
                "ok": False,
            }
            if port_open(node["port"]):
                try:
                    with_auth = node["port"] != 27120
                    hello = self.direct(node["port"], with_auth).admin.command("hello")
                    info["ok"] = True
                    info["primary"] = hello.get("primary")
                    if hello.get("arbiterOnly"):
                        info["role"] = "ARBITER"
                    elif hello.get("isWritablePrimary"):
                        info["role"] = "PRIMARY"
                    elif hello.get("secondary"):
                        info["role"] = "SECONDARY"
                    else:
                        info["role"] = "SIN ROL"
                except Exception:
                    info["role"] = "SIN RESPUESTA"
            statuses.append(info)
        return statuses

    def current_primary(self):
        for status in self.nodes_status():
            if status["role"] == "PRIMARY":
                return status
        return None

    def _close_direct(self, port):
        for key in [k for k in self._direct if k[0] == port]:
            cached = self._direct.pop(key, None)
            if cached:
                cached.close()

    def _kill_process_on_port(self, port):
        if os.name != "nt":
            raise RuntimeError("El apagado del arbitro solo esta soportado en Windows.")
        output = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        pid = None
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                pid = int(parts[4])
                break
        if pid is None:
            raise RuntimeError(f"No se encontro el proceso del puerto {port}.")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)

    def shutdown_node(self, port):
        if not port_open(port):
            raise RuntimeError(f"El nodo del puerto {port} ya está apagado.")
        error = None
        if port == 27120:
            self._kill_process_on_port(port)
            deadline = time.time() + 10
            while time.time() < deadline:
                if not port_open(port):
                    self._close_direct(port)
                    return
                time.sleep(0.2)
            raise RuntimeError("El arbitro sigue respondiendo; no se pudo apagar.")
        try:
            self.direct(port).admin.command({"shutdown": 1, "force": True})
        except PyMongoError as exc:
            error = exc
        deadline = time.time() + 40
        while time.time() < deadline:
            if not port_open(port):
                self._close_direct(port)
                return
            time.sleep(0.25)
        raise RuntimeError(f"No se pudo apagar el nodo {port}. {error or ''}".strip())

    def start_node(self, port):
        if port_open(port):
            raise RuntimeError(f"El nodo del puerto {port} ya está encendido.")
        node = next((n for n in Constants.NODES if n["port"] == port), None)
        if node is None:
            raise RuntimeError(f"El puerto {port} no pertenece al laboratorio.")
        cfg = node["cfg"]
        if not cfg.exists():
            raise RuntimeError(f"No existe el archivo de configuración: {cfg}")
        if not MONGOD_EXE.exists():
            raise RuntimeError(f"No se encontró mongod en: {MONGOD_EXE}")

        self._close_direct(port)

        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

        subprocess.Popen(
            [str(MONGOD_EXE), "--config", str(cfg)],
            cwd=str(Constants.LAB_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )

        deadline = time.time() + 25
        last_error = None
        while time.time() < deadline:
            if port_open(port):
                try:
                    self.direct(port, port != 27120).admin.command("hello")
                    return
                except Exception as exc:
                    last_error = exc
            time.sleep(0.4)
        raise RuntimeError(
            f"El nodo {port} no respondió tras el reinicio. {last_error or ''}".strip()
        )

    def wait_for_primary(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            primary = self.current_primary()
            if primary:
                return primary
            time.sleep(0.5)
        return None

