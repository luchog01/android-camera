from flask import Flask, render_template, Response
import subprocess
import threading
import time
import os
import signal
import sys
import numpy as np
from PIL import Image
import io
from concurrent.futures import ThreadPoolExecutor
import queue

app = Flask(__name__)


class HighSpeedCameraStreamer:
    def __init__(self):
        self.running = False
        self.target_width = 320  # Much smaller for speed
        self.target_height = 240
        self.jpeg_quality = 60  # Lower quality for speed
        self.frame_queue = queue.Queue(maxsize=5)  # Buffer frames
        self.capture_executor = ThreadPoolExecutor(max_workers=3)
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0
        self.last_frame = None
        self.frame_lock = threading.Lock()

        # Performance optimizations
        self.skip_frames = 0  # Skip frames if processing is slow
        self.max_skip = 2

    def start_camera(self):
        """Start the camera streaming system"""
        try:
            # Test if termux-api is available
            subprocess.run(["termux-camera-info"], check=True, capture_output=True)
            self.running = True

            # Start multiple capture threads for parallel processing
            for i in range(2):
                threading.Thread(target=self._capture_worker, daemon=True).start()

            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: termux-api not installed or camera not available")
            return False

    def _capture_worker(self):
        """Worker thread for continuous frame capture"""
        temp_files = [
            f"/data/data/com.termux/files/home/temp_photo_{i}.jpg" for i in range(3)
        ]
        file_index = 0

        while self.running:
            try:
                temp_file = temp_files[file_index]
                file_index = (file_index + 1) % len(temp_files)

                # Capture with minimal settings for speed
                start_time = time.time()
                result = subprocess.run(
                    [
                        "termux-camera-photo",
                        "-c",
                        "0",  # Back camera
                        "--silent",  # Reduce output
                        temp_file,
                    ],
                    capture_output=True,
                    timeout=5,
                    text=True,
                )

                if result.returncode == 0 and os.path.exists(temp_file):
                    capture_time = time.time() - start_time

                    # Process image in executor for non-blocking operation
                    if not self.frame_queue.full():
                        future = self.capture_executor.submit(
                            self._process_image, temp_file
                        )
                        try:
                            processed_frame = future.result(timeout=0.5)
                            if processed_frame:
                                try:
                                    self.frame_queue.put_nowait(processed_frame)
                                except queue.Full:
                                    pass  # Skip if queue is full
                        except Exception as e:
                            print(f"Processing error: {e}")

                # Minimal delay between captures
                time.sleep(0.01)

            except Exception as e:
                print(f"Capture error: {e}")
                time.sleep(0.1)

    def _process_image(self, image_path):
        """Fast image processing with aggressive optimization"""
        try:
            # Load and process image as quickly as possible
            with Image.open(image_path) as img:
                # Convert to RGB only if necessary
                if img.mode != "RGB":
                    img = img.convert("RGB")

                # Fast resize with nearest neighbor for speed
                img = img.resize(
                    (self.target_width, self.target_height), Image.Resampling.NEAREST
                )

                # Fast JPEG compression
                output_buffer = io.BytesIO()
                img.save(
                    output_buffer,
                    format="JPEG",
                    quality=self.jpeg_quality,
                    optimize=False,
                )  # Disable optimize for speed

                # Clean up temp file immediately
                try:
                    os.remove(image_path)
                except:
                    pass

                return output_buffer.getvalue()

        except Exception as e:
            print(f"Processing error: {e}")
            try:
                os.remove(image_path)
            except:
                pass
            return None

    def generate_frames(self):
        """High-speed frame generator with buffering"""
        frame_interval = 1.0 / 30  # Target 30 FPS
        last_frame_time = 0

        while self.running:
            current_time = time.time()

            # Try to get a fresh frame from queue
            frame_data = None
            try:
                # Non-blocking get with short timeout
                frame_data = self.frame_queue.get_nowait()
                self._update_fps_counter()
            except queue.Empty:
                # Use last frame if no new frame available
                with self.frame_lock:
                    frame_data = self.last_frame

            if frame_data:
                with self.frame_lock:
                    self.last_frame = frame_data

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(frame_data)).encode()
                    + b"\r\n\r\n"
                    + frame_data
                    + b"\r\n"
                )

            # Frame rate limiting
            elapsed = current_time - last_frame_time
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
            last_frame_time = time.time()

    def _update_fps_counter(self):
        """Update FPS counter"""
        self.fps_counter += 1
        current_time = time.time()

        if current_time - self.fps_start_time >= 1.0:
            self.current_fps = self.fps_counter / (current_time - self.fps_start_time)
            self.fps_counter = 0
            self.fps_start_time = current_time

    def stop(self):
        """Stop the camera streaming"""
        self.running = False
        self.capture_executor.shutdown(wait=False)


