import http.server
import threading
import subprocess
import os
import sys
import time

PORT = 8995
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
COMP_DIR = os.path.join(ROOT_DIR, 'brag-output', 'composition')

class TestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"GET: {self.path}")
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
        print(f"POST: {self.path}")
        content_len = int(self.headers.get('Content-Length', 0))
        self.rfile.read(content_len)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')
        if self.path == '/done':
            threading.Thread(target=self.server.shutdown).start()

server = http.server.HTTPServer(('127.0.0.1', PORT), TestHandler)
t = threading.Thread(target=server.serve_forever)
t.start()
print("Server ready on", PORT)

chrome_exe = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
cmd = [chrome_exe, '--headless=new', '--disable-gpu', '--no-sandbox', f'http://127.0.0.1:{PORT}/render.html']
print("Running chrome...")
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
t.join(timeout=15)
try:
    proc.terminate()
except:
    pass
print("Done!")
