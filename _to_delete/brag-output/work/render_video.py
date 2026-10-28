import http.server
import threading
import subprocess
import os
import sys
import time
import shutil

PORT = 8996
TOTAL_FRAMES = 750
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
COMP_DIR = os.path.join(ROOT_DIR, 'brag-output', 'composition')
WORK_DIR = os.path.join(ROOT_DIR, 'brag-output', 'work')
FRAMES_DIR = os.path.join(WORK_DIR, 'frames')
OUTPUT_DIR = os.path.join(ROOT_DIR, 'brag-output')

os.makedirs(FRAMES_DIR, exist_ok=True)

class VideoRenderHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        url_path = self.path.split('?')[0]
        if url_path.startswith('/log'):
            print("[Browser Log]", self.path, flush=True)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')
            return

        if url_path == '/' or url_path == '/render.html':
            render_file = os.path.join(COMP_DIR, 'render.html')
            with open(render_file, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif url_path.startswith('/assets/'):
            rel_path = url_path[len('/assets/'):]
            local_file = os.path.join(COMP_DIR, 'assets', rel_path.replace('/', os.sep))
            if os.path.exists(local_file) and os.path.isfile(local_file):
                ext = os.path.splitext(local_file)[1].lower()
                mime = 'application/octet-stream'
                if ext == '.png': mime = 'image/png'
                elif ext == '.jpg' or ext == '.jpeg': mime = 'image/jpeg'
                elif ext == '.svg': mime = 'image/svg+xml'
                elif ext == '.mp3': mime = 'audio/mpeg'
                elif ext == '.ogg': mime = 'audio/ogg'
                
                with open(local_file, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, f"Asset not found: {url_path}")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith('/save_frame'):
            content_len = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(content_len)
            
            query = self.path.split('?')[-1]
            frame_idx = 0
            for part in query.split('&'):
                if part.startswith('frame='):
                    frame_idx = int(part.split('=')[1])
            
            filename = f"frame_{frame_idx:04d}.jpg"
            filepath = os.path.join(FRAMES_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(data)

            if frame_idx % 60 == 0 or frame_idx == TOTAL_FRAMES - 1:
                print(f"[Render Progress] Saved frame {frame_idx:04d} / {TOTAL_FRAMES} ({(frame_idx/30.0):.1f}s)", flush=True)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')
        elif self.path == '/done':
            print("[Render Complete] Received completion signal from browser.", flush=True)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '4')
            self.end_headers()
            self.wfile.write(b'done')
            threading.Thread(target=self.server.shutdown).start()

def find_browser():
    candidates = [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def main():
    browser_exe = find_browser()
    if not browser_exe:
        print("Error: Neither Google Chrome nor Edge was found!")
        sys.exit(1)

    print(f"Using browser: {browser_exe}")

    server = http.server.HTTPServer(('127.0.0.1', PORT), VideoRenderHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    print(f"HTTP Server started at http://127.0.0.1:{PORT}/")

    cmd = [
        browser_exe,
        '--headless=new',
        '--disable-gpu',
        '--no-sandbox',
        '--disable-web-security',
        '--allow-file-access-from-files',
        '--window-size=1920,1080',
        f'http://127.0.0.1:{PORT}/render.html'
    ]
    print("Launching browser rendering session...")
    proc = subprocess.Popen(cmd)

    # Wait for completion
    server_thread.join(timeout=180)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except:
        pass

    frame_files = [f for f in os.listdir(FRAMES_DIR) if f.startswith('frame_') and f.endswith('.jpg')]
    print(f"Total rendered frames gathered: {len(frame_files)} / {TOTAL_FRAMES}")

    if len(frame_files) < TOTAL_FRAMES:
        print(f"Warning: Only {len(frame_files)} frames rendered.")

    # -------------------------------------------------------------
    # Audio Mixing with FFmpeg
    # -------------------------------------------------------------
    music_file = os.path.join(COMP_DIR, 'assets', 'music', 'happy-beats-business-moves-vol-12-by-ende-dot-app.mp3')
    sfx_files = [
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'impact', 'impactBell_heavy_000.ogg'), 0, 0.95),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'impact', 'impactSoft_medium_000.ogg'), 3500, 0.85),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'casino', 'card-slide-1.ogg'), 7000, 0.75),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'casino', 'card-place-1.ogg'), 8500, 0.75),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'interface', 'click_001.ogg'), 11200, 0.80),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'interface', 'glitch_002.ogg'), 15000, 0.75),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'impact', 'impactSoft_medium_002.ogg'), 18500, 0.90),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'casino', 'chips-stack-1.ogg'), 19500, 0.75),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'impact', 'impactBell_heavy_003.ogg'), 22000, 0.95),
        (os.path.join(COMP_DIR, 'assets', 'sfx', 'interface', 'switch_001.ogg'), 22800, 0.70)
    ]

    audio_cmd = ['ffmpeg', '-y', '-i', music_file]
    for sfx_path, _, _ in sfx_files:
        audio_cmd.extend(['-i', sfx_path])

    filter_parts = [
        "[0:a]volume=0.82,afade=t=out:st=23.4:d=1.6[music]"
    ]
    inputs_tags = ["[music]"]
    for i, (_, delay_ms, vol) in enumerate(sfx_files, start=1):
        tag = f"sfx{i}"
        filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume={vol}[{tag}]")
        inputs_tags.append(f"[{tag}]")

    num_inputs = len(inputs_tags)
    filter_parts.append(f"{''.join(inputs_tags)}amix=inputs={num_inputs}:duration=first:dropout_transition=2[aout]")

    mastered_audio = os.path.join(WORK_DIR, 'mastered_audio.aac')
    audio_cmd.extend([
        '-filter_complex', ';'.join(filter_parts),
        '-map', '[aout]',
        '-c:a', 'aac',
        '-b:a', '256k',
        '-t', '25.0',
        mastered_audio
    ])

    print("Mastering soundtrack and SFX mix...")
    subprocess.run(audio_cmd, check=True)
    print("Mastered audio created successfully.")

    # -------------------------------------------------------------
    # Poster Frame (Frame 680)
    # -------------------------------------------------------------
    poster_source = os.path.join(FRAMES_DIR, 'frame_0680.jpg')
    poster_target = os.path.join(OUTPUT_DIR, 'brag.jpg')
    if os.path.exists(poster_source):
        shutil.copyfile(poster_source, poster_target)
        print("Generated poster: brag-output/brag.jpg")
        # Bake as frame 0 so idle thumbnail is the poster
        frame_zero = os.path.join(FRAMES_DIR, 'frame_0000.jpg')
        shutil.copyfile(poster_source, frame_zero)
        print("Baking poster as frame 0...")

    # -------------------------------------------------------------
    # Final Video Assembly with FFmpeg
    # -------------------------------------------------------------
    video_target = os.path.join(OUTPUT_DIR, 'brag.mp4')
    input_pattern = os.path.join(FRAMES_DIR, 'frame_%04d.jpg')
    video_cmd = [
        'ffmpeg', '-y',
        '-framerate', '30',
        '-i', input_pattern,
        '-i', mastered_audio,
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '17',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'copy',
        '-t', '25.0',
        '-movflags', '+faststart',
        video_target
    ]

    print("Encoding final video: brag-output/brag.mp4...")
    subprocess.run(video_cmd, check=True)
    print("Video rendered successfully!")

    if os.path.exists(video_target):
        size_mb = os.path.getsize(video_target) / (1024 * 1024)
        print(f"SUCCESS: {video_target} exists ({size_mb:.2f} MB)")

if __name__ == '__main__':
    main()
