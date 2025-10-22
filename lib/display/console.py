"""  simple client/server logger for debugging """

import datetime
import socket
import sys
import threading

HOST = "127.0.0.1"
PORT = 50505

# ──────────────────────────────
# CLIENT LOGGER
# ──────────────────────────────


def log(*args: list[str] | str) -> None:
    message = "".join(str(arg) for arg in args)
    try:
        with socket.create_connection((HOST, PORT), timeout=0.5) as sock:
            sock.sendall((message + "\n").encode("utf-8"))
    except (ConnectionRefusedError, socket.timeout):
        pass  # Fail silently if server not running


# Oredirect print() to console.log()
class ConsoleWriter:
    def write(self, text):
        if text.strip():
            log(text)

    def flush(self):
        pass


def redirect_stdout():
    sys.stdout = sys.stderr = ConsoleWriter()


# ──────────────────────────────
# SERVER FUNCTION
# ──────────────────────────────

def _handle_client(conn, addr):
    with conn:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{now}] {text.strip()}")


def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()
        print(f"🔌 Console server running on {HOST}:{PORT}")
        while True:
            conn, addr = server.accept()
            threading.Thread(target=_handle_client, args=(conn, addr), daemon=True).start()


# ──────────────────────────────
# MAIN ENTRYPOINT
# ──────────────────────────────

if __name__ == "__main__":
    run_server()