# Ultra-fast alternative using video capture (if available)
class VideoCameraStreamer:
    def __init__(self):
        self.running = False
        self.process = None
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0

    def start_camera(self):
        """Start video capture using ffmpeg if available"""
        try:
            # Try to start ffmpeg-based video capture
            self.process = subprocess.Popen(
                [
                    "ffmpeg",
                    "-f",
                    "v4l2",
                    "-video_size",
                    "320x240",
                    "-framerate",
                    "30",
                    "-i",
                    "/dev/video0",
                    "-c:v",
                    "mjpeg",
                    "-q:v",
                    "5",
                    "-f",
                    "mjpeg",
                    "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )

            self.running = True
            return True
        except FileNotFoundError:
            print("FFmpeg not available, falling back to photo capture")
            return False

    def generate_frames(self):
        """Generate frames from video stream"""
        if not self.process:
            return

        buffer = b""
        while self.running and self.process.poll() is None:
            try:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break

                buffer += chunk

                # Look for JPEG boundaries
                while True:
                    start = buffer.find(b"\xff\xd8")  # JPEG start
                    end = buffer.find(b"\xff\xd9", start + 2)  # JPEG end

                    if start != -1 and end != -1:
                        # Extract complete JPEG frame
                        frame = buffer[start : end + 2]
                        buffer = buffer[end + 2 :]

                        self._update_fps_counter()

                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: "
                            + str(len(frame)).encode()
                            + b"\r\n\r\n"
                            + frame
                            + b"\r\n"
                        )
                    else:
                        break

            except Exception as e:
                print(f"Video stream error: {e}")
                break

    def _update_fps_counter(self):
        """Update FPS counter"""
        self.fps_counter += 1
        current_time = time.time()

        if current_time - self.fps_start_time >= 1.0:
            self.current_fps = self.fps_counter / (current_time - self.fps_start_time)
            self.fps_counter = 0
            self.fps_start_time = current_time

    def stop(self):
        """Stop video capture"""
        self.running = False
        if self.process:
            self.process.terminate()


# Try video capture first, fallback to photo capture
video_camera = VideoCameraStreamer()
if video_camera.start_camera():
    print("✅ Using high-speed video capture mode")
    camera = video_camera
else:
    print("📸 Using optimized photo capture mode")
    camera = HighSpeedCameraStreamer()


@app.route("/")
def index():
    """Main page with optimized video stream"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>High-Speed Android Camera Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            text-align: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 10px;
            color: white;
        }
        .container {
            max-width: 95vw;
            margin: 0 auto;
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
            backdrop-filter: blur(4px);
            border: 1px solid rgba(255, 255, 255, 0.18);
        }
        h1 {
            color: white;
            margin-bottom: 15px;
            font-size: 24px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        #videoStream {
            width: 100%;
            max-width: 640px;
            height: auto;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }
        .performance-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
            gap: 10px;
            margin: 15px 0;
            padding: 10px;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            backdrop-filter: blur(2px);
        }
        .stat-item {
            text-align: center;
        }
        .stat-value {
            font-size: 20px;
            font-weight: bold;
            color: #00ff88;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
        }
        .stat-label {
            font-size: 11px;
            color: rgba(255,255,255,0.8);
            margin-top: 3px;
        }
        .controls {
            margin-top: 15px;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
        }
        button {
            background: linear-gradient(45deg, #00c9ff, #92fe9d);
            color: #333;
            border: none;
            padding: 8px 16px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }
        .status {
            margin-top: 10px;
            padding: 8px;
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            backdrop-filter: blur(2px);
            font-size: 12px;
            text-align: left;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 High-Speed Camera Stream</h1>
        
        <div class="performance-stats">
            <div class="stat-item">
                <div class="stat-value" id="fps">--</div>
                <div class="stat-label">FPS</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="resolution">--</div>
                <div class="stat-label">Resolution</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="quality">--</div>
                <div class="stat-label">Quality</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="status">--</div>
                <div class="stat-label">Status</div>
            </div>
        </div>
        
        <img id="videoStream" src="/video_feed" alt="High-Speed Camera Stream">
        
        <div class="controls">
            <button onclick="refreshStream()">🔄 Refresh</button>
            <button onclick="toggleFullscreen()">⛶ Fullscreen</button>
            <button onclick="stopStream()">⏹️ Stop</button>
        </div>
        
        <div class="status">
            <strong>⚡ Mode:</strong> High-Speed Optimized<br>
            <strong>🎯 Target:</strong> 30 FPS<br>
            <strong>📱 Device:</strong> Android via Termux<br>
            <strong>🌐 Access:</strong> http://your-phone-ip:5000
        </div>
    </div>

    <script>
        let refreshTimer;
        
        function refreshStream() {
            clearTimeout(refreshTimer);
            const img = document.getElementById('videoStream');
            img.src = '/video_feed?' + Date.now();
        }

        function toggleFullscreen() {
            const video = document.getElementById('videoStream');
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                video.requestFullscreen().catch(err => {
                    console.log('Fullscreen error:', err);
                });
            }
        }

        function stopStream() {
            fetch('/stop')
                .then(response => response.text())
                .then(data => {
                    alert(data);
                    updateStatus();
                });
        }

        function updateStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('fps').textContent = data.fps.toFixed(1);
                    document.getElementById('resolution').textContent = data.resolution;
                    document.getElementById('quality').textContent = data.quality + '%';
                    document.getElementById('status').textContent = data.running ? '🟢' : '🔴';
                })
                .catch(error => console.error('Status error:', error));
        }

        // Auto-refresh every 500ms for smooth streaming
        function autoRefresh() {
            refreshStream();
            refreshTimer = setTimeout(autoRefresh, 500);
        }

        // Update status every 1 second
        setInterval(updateStatus, 1000);
        updateStatus();
        
        // Start auto-refresh after page load
        setTimeout(autoRefresh, 1000);
        
        // Handle visibility changes to save resources
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                clearTimeout(refreshTimer);
            } else {
                autoRefresh();
            }
        });
    </script>
</body>
</html>
    """


@app.route("/video_feed")
def video_feed():
    """High-speed video streaming route"""
    if not camera.running:
        camera.start_camera()

    return Response(
        camera.generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.route("/status")
def status():
    """Get camera status and performance metrics"""
    if isinstance(camera, VideoCameraStreamer):
        resolution = "320x240"
        quality = 85
    else:
        resolution = f"{camera.target_width}x{camera.target_height}"
        quality = camera.jpeg_quality

    return {
        "running": camera.running,
        "fps": camera.current_fps,
        "resolution": resolution,
        "quality": quality,
        "mode": "video" if isinstance(camera, VideoCameraStreamer) else "photo",
    }


@app.route("/stop")
def stop_stream():
    """Stop the camera stream"""
    camera.stop()
    return "High-speed camera stream stopped"


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nStopping high-speed camera stream...")
    camera.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    print("🚀 Starting HIGH-SPEED Android Camera Streaming Server...")
    print("📱 Optimized for 30 FPS performance")
    print("🌐 Server available at: http://localhost:5000")

    # Get local IP
    try:
        import socket

        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"📍 Network access: http://{local_ip}:5000")
    except:
        print("💡 Find your IP with: ip addr show")

    print("⚡ Performance tips:")
    print("   - Lower resolution = higher FPS")
    print("   - Good lighting improves capture speed")
    print("   - Close other apps to free resources")
    print("-" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
