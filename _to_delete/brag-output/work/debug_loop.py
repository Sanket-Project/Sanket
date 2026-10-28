import http.server
import threading
import subprocess
import os
import sys
import time

PORT = 8998
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
COMP_DIR = os.path.join(ROOT_DIR, 'brag-output', 'composition')

class DebugHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        print(f"DEBUG GET: {self.path}", flush=True)
        if self.path.startswith('/log'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')
            return

        if self.path == '/' or self.path.startswith('/render.html'):
            with open(os.path.join(COMP_DIR, 'render.html'), 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path.startswith('/assets/'):
            rel_path = self.path[len('/assets/'):]
            local_file = os.path.join(COMP_DIR, 'assets', rel_path.replace('/', os.sep))
            if os.path.exists(local_file) and os.path.isfile(local_file):
                with open(local_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        print(f"DEBUG POST: {self.path}", flush=True)
        content_len = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(content_len)
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')

server = http.server.HTTPServer(('127.0.0.1', PORT), DebugHandler)
t = threading.Thread(target=server.serve_forever)
t.start()
print("Debug Server ready on", PORT, flush=True)

chrome_exe = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
cmd = [
    chrome_exe,
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--enable-logging=stderr',
    '--v=1',
    f'http://127.0.0.1:{PORT}/render.html'
]
proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)

# Let it run for 10 seconds and print all requests
time.sleep(10)
proc.terminate()
server.shutdown()
t.join()
print("Finished debug loop.")
