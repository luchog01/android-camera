from flask import Flask, render_template, Response
import subprocess
import threading
import time
import os
import signal
import sys

app = Flask(__name__)


class CameraStreamer:
    def __init__(self):
        self.process = None
        self.running = False

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
        """Capture a single frame from camera"""
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
                timeout=5,
            )

            if result.returncode == 0 and os.path.exists(temp_file):
                with open(temp_file, "rb") as f:
                    frame_data = f.read()
                # Clean up temp file
                os.remove(temp_file)
                return frame_data
            return None
        except Exception as e:
            print(f"Error capturing frame: {e}")
            return None

    def generate_frames(self):
        """Generator function to yield frames for streaming"""
        while self.running:
            frame_data = self.capture_frame()
            if frame_data:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n"
                )
            time.sleep(0.5)  # Adjust delay as needed (0.5s = ~2 FPS)

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
    </style>
</head>
<body>
    <div class="container">
        <h1>📱 Android Camera Stream</h1>
        <img id="videoStream" src="/video_feed" alt="Camera Stream">
        <div class="controls">
            <button onclick="refreshStream()">🔄 Refresh Stream</button>
            <button onclick="toggleFullscreen()">🖼️ Toggle Fullscreen</button>
        </div>
        <div class="status info">
            <strong>📡 Status:</strong> Streaming from Android back camera<br>
            <strong>🌐 URL:</strong> http://your-phone-ip:5000<br>
            <strong>⚡ Controls:</strong> Use buttons above to refresh or go fullscreen
        </div>
    </div>

    <script>
        function refreshStream() {
            const img = document.getElementById('videoStream');
            const timestamp = new Date().getTime();
            img.src = '/video_feed?' + timestamp;
        }
        
        function toggleFullscreen() {
            const img = document.getElementById('videoStream');
            if (img.requestFullscreen) {
                img.requestFullscreen();
            } else if (img.webkitRequestFullscreen) {
                img.webkitRequestFullscreen();
            } else if (img.mozRequestFullScreen) {
                img.mozRequestFullScreen();
            }
        }
        
        // Auto-refresh every 30 seconds to prevent timeouts
        setInterval(refreshStream, 30000);
        
        // Handle connection errors
        document.getElementById('videoStream').onerror = function() {
            console.log('Stream error - attempting refresh...');
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
        if not camera.start_camera():
            return "Camera not available", 500

    return Response(
        camera.generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


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
