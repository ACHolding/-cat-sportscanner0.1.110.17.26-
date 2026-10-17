#!/usr/bin/env python3
# catportscannerv0.1a.py - Cat Port Scanner (tkinter, 1920x1080 centered)
# Blue text, black buttons.
# Only scan hosts you own or have permission to test.

import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from concurrent.futures import ThreadPoolExecutor

BLUE = "#3399ff"
BG = "#0a0a14"
BTN_BG = "#000000"
WIN_W, WIN_H = 1920, 1080

COMMON_SERVICES = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 80: "http",
    110: "pop3", 135: "msrpc", 139: "netbios", 143: "imap", 443: "https",
    445: "smb", 993: "imaps", 995: "pop3s", 1433: "mssql", 3306: "mysql",
    3389: "rdp", 5432: "postgres", 5900: "vnc", 8080: "http-alt",
}


class CatPortScanner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cat Port Scanner v0.1a")
        self.resizable(True, True)
        self.configure(bg=BG)
        self._center_on_os(WIN_W, WIN_H)

        self.stop_event = threading.Event()
        self.scanning = False

        self._build_ui()
        # Re-center after widgets map (macOS / multi-monitor safe)
        self.after_idle(lambda: self._center_on_os(WIN_W, WIN_H))

    def _center_on_os(self, w: int, h: int) -> None:
        """Place a WxH window in the center of the primary OS display (e.g. 1920x1080)."""
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # Clamp to screen so centering still works if the display is smaller
        w = min(w, sw)
        h = min(h, sh)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _label(self, parent, text):
        return tk.Label(parent, text=text, fg=BLUE, bg=BG, font=("Consolas", 10))

    def _entry(self, parent, width, default):
        e = tk.Entry(parent, width=width, fg=BLUE, bg="#111122",
                     insertbackground=BLUE, relief="flat",
                     font=("Consolas", 10))
        e.insert(0, default)
        return e

    def _button(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, fg=BLUE, bg=BTN_BG,
                         activeforeground="#66bbff", activebackground="#111111",
                         relief="flat", bd=0, padx=12, pady=4,
                         font=("Consolas", 10, "bold"), cursor="hand2")

    def _build_ui(self):
        # Everything lives in one frame centred in the window
        main = tk.Frame(self, bg=BG)
        main.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(main, text="=^.^= CAT PORT SCANNER", fg=BLUE, bg=BG,
                 font=("Consolas", 28, "bold")).pack(pady=(8, 12))

        top = tk.Frame(main, bg=BG)
        top.pack(pady=8)

        self._label(top, "Host:").grid(row=0, column=0, sticky="w")
        self.host_entry = self._entry(top, 22, "127.0.0.1")
        self.host_entry.grid(row=0, column=1, padx=4)

        self._label(top, "Start:").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.start_entry = self._entry(top, 6, "1")
        self.start_entry.grid(row=0, column=3, padx=4)

        self._label(top, "End:").grid(row=0, column=4, sticky="w")
        self.end_entry = self._entry(top, 6, "1024")
        self.end_entry.grid(row=0, column=5, padx=4)

        self._label(top, "Timeout(s):").grid(row=1, column=0, sticky="w", pady=4)
        self.timeout_entry = self._entry(top, 6, "0.5")
        self.timeout_entry.grid(row=1, column=1, sticky="w", padx=4)

        self._label(top, "Threads:").grid(row=1, column=2, sticky="w", padx=(8, 0))
        self.threads_entry = self._entry(top, 6, "100")
        self.threads_entry.grid(row=1, column=3, padx=4)

        btns = tk.Frame(main, bg=BG)
        btns.pack(pady=8)
        self.scan_btn = self._button(btns, "Scan", self.start_scan)
        self.scan_btn.pack(side="left", padx=4)
        self.stop_btn = self._button(btns, "Stop", self.stop_scan)
        self.stop_btn.pack(side="left", padx=4)
        self._button(btns, "Clear", self.clear).pack(side="left", padx=4)

        frame = tk.Frame(main, bg=BG)
        frame.pack(padx=10, pady=8)
        self.output = tk.Text(frame, bg="#05050c", fg=BLUE, width=110, height=24,
                              font=("Consolas", 12), relief="flat",
                              insertbackground=BLUE)
        sb = tk.Scrollbar(frame, command=self.output.yview)
        self.output.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Cat.Horizontal.TProgressbar", troughcolor=BG,
                        background=BLUE, bordercolor=BG,
                        lightcolor=BLUE, darkcolor=BLUE)
        self.progress = ttk.Progressbar(main, style="Cat.Horizontal.TProgressbar",
                                        length=900, mode="determinate")
        self.progress.pack(padx=10, pady=(4, 2))

        self.status = tk.Label(main, text="Idle", fg=BLUE, bg=BG,
                               font=("Consolas", 11), anchor="center")
        self.status.pack(fill="x", padx=10, pady=(0, 4))

    # ---- helpers (thread-safe UI updates) ----
    def log(self, msg):
        self.after(0, lambda: (self.output.insert("end", msg + "\n"),
                               self.output.see("end")))

    def set_status(self, msg):
        self.after(0, lambda: self.status.config(text=msg))

    def clear(self):
        self.output.delete("1.0", "end")
        self.progress["value"] = 0

    # ---- scanning ----
    def start_scan(self):
        if self.scanning:
            return
        try:
            host = self.host_entry.get().strip()
            start = int(self.start_entry.get())
            end = int(self.end_entry.get())
            timeout = float(self.timeout_entry.get())
            threads = max(1, min(500, int(self.threads_entry.get())))
            if not host or not (1 <= start <= end <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("Input error",
                                 "Check host and ports (1-65535, start <= end).")
            return
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror:
            messagebox.showerror("Error", f"Cannot resolve host: {host}")
            return

        self.stop_event.clear()
        self.scanning = True
        self.progress["maximum"] = end - start + 1
        self.progress["value"] = 0
        self.log(f"[*] Scanning {host} ({ip}) ports {start}-{end}")
        threading.Thread(target=self._scan,
                         args=(ip, start, end, timeout, threads),
                         daemon=True).start()

    def stop_scan(self):
        if self.scanning:
            self.stop_event.set()
            self.set_status("Stopping...")

    def _probe(self, ip, port, timeout):
        if self.stop_event.is_set():
            return
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                if s.connect_ex((ip, port)) == 0:
                    svc = COMMON_SERVICES.get(port)
                    if not svc:
                        try:
                            svc = socket.getservbyport(port)
                        except OSError:
                            svc = "unknown"
                    self.log(f"[+] {port}/tcp open  {svc}")
                    self.found.append(port)
        except OSError:
            pass
        finally:
            self.after(0, lambda: self.progress.step(1))

    def _scan(self, ip, start, end, timeout, threads):
        self.found = []
        self.set_status("Scanning...")
        with ThreadPoolExecutor(max_workers=threads) as ex:
            for port in range(start, end + 1):
                ex.submit(self._probe, ip, port, timeout)
        stopped = self.stop_event.is_set()
        self.log(f"[*] {'Stopped' if stopped else 'Done'}. "
                 f"{len(self.found)} open port(s).")
        self.set_status("Stopped" if stopped else "Finished")
        self.scanning = False


if __name__ == "__main__":
    CatPortScanner().mainloop()
