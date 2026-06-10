#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError as error:
    if error.name == "tkinter":
        print("tkinter is required. Install it with: sudo apt install python3-tk", file=sys.stderr)
        raise SystemExit(1) from error
    raise


class HideMeSystemdGUI:
    SERVER_SUFFIX = ".hideservers.net"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Hide.me Systemd Manager")
        self.root.geometry("600x400")
        self.root.minsize(560, 360)

        self.config_file = Path.home() / ".hideme_servers.json"
        self.launcher_file = Path.home() / ".local" / "share" / "applications" / "hideme-systemd-gui.desktop"
        self.autostart_file = Path.home() / ".config" / "autostart" / "hideme-systemd-gui.desktop"

        self.servers = self.load_servers()
        self.server_var = tk.StringVar()
        self.startup_var = tk.BooleanVar(value=self.autostart_file.exists())
        self.status_var = tk.StringVar(value="Ready")

        self._setup_styles()
        self._build_layout()
        self._ensure_launcher_entry()

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.configure("Large.TButton", font=("Sans", 12), padding=(10, 10))
        style.configure("Large.TCombobox", font=("Sans", 13), padding=6)
        style.configure("Header.TLabel", font=("Sans", 13, "bold"))

    def _build_layout(self):
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Hide.me VPN Server", style="Header.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        server_row = ttk.Frame(container)
        server_row.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        server_row.columnconfigure(0, weight=1)

        self.dropdown = ttk.Combobox(
            server_row,
            textvariable=self.server_var,
            values=self.servers,
            style="Large.TCombobox",
            state="normal",
            width=40,
        )
        self.dropdown.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ttk.Button(server_row, text="Save Server", style="Large.TButton", command=self.add_server).grid(
            row=0, column=1, sticky="ew"
        )

        ttk.Button(server_row, text="Remove", style="Large.TButton", command=self.remove_server).grid(
            row=0, column=2, sticky="ew", padx=(8, 0)
        )

        action_row = ttk.Frame(container)
        action_row.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        action_row.columnconfigure((0, 1), weight=1)

        ttk.Button(action_row, text="Start VPN", style="Large.TButton", command=self.start).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(action_row, text="Stop VPN", style="Large.TButton", command=self.stop).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        ttk.Checkbutton(
            container,
            text="Run on startup",
            variable=self.startup_var,
            command=self.toggle_startup,
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))

        status_frame = ttk.LabelFrame(container, text="Status", padding=12)
        status_frame.grid(row=4, column=0, sticky="nsew")
        container.rowconfigure(4, weight=1)
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            wraplength=530,
        )
        self.status_label.grid(row=0, column=0, sticky="nw")

    def load_servers(self):
        if not self.config_file.exists():
            return []

        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [s for s in data if isinstance(s, str)]
        except (json.JSONDecodeError, OSError):
            pass

        return []

    def save_servers(self):
        self.config_file.write_text(json.dumps(self.servers, indent=2), encoding="utf-8")

    @classmethod
    def normalize_server(cls, value: str):
        server = value.strip().lower()
        if server.endswith(cls.SERVER_SUFFIX):
            server = server[: -len(cls.SERVER_SUFFIX)]

        if not server:
            return ""

        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", server):
            return ""

        return server

    def selected_server(self):
        server = self.normalize_server(self.server_var.get())
        if not server:
            return ""
        return f"{server}{self.SERVER_SUFFIX}"

    def add_server(self):
        normalized = self.normalize_server(self.server_var.get())
        if not normalized:
            self.set_status("Enter a valid server (example: ep-ru2 or ep-ru2.hideservers.net)", "error")
            return

        if normalized in self.servers:
            self.server_var.set(normalized)
            self.set_status(f"Server already saved: {normalized}", "info")
            return

        self.servers.append(normalized)
        self.servers.sort()
        self.save_servers()
        self.dropdown["values"] = self.servers
        self.server_var.set(normalized)
        self.set_status(f"Saved server: {normalized}", "success")

    def remove_server(self):
        normalized = self.normalize_server(self.server_var.get())
        if not normalized:
            self.set_status("Select or enter a valid server to remove", "error")
            return

        if normalized not in self.servers:
            self.set_status(f"Server not found: {normalized}", "info")
            return

        self.servers.remove(normalized)
        self.save_servers()
        self.dropdown["values"] = self.servers
        self.server_var.set("")
        self.set_status(f"Removed server: {normalized}", "success")

    def start(self):
        self.run_systemctl("start")

    def stop(self):
        self.run_systemctl("stop")

    def run_systemctl(self, action: str):
        server = self.selected_server()
        if not server:
            self.set_status("Select a valid server first", "error")
            return

        unit = f"hide.me@{server}"
        command = ["systemctl", action, unit]

        if os.geteuid() != 0:
            if shutil.which("pkexec"):
                command = ["pkexec", *command]
            else:
                self.set_status("Admin privileges are required. Install pkexec or run this app with sufficient rights.", "error")
                return

        try:
            completed = subprocess.run(command, check=True, text=True, capture_output=True)
            output = (completed.stdout or "").strip() or (completed.stderr or "").strip()
            self.set_status(f"Success: systemctl {action} {unit}" + (f"\n{output}" if output else ""), "success")
        except subprocess.CalledProcessError as error:
            output = (error.stderr or error.stdout or str(error)).strip()
            self.set_status(f"Failed: systemctl {action} {unit}\n{output}", "error")

    def set_status(self, message: str, level: str):
        self.status_var.set(message)
        colors = {
            "success": "#146c2e",
            "error": "#b3261e",
            "info": "#234f9a",
        }
        self.status_label.configure(foreground=colors.get(level, "#222"))

    def launcher_content(self, autostart: bool = False):
        exec_path = os.path.abspath(sys.argv[0])
        content = [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=Hide.me Systemd GUI",
            "Comment=Manage Hide.me systemd VPN services",
            f'Exec=python3 "{exec_path}"',
            "Icon=network-vpn",
            "Terminal=false",
            "Categories=Network;Utility;",
        ]
        if autostart:
            content.append("X-GNOME-Autostart-enabled=true")
        return "\n".join(content) + "\n"

    def _ensure_launcher_entry(self):
        try:
            self.launcher_file.parent.mkdir(parents=True, exist_ok=True)
            self.launcher_file.write_text(self.launcher_content(), encoding="utf-8")
        except OSError as error:
            self.set_status(f"Could not create launcher entry: {error}", "error")

    def toggle_startup(self):
        enabled = self.startup_var.get()

        if enabled:
            try:
                self.autostart_file.parent.mkdir(parents=True, exist_ok=True)
                self.autostart_file.write_text(self.launcher_content(autostart=True), encoding="utf-8")
                self.set_status("Startup enabled", "success")
            except OSError as error:
                self.startup_var.set(False)
                self.set_status(f"Could not enable startup: {error}", "error")
        else:
            try:
                if self.autostart_file.exists():
                    self.autostart_file.unlink()
                self.set_status("Startup disabled", "info")
            except OSError as error:
                self.startup_var.set(True)
                self.set_status(f"Could not disable startup: {error}", "error")


def main():
    root = tk.Tk()
    HideMeSystemdGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
