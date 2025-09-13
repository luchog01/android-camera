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

app = Flask(__name__)


class CameraStreamer:
    def __init__(self):
        self.process = None
        self.running = False
        self.target_width = 640  # Reduced from full HD
        self.target_height = 480  # Optimized for mobile
        self.jpeg_quality = 75   # Balance between quality and size
        self.frame_cache = None
        self.cache_lock = threading.Lock()
        self.fps_counter = 0
        self.fps_start_time = time.time()
        self.current_fps = 0

    def start_camera(self):
        """Start the camera using termux-camera-photo in a loop"""
        try:
            # Test if termux-api is available
            subprocess.run(["termux-camera-info"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: termux-api not installed or camera not available")
            return False

        self.running = True
        return True

    def capture_frame(self):
        """Capture and optimize a single frame from camera"""
        try:
            # Capture photo to temporary file
            temp_file = "/data/data/com.termux/files/home/temp_photo.jpg"
            result = subprocess.run(
                [
                    "termux-camera-photo",
                    "-c",
                    "0",  # Back camera (0 = back, 1 = front)
                    temp_file,
                ],
                capture_output=True,
                timeout=3,  # Reduced timeout for faster response
            )

            if result.returncode == 0 and os.path.exists(temp_file):
                # Process and optimize the image
                optimized_frame = self._optimize_image(temp_file)
                # Clean up temp file
                os.remove(temp_file)
                return optimized_frame
            return None
        except Exception as e:
            print(f"Error capturing frame: {e}")
            return None
    
    def _optimize_image(self, image_path):
        """Optimize image using numpy and PIL for better performance"""
        try:
            # Load image with PIL
            with Image.open(image_path) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize using numpy for speed
                img_array = np.array(img)
                
                # Calculate new dimensions maintaining aspect ratio
                original_height, original_width = img_array.shape[:2]
                aspect_ratio = original_width / original_height
                
                if aspect_ratio > (self.target_width / self.target_height):
                    new_width = self.target_width
                    new_height = int(self.target_width / aspect_ratio)
                else:
                    new_height = self.target_height
                    new_width = int(self.target_height * aspect_ratio)
                
                # Resize using PIL (faster than numpy for resizing)
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert back to bytes with optimized JPEG compression
                output_buffer = io.BytesIO()
                resized_img.save(output_buffer, 
                               format='JPEG', 
                               quality=self.jpeg_quality,
                               optimize=True)
                
                return output_buffer.getvalue()
                
        except Exception as e:
            print(f"Error optimizing image: {e}")
            return None

    def generate_frames(self):
        """Generator function to yield frames for streaming with caching"""
        while self.running:
            frame_start_time = time.time()
            frame_data = self.capture_frame()
            
            if frame_data:
                # Cache the frame for potential reuse
                with self.cache_lock:
                    self.frame_cache = frame_data
                
                # Update FPS counter
                self._update_fps_counter()
                
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n"
                )
            else:
                # Use cached frame if capture fails
                with self.cache_lock:
                    if self.frame_cache:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + self.frame_cache + b"\r\n"
                        )
            
            # Dynamic sleep to maintain consistent FPS
            frame_time = time.time() - frame_start_time
            target_frame_time = 0.2  # 5 FPS
            sleep_time = max(0, target_frame_time - frame_time)
            time.sleep(sleep_time)
    
    def _update_fps_counter(self):
        """Update FPS counter for performance monitoring"""
        self.fps_counter += 1
        current_time = time.time()
        
        if current_time - self.fps_start_time >= 1.0:  # Update every second
            self.current_fps = self.fps_counter / (current_time - self.fps_start_time)
            self.fps_counter = 0
            self.fps_start_time = current_time

    def stop(self):
        """Stop the camera streaming"""
        self.running = False


# Global camera streamer instance
camera = CameraStreamer()


@app.route("/")
def index():
    """Main page with video stream"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Android Camera Stream</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            text-align: center;
            background-color: #f0f0f0;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
        }
        #videoStream {
            max-width: 100%;
            height: auto;
            border: 3px solid #333;
            border-radius: 10px;
        }
        .controls {
            margin-top: 20px;
        }
        button {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            margin: 5px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #0056b3;
        }
        .status {
            margin-top: 10px;
            padding: 10px;
            border-radius: 5px;
        }
        .error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .info {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .performance-stats {
            display: flex;
            justify-content: space-around;
            margin: 15px 0;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }
        .stat-item {
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }
        .stat-label {
            font-size: 12px;
            color: #6c757d;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📱 Android Camera Stream (Optimized)</h1>
        
        <!-- Performance Statistics -->
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
        
        <img id="videoStream" src="/video_feed" alt="Camera Stream">
        <div class="controls">
            <button onclick="refreshStream()">🔄 Refresh Stream</button>
            <button onclick="toggleFullscreen()">🖼️ Toggle Fullscreen</button>
            <button onclick="stopStream()">⏹️ Stop Stream</button>
        </div>
        <div class="status info">
            <strong>📡 Status:</strong> Streaming from Android back camera<br>
            <strong>🌐 URL:</strong> http://your-phone-ip:5000<br>
            <strong>⚡ Controls:</strong> Use buttons above to refresh or go fullscreen
        </div>
    </div>

    <script>
        function refreshStream() {
            document.getElementById('videoStream').src = '/video_feed?' + new Date().getTime();
        }

        function toggleFullscreen() {
            const video = document.getElementById('videoStream');
            if (video.requestFullscreen) {
                video.requestFullscreen();
            } else if (video.webkitRequestFullscreen) {
                video.webkitRequestFullscreen();
            } else if (video.mozRequestFullScreen) {
                video.mozRequestFullScreen();
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
                    document.getElementById('fps').textContent = data.fps;
                    document.getElementById('resolution').textContent = data.resolution;
                    document.getElementById('quality').textContent = data.quality + '%';
                    document.getElementById('status').textContent = data.running ? '🟢 ON' : '🔴 OFF';
                })
                .catch(error => {
                    console.error('Error fetching status:', error);
                });
        }

        // Update status every 2 seconds
        setInterval(updateStatus, 2000);
        
        // Initial status update
        updateStatus();
            setTimeout(refreshStream, 2000);
        };
    </script>
</body>
</html>
    """


@app.route("/video_feed")
def video_feed():
    """Video streaming route"""
    if not camera.running:
        camera.start_camera()
    
    return Response(
        camera.generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status")
def status():
    """Get camera status and performance metrics"""
    return {
        "running": camera.running,
        "fps": round(camera.current_fps, 2),
        "resolution": f"{camera.target_width}x{camera.target_height}",
        "quality": camera.jpeg_quality,
        "cached_frame": camera.frame_cache is not None
    }


@app.route("/stop")
def stop_stream():
    """Stop the camera stream"""
    camera.stop()
    return "Camera stream stopped"


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nStopping camera stream...")
    camera.stop()
    sys.exit(0)


if __name__ == "__main__":
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    print("🚀 Starting Android Camera Streaming Server...")
    print("📱 Make sure termux-api is installed and camera permissions are granted")
    print("🌐 Server will be available at: http://localhost:5000")
    print("🔗 To access from other devices, use your phone's IP address")
    print("⚠️  Press Ctrl+C to stop the server")

    # Get local IP address
    try:
        import socket

        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"📍 Your phone's IP: http://{local_ip}:5000")
    except:
        print("💡 Find your IP with: ip addr show")

    print("-" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)
