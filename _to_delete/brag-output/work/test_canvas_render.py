import http.server
import threading
import subprocess
import os
import sys
import time

PORT = 8976

class FrameHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Quiet

    def do_GET(self):
        if self.path == '/':
            html = """
            <!DOCTYPE html>
            <html>
            <body>
            <canvas id="c" width="400" height="300"></canvas>
            <script>
            async function run() {
                const c = document.getElementById('c');
                const ctx = c.getContext('2d');
                for (let i = 0; i < 5; i++) {
                    ctx.fillStyle = i % 2 === 0 ? 'red' : 'blue';
                    ctx.fillRect(0, 0, 400, 300);
                    ctx.fillStyle = 'white';
                    ctx.font = '30px sans-serif';
                    ctx.fillText('Frame ' + i, 50, 150);
                    const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.9));
                    await fetch('/frame?idx=' + i, { method: 'POST', body: blob });
                }
                await fetch('/done', { method: 'POST' });
            }
            window.onload = run;
            </script>
            </body>
            </html>
            """
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith('/frame'):
            content_len = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(content_len)
            idx = self.path.split('=')[-1]
            os.makedirs('test_frames', exist_ok=True)
            with open(f'test_frames/frame_{idx}.jpg', 'wb') as f:
                f.write(data)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
        elif self.path == '/done':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            threading.Thread(target=self.server.shutdown).start()

def main():
    server = http.server.HTTPServer(('127.0.0.1', PORT), FrameHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if not os.path.exists(chrome_path):
        chrome_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

    cmd = [chrome_path, '--headless=new', '--disable-gpu', '--no-sandbox', f'http://127.0.0.1:{PORT}/']
    proc = subprocess.Popen(cmd)
    server_thread.join(timeout=15)
    proc.terminate()

    files = os.listdir('test_frames') if os.path.exists('test_frames') else []
    print(f'Test completed! Frames received: {len(files)}')
    # cleanup
    for f in files:
        os.remove(os.path.join('test_frames', f))
    if os.path.exists('test_frames'):
        os.rmdir('test_frames')

if __name__ == '__main__':
    main()
