import json
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
from bson.json_util import dumps
from managers.mongo_manager import MongoManager
from pymongo.errors import PyMongoError
from utils.constants import Constants
from utils.functions import simplify_docs, port_open

BG = "#f5f6f8"
GREEN = "#1a7f37"
RED = "#b42318"
ORANGE = "#b54708"
BLUE = "#175cd3"

def timestamp():
    return datetime.now().strftime("%H:%M:%S")

class App:
    def __init__(self, root):
        self.root = root
        self.manager = MongoManager()
        self.selected_id = None
        self._refreshing = False
        self._last_conn_ok = None
        self._build_ui()
        self.refresh_crud()
        self.refresh_status_async()
        self.root.after(5000, self._tick)

    def _build_ui(self):
        self.root.title("CRUD MongoDB - Replica Set RP")
        self.root.geometry("1020x720")
        self.root.minsize(940, 640)
        self.root.configure(bg=BG)

        header = tk.Frame(self.root, bg="#1f2937", padx=14, pady=10)
        header.pack(fill=tk.X)
        self.lbl_conn = tk.Label(
            header,
            text="Conectando...",
            bg="#1f2937",
            fg="#fbbf24",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_conn.pack(side=tk.RIGHT)

        status_frame = tk.LabelFrame(
            self.root,
            text=" Estado del replica set ",
            bg=BG,
            padx=10,
            pady=8,
            font=("Segoe UI", 9, "bold"),
        )
        status_frame.pack(fill=tk.X, padx=12, pady=(8, 4))
        self.lbl_primary = tk.Label(
            status_frame,
            text="Primario: consultando...",
            bg=BG,
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_primary.pack(fill=tk.X)
        self.lbl_members = tk.Label(
            status_frame,
            text="Miembros: consultando...",
            bg=BG,
            anchor="w",
            font=("Consolas", 9),
        )
        self.lbl_members.pack(fill=tk.X, pady=(4, 0))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        self._build_crud_tab()
        self._build_sim_tab()
        self._build_tests_tab()

        self.log("Aplicacion iniciada. Conexion: replicaSet=RP, authSource=admin.")

    def _build_crud_tab(self):
        tab = tk.Frame(self.notebook, bg=BG, padx=10, pady=10)
        self.notebook.add(tab, text="CRUD de usuarios")

        form = tk.LabelFrame(
            tab,
            text=" Datos del usuario ",
            bg=BG,
            padx=10,
            pady=10,
            font=("Segoe UI", 9, "bold"),
        )
        form.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        tk.Label(form, text="Nombre:", bg=BG).pack(anchor="w")
        self.ent_nombre = tk.Entry(form, width=28, font=("Segoe UI", 10))
        self.ent_nombre.pack(pady=(2, 10), fill=tk.X)

        tk.Label(form, text="Apellido:", bg=BG).pack(anchor="w")
        self.ent_apellido = tk.Entry(form, width=28, font=("Segoe UI", 10))
        self.ent_apellido.pack(pady=(2, 12), fill=tk.X)

        tk.Button(
            form,
            text="Guardar",
            bg=GREEN,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self.save_user,
        ).pack(fill=tk.X, pady=3)
        tk.Button(
            form,
            text="Actualizar seleccionado",
            bg=BLUE,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self.update_user,
        ).pack(fill=tk.X, pady=3)
        tk.Button(
            form,
            text="Eliminar seleccionado",
            bg=RED,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self.delete_user,
        ).pack(fill=tk.X, pady=3)
        tk.Button(
            form,
            text="Limpiar campos",
            command=self.clear_form,
        ).pack(fill=tk.X, pady=(12, 3))
        tk.Button(
            form,
            text="Recargar desde el primario",
            command=self.refresh_crud,
        ).pack(fill=tk.X, pady=3)

        table_frame = tk.Frame(tab, bg=BG)
        table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        columns = ("id", "nombre", "apellido")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("nombre", text="Nombre")
        self.tree.heading("apellido", text="Apellido")
        self.tree.column("id", width=230, anchor="w")
        self.tree.column("nombre", width=150, anchor="w")
        self.tree.column("apellido", width=150, anchor="w")

        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

    def _build_sim_tab(self):
        tab = tk.Frame(self.notebook, bg=BG, padx=10, pady=10)
        self.notebook.add(tab, text="Replica, apagado y reinicio")

        top = tk.Frame(tab, bg=BG)
        top.pack(fill=tk.X)

        columns = ("nodo", "puerto", "rol", "primario")
        self.tree_nodes = ttk.Treeview(
            top, columns=columns, show="headings", height=5, selectmode="browse"
        )
        self.tree_nodes.heading("nodo", text="Nodo")
        self.tree_nodes.heading("puerto", text="Puerto")
        self.tree_nodes.heading("rol", text="Rol actual")
        self.tree_nodes.heading("primario", text="Primario conocido")
        self.tree_nodes.column("nodo", width=120)
        self.tree_nodes.column("puerto", width=80, anchor="center")
        self.tree_nodes.column("rol", width=140, anchor="center")
        self.tree_nodes.column("primario", width=190, anchor="center")
        self.tree_nodes.pack(fill=tk.X)

        buttons = tk.Frame(tab, bg=BG, pady=8)
        buttons.pack(fill=tk.X)

        tk.Button(
            buttons,
            text="Actualizar estado",
            command=self.refresh_status_async,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            buttons,
            text="Apagar nodo seleccionado",
            bg=RED,
            fg="white",
            command=self.shutdown_selected,
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            buttons,
            text="Reiniciar nodo seleccionado",
            bg=GREEN,
            fg="white",
            command=self.restart_selected,
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            buttons,
            text="Apagar el PRIMARIO",
            bg="#7a271a",
            fg="white",
            command=self.shutdown_primary,
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            buttons,
            text="Reiniciar todos los apagados",
            command=self.restart_all_down,
        ).pack(side=tk.LEFT, padx=6)

        log_frame = tk.LabelFrame(
            tab, text=" Registro de eventos ", bg=BG, padx=6, pady=6,
            font=("Segoe UI", 9, "bold")
        )
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.txt_log = tk.Text(
            log_frame, height=12, state=tk.DISABLED, font=("Consolas", 9), bg="#ffffff"
        )
        log_scroll = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.txt_log.yview
        )
        self.txt_log.configure(yscrollcommand=log_scroll.set)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_tests_tab(self):
        tab = tk.Frame(self.notebook, bg=BG, padx=10, pady=10)
        self.notebook.add(tab, text="Pruebas de replicacion")

        buttons = tk.Frame(tab, bg=BG)
        buttons.pack(fill=tk.X, pady=(0, 8))

        tk.Button(
            buttons,
            text="Leer desde un secundario (SECONDARY_PREFERRED)",
            bg=BLUE,
            fg="white",
            command=self.show_secondary,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            buttons,
            text="Leer directamente de 27117, 27118 y 27119",
            bg="#344054",
            fg="white",
            command=self.show_each_node,
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            buttons,
            text="Estado de cada nodo",
            bg="#6941c6",
            fg="white",
            command=self.show_status_each_node,
        ).pack(side=tk.LEFT, padx=6)
        tk.Button(
            buttons,
            text="Limpiar",
            command=lambda: self.set_output(""),
        ).pack(side=tk.LEFT, padx=6)

        self.txt_output = tk.Text(
            tab, state=tk.DISABLED, font=("Consolas", 9), bg="#ffffff", wrap=tk.NONE
        )
        scroll_y = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.txt_output.yview)
        scroll_x = ttk.Scrollbar(tab, orient=tk.HORIZONTAL, command=self.txt_output.xview)
        self.txt_output.configure(
            yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set
        )
        self.txt_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

    def log(self, message):
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f"[{timestamp()}] {message}\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state=tk.DISABLED)

    def set_output(self, text):
        self.txt_output.configure(state=tk.NORMAL)
        self.txt_output.delete("1.0", tk.END)
        self.txt_output.insert(tk.END, text)
        self.txt_output.configure(state=tk.DISABLED)

    def clear_form(self):
        self.selected_id = None
        self.ent_nombre.delete(0, tk.END)
        self.ent_apellido.delete(0, tk.END)
        self.tree.selection_remove(self.tree.selection())

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        self.selected_id = values[0]
        self.ent_nombre.delete(0, tk.END)
        self.ent_nombre.insert(0, values[1])
        self.ent_apellido.delete(0, tk.END)
        self.ent_apellido.insert(0, values[2])

    def refresh_crud(self):
        try:
            docs = self.manager.list_users()
        except Exception as exc:
            self.log(f"No se pudo leer la coleccion: {exc}")
            messagebox.showerror(
                "Sin conexion",
                "No se pudo leer desde el replica set.\n\n"
                "Verifica que exista un primario disponible.\n\n"
                f"Detalle: {exc}",
            )
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for doc in docs:
            self.tree.insert(
                "",
                tk.END,
                iid=str(doc["_id"]),
                values=(
                    str(doc["_id"]),
                    doc.get("nombre", ""),
                    doc.get("apellido", ""),
                ),
            )
        self.log(f"Usuarios cargados desde el primario: {len(docs)}")

    def save_user(self):
        nombre = self.ent_nombre.get().strip()
        apellido = self.ent_apellido.get().strip()
        if not nombre or not apellido:
            messagebox.showwarning("Validacion", "Completa nombre y apellido.")
            return
        try:
            user_id = self.manager.insert_user(nombre, apellido)
        except PyMongoError as exc:
            self.log(f"Error al insertar: {exc}")
            messagebox.showerror(
                "Error al guardar",
                "No se pudo guardar. Si acabas de apagar el primario, "
                "espera unos segundos a que ocurra la eleccion.\n\n"
                f"Detalle: {exc}",
            )
            return
        self.log(f"Usuario insertado con _id={user_id}")
        self.clear_form()
        self.refresh_crud()
        messagebox.showinfo("Guardado", "Usuario guardado con exito.")

    def update_user(self):
        if not self.selected_id:
            messagebox.showwarning("Seleccion", "Selecciona un usuario de la tabla.")
            return
        nombre = self.ent_nombre.get().strip()
        apellido = self.ent_apellido.get().strip()
        if not nombre or not apellido:
            messagebox.showwarning("Validacion", "Completa nombre y apellido.")
            return
        try:
            modified = self.manager.update_user(self.selected_id, nombre, apellido)
        except PyMongoError as exc:
            self.log(f"Error al actualizar: {exc}")
            messagebox.showerror("Error al actualizar", str(exc))
            return
        self.log(f"Usuario {self.selected_id} actualizado (modificados={modified})")
        self.clear_form()
        self.refresh_crud()
        messagebox.showinfo("Actualizado", "Usuario actualizado con exito.")

    def delete_user(self):
        if not self.selected_id:
            messagebox.showwarning("Seleccion", "Selecciona un usuario de la tabla.")
            return
        if not messagebox.askyesno(
            "Confirmar", "¿Eliminar el usuario seleccionado?"
        ):
            return
        try:
            deleted = self.manager.delete_user(self.selected_id)
        except PyMongoError as exc:
            self.log(f"Error al eliminar: {exc}")
            messagebox.showerror("Error al eliminar", str(exc))
            return
        self.log(f"Usuario {self.selected_id} eliminado (eliminados={deleted})")
        self.clear_form()
        self.refresh_crud()
        messagebox.showinfo("Eliminado", "Usuario eliminado con exito.")

    def show_secondary(self):
        try:
            docs = self.manager.read_secondary()
        except Exception as exc:
            self.log(f"Error leyendo de secundario: {exc}")
            messagebox.showerror("Error de lectura", str(exc))
            return
        text = (
            "Lectura con readPreference=SECONDARY_PREFERRED\n"
            "El driver elige un secundario si esta disponible.\n\n"
            + json.dumps(simplify_docs(docs), indent=2, ensure_ascii=False)
        )
        self.set_output(text)
        self.log(f"Leidos {len(docs)} documentos desde un secundario.")

    def show_each_node(self):
        data = self.manager.read_each_node()
        lines = [
            "Lectura directa contra cada nodo (directConnection=true).",
            "Los tres nodos de datos deben mostrar la misma informacion.",
            "",
        ]
        for port in Constants.DATA_PORTS:
            info = data[str(port)]
            lines.append(f"===== Nodo {port} =====")
            if info["ok"]:
                lines.append(f"Documentos: {info['cantidad']}")
                lines.append(
                    json.dumps(info["documentos"], indent=2, ensure_ascii=False)
                )
            else:
                lines.append(f"ERROR: {info['error']}")
            lines.append("")
        self.set_output("\n".join(lines))
        self.log("Comparacion de datos ejecutada en los 3 nodos de datos.")

    def show_status_each_node(self):
        data = self.manager.status_each_node()
        lines = [
            "rs.status() ejecutado directamente en cada nodo.",
            "",
        ]
        for node in Constants.NODES:
            info = data[str(node["port"])]
            lines.append(f"===== {node['name']} (puerto {node['port']}) =====")
            if info["ok"]:
                status = info["status"]
                lines.append(
                    f"set={status.get('set')} | myState={status.get('myState')} | "
                    f"ok={status.get('ok')}"
                )
                lines.append(dumps(status, indent=2, ensure_ascii=False))
            else:
                lines.append(f"ERROR: {info['error']}")
            lines.append("")
        self.set_output("\n".join(lines))
        self.log("rs.status() consultado en los 4 nodos.")

    def refresh_status_async(self):
        if self._refreshing:
            return
        self._refreshing = True
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self):
        statuses = self.manager.nodes_status()
        hello = None
        error = None
        try:
            hello = self.manager.hello()
        except Exception as exc:
            error = exc
        self.root.after(0, lambda: self._apply_status(statuses, hello, error))

    def _apply_status(self, statuses, hello, error):
        self._refreshing = False
        primary = next((s for s in statuses if s["role"] == "PRIMARY"), None)

        if hello:
            self.lbl_conn.configure(
                text=f"Conectado · primario {hello.get('primary')}", fg="#4ade80"
            )
            self.lbl_primary.configure(
                text=f"Primario actual: {hello.get('primary')}  |  conectado a: {hello.get('me')}",
                fg=GREEN,
            )
            if self._last_conn_ok is not True:
                self.log("Conexion con el replica set restablecida.")
            self._last_conn_ok = True
        else:
            if primary:
                self.lbl_conn.configure(
                    text="Reconectando con el nuevo primario...", fg="#fbbf24"
                )
                self.lbl_primary.configure(
                    text=f"Primario elegido: {primary['primary'] or primary['port']} (aun sincronizando)",
                    fg=ORANGE,
                )
            else:
                self.lbl_conn.configure(
                    text="Sin primario: eleccion en curso...", fg="#f87171"
                )
                self.lbl_primary.configure(
                    text="No hay primario disponible en este momento.", fg=RED
                )
            if self._last_conn_ok is not False:
                self.log("Sin primario disponible; el replica set esta eligiendo.")
            self._last_conn_ok = False

        parts = [f"{s['port']} {s['role']}" for s in statuses]
        self.lbl_members.configure(text="Miembros:  " + "   |   ".join(parts))

        selected = self.tree_nodes.selection()
        self.tree_nodes.delete(*self.tree_nodes.get_children())
        for status in statuses:
            self.tree_nodes.insert(
                "",
                tk.END,
                iid=str(status["port"]),
                values=(
                    status["name"],
                    status["port"],
                    status["role"],
                    status["primary"] or "-",
                ),
            )
        for item in selected:
            if self.tree_nodes.exists(item):
                self.tree_nodes.selection_set(item)

    def _tick(self):
        self.refresh_status_async()
        self.root.after(5000, self._tick)

    def _selected_port(self):
        selection = self.tree_nodes.selection()
        if not selection:
            messagebox.showwarning("Seleccion", "Selecciona un nodo de la tabla.")
            return None
        return int(selection[0])

    def _run_node_action(self, port, action):
        label = next((n["name"] for n in Constants.NODES if n["port"] == port), str(port))
        was_primary = False
        if action == "shutdown":
            current = self.manager.current_primary()
            was_primary = current is not None and current["port"] == port
            if not messagebox.askyesno(
                "Confirmar apagado",
                f"¿Apagar {label} (puerto {port})?\n\n"
                + (
                    "Es el PRIMARIO actual. Se producira una eleccion."
                    if was_primary
                    else (
                        "Es el arbitro (no almacena datos)."
                        if port == 27120
                        else "Es un nodo secundario."
                    )
                ),
            ):
                return
            self.log(f"Apagando {label} (puerto {port})...")
        else:
            self.log(f"Reiniciando {label} (puerto {port})...")

        def worker():
            try:
                if action == "shutdown":
                    self.manager.shutdown_node(port)
                    self.root.after(0, lambda: self.log(f"{label} apagado."))
                    if was_primary:
                        self.root.after(
                            0, lambda: self.log("Esperando eleccion de nuevo primario...")
                        )
                        new_primary = self.manager.wait_for_primary(timeout=35)
                        if new_primary:
                            message = (
                                f"Nuevo primario: {new_primary['name']} "
                                f"(puerto {new_primary['port']})."
                            )
                        else:
                            message = "No se detecto un nuevo primario a tiempo."
                        self.root.after(0, lambda msg=message: self.log(msg))
                else:
                    self.manager.start_node(port)
                    self.root.after(
                        0,
                        lambda: self.log(
                            f"{label} reiniciado y autenticado correctamente."
                        ),
                    )
            except Exception as exc:
                self.root.after(
                    0,
                    lambda err=str(exc): (
                        self.log(f"ERROR: {err}"),
                        messagebox.showerror("Error en la operacion", err),
                    ),
                )
            finally:
                self.root.after(0, self.refresh_status_async)

        threading.Thread(target=worker, daemon=True).start()

    def shutdown_selected(self):
        port = self._selected_port()
        if port is not None:
            self._run_node_action(port, "shutdown")

    def restart_selected(self):
        port = self._selected_port()
        if port is not None:
            if port_open(port):
                messagebox.showinfo(
                    "Nodo encendido",
                    f"El nodo del puerto {port} ya esta en ejecucion.",
                )
                return
            self._run_node_action(port, "restart")

    def shutdown_primary(self):
        primary = self.manager.current_primary()
        if not primary:
            messagebox.showerror(
                "Sin primario",
                "No se detecta un primario en este momento.",
            )
            return
        self._run_node_action(primary["port"], "shutdown")

    def restart_all_down(self):
        down = [n for n in Constants.NODES if not port_open(n["port"])]
        if not down:
            messagebox.showinfo("Todo encendido", "No hay nodos apagados.")
            return
        ports = [n["port"] for n in down]

        def worker():
            for port in ports:
                name = next(n["name"] for n in Constants.NODES if n["port"] == port)
                try:
                    self.manager.start_node(port)
                    self.root.after(
                        0, lambda n=name, p=port: self.log(f"{n} ({p}) reiniciado.")
                    )
                except Exception as exc:
                    self.root.after(
                        0,
                        lambda err=str(exc), p=port: self.log(
                            f"ERROR al reiniciar {p}: {err}"
                        ),
                    )
            self.root.after(0, self.refresh_status_async)

        threading.Thread(target=worker, daemon=True).start()
