import socket

def simplify_docs(docs):
    return [
        {
            "_id": str(d.get("_id")),
            "nombre": d.get("nombre", ""),
            "apellido": d.get("apellido", ""),
        }
        for d in docs
    ]

def port_open(port, timeout=0.35):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False