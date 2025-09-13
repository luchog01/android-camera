#!/usr/bin/env python3
"""
Lightweight Android Camera Streaming Server using Flask (Pure Python)
Designed to run on Termux for Android devices with minimal dependencies
"""

import logging
from flask import Flask, Response, jsonify
import threading
import time
import subprocess
from typing import Generator
import os
import math
import struct

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class LightweightCameraStreamer:
    def __init__(self):
        self.is_streaming = False
        self.lock = threading.Lock()
        self.fps = 10  # Lower FPS for better performance
        self.frame_count = 0
        self.last_time = time.time()
        self.temp_file = "/tmp/camera_frame.jpg"
        
    def initialize_camera(self) -> bool:
        """Initialize camera - primarily uses Termux"""
        try:
            if self.is_termux_available():
                logger.info("Termux detected, using termux-camera-photo")
                return True
            else:
                logger.info("Termux not available, using test mode")
                return True  # Always return True, fallback to test frames
                
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            return True  # Still allow test mode
    
    def is_termux_available(self) -> bool:
        """Check if Termux API is available"""
        try:
            # First check if termux-camera-photo command exists
            result = subprocess.run(['termux-camera-photo', '--help'], 
                                  capture_output=True, text=True, timeout=5)
            logger.info(f"Termux camera check result: {result.returncode}")
            if result.stderr:
                logger.info(f"Termux camera stderr: {result.stderr}")
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.info(f"Termux camera not available: {e}")
            return False
    
    def capture_termux_frame(self) -> bytes:
        """Capture frame using Termux camera API"""
        try:
            # Use termux-camera-photo to capture image
            logger.info("Attempting to capture frame with termux-camera-photo")
            result = subprocess.run([
                'termux-camera-photo', 
                '-c', '0',  # Use back camera (try camera 0)
                self.temp_file
            ], capture_output=True, timeout=10, text=True)
            
            logger.info(f"Camera capture result: return code {result.returncode}")
            if result.stdout:
                logger.info(f"Camera stdout: {result.stdout}")
            if result.stderr:
                logger.info(f"Camera stderr: {result.stderr}")
            
            if result.returncode == 0 and os.path.exists(self.temp_file):
                logger.info(f"Camera file captured successfully: {self.temp_file}")
                with open(self.temp_file, 'rb') as f:
                    frame_data = f.read()
                logger.info(f"Frame data size: {len(frame_data)} bytes")
                # Clean up temp file
                try:
                    os.remove(self.temp_file)
                except (OSError, FileNotFoundError):
                    pass
                return frame_data
            else:
                logger.error(f"Termux camera failed - return code: {result.returncode}")
                logger.error(f"File exists: {os.path.exists(self.temp_file)}")
                # Try alternative camera IDs
                for camera_id in ['1', '2']:
                    logger.info(f"Trying camera ID {camera_id}")
                    alt_result = subprocess.run([
                        'termux-camera-photo', 
                        '-c', camera_id,
                        self.temp_file
                    ], capture_output=True, timeout=10, text=True)
                    
                    if alt_result.returncode == 0 and os.path.exists(self.temp_file):
                        logger.info(f"Success with camera ID {camera_id}")
                        with open(self.temp_file, 'rb') as f:
                            frame_data = f.read()
                        try:
                            os.remove(self.temp_file)
                        except (OSError, FileNotFoundError):
                            pass
                        return frame_data
                
                return None
        except Exception as e:
            logger.error(f"Termux capture failed: {e}")
            return None
    
    def get_frame(self) -> bytes:
        """Get current frame as JPEG bytes"""
        with self.lock:
            if self.is_termux_available():
                frame_data = self.capture_termux_frame()
                if frame_data:
                    return frame_data
            
            # Fallback to test frame
            return self.generate_test_frame()
    
    def generate_test_frame(self) -> bytes:
        """Generate a test frame using pure Python BMP"""
        try:
            # Create a simple test pattern
            width, height = 320, 240  # Smaller for better performance
            
            # Create BMP image data
            return self.create_bmp_image(width, height)
            
        except Exception as e:
            logger.error(f"Test frame generation failed: {e}")
            # Return minimal fallback frame
            return self.create_minimal_frame()
    
    def create_bmp_image(self, width: int, height: int) -> bytes:
        """Create a BMP image using pure Python"""
        try:
            # Calculate row padding (BMP rows must be multiple of 4 bytes)
            row_size = ((width * 3 + 3) // 4) * 4
            pixel_data_size = row_size * height
            file_size = 54 + pixel_data_size
            
            # BMP header
            bmp_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
            
            # DIB header
            dib_header = struct.pack('<IIIHHIIIIII', 
                40,  # DIB header size
                width, height,  # Image dimensions
                1,  # Color planes
                24,  # Bits per pixel
                0,  # Compression
                pixel_data_size,  # Image size
                2835, 2835,  # Pixels per meter
                0, 0  # Colors used/important
            )
            
            # Create animated pattern
            t = time.time()
            center_x = int((math.sin(t * 0.5) + 1) * width / 2)
            center_y = int((math.cos(t * 0.5) + 1) * height / 2)
            
            # Generate pixel data (BGR format for BMP)
            pixels = bytearray()
            for y in range(height - 1, -1, -1):  # BMP is bottom-up
                row_data = bytearray()
                for x in range(width):
                    # Calculate distance from center for circle effect
                    dx = x - center_x
                    dy = y - center_y
                    distance = math.sqrt(dx*dx + dy*dy)
                    
                    # Create smooth animated pattern
                    if distance < 25:  # Moving circle
                        # Bright green circle
                        row_data.extend([0, 255, 0])  # BGR: Green
                    elif distance < 35:  # Circle border
                        # Yellow border
                        row_data.extend([0, 255, 255])  # BGR: Yellow
                    else:
                        # Create gradient background with animated waves
                        wave1 = int(50 + 30 * math.sin((x + t * 20) * 0.1))
                        wave2 = int(50 + 30 * math.cos((y + t * 15) * 0.1))
                        
                        # Blue gradient background
                        blue = min(255, max(0, 100 + wave1))
                        green = min(255, max(0, 50 + wave2))
                        red = min(255, max(0, 30 + int(10 * math.sin(t))))
                        
                        row_data.extend([blue, green, red])  # BGR
                
                # Add padding to make row size multiple of 4
                padding = row_size - (width * 3)
                row_data.extend([0] * padding)
                pixels.extend(row_data)
            
            self.frame_count += 1
            return bmp_header + dib_header + pixels
            
        except Exception as e:
            logger.error(f"BMP creation failed: {e}")
            return self.create_minimal_frame()
    
    def create_minimal_frame(self) -> bytes:
        """Create minimal fallback frame"""
        try:
            # Minimal 100x100 red BMP
            width, height = 100, 100
            file_size = 54 + (width * height * 3)
            
            bmp_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
            dib_header = struct.pack('<IIIHHIIIIII', 40, width, height, 1, 24, 0, 
                                   width * height * 3, 2835, 2835, 0, 0)
            
            # Red pixels (BGR format)
            pixels = bytearray([0, 0, 255] * width * height)  # Red in BGR
            
            return bmp_header + dib_header + pixels
        except Exception:
            return b''
    
    def start_streaming(self):
        """Start the video streaming"""
        if not self.initialize_camera():
            logger.error("Failed to initialize camera")
            return False
        
        self.is_streaming = True
        logger.info("Lightweight camera streaming started")
        return True
    
    def stop_streaming(self):
        """Stop the video streaming"""
        self.is_streaming = False
        logger.info("Camera streaming stopped")

# Global camera streamer instance
camera_streamer = LightweightCameraStreamer()

def generate_frames() -> Generator[bytes, None, None]:
    """Generator function for video frames"""
    while camera_streamer.is_streaming:
        try:
            frame_data = camera_streamer.get_frame()
            if frame_data:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            else:
                # If no frame available, wait a bit
                time.sleep(0.2)
        except Exception as e:
            logger.error(f"Frame generation error: {e}")
            time.sleep(0.2)

@app.route("/")
def index():
    """Serve the main page with video stream"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lightweight Camera Stream</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
                color: white;
                text-align: center;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 30px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            h1 {
                margin-bottom: 30px;
                font-size: 2.2em;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
            }
            .video-container {
                position: relative;
                display: inline-block;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
                margin: 20px 0;
            }
            img {
                max-width: 100%;
                height: auto;
                display: block;
            }
            .controls {
                margin-top: 20px;
            }
            .btn {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.3);
                color: white;
                padding: 10px 20px;
                margin: 5px;
                border-radius: 20px;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.3s ease;
            }
            .btn:hover {
                background: rgba(255, 255, 255, 0.3);
                transform: translateY(-2px);
            }
            .status {
                margin-top: 20px;
                padding: 15px;
                background: rgba(0, 0, 0, 0.2);
                border-radius: 10px;
                font-family: monospace;
                font-size: 14px;
            }
            .info {
                margin-top: 15px;
                font-size: 12px;
                opacity: 0.8;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 15px;
                }
                h1 {
                    font-size: 1.8em;
                }
                .btn {
                    display: block;
                    margin: 8px auto;
                    width: 180px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 Lightweight Camera Stream</h1>
            <div class="video-container">
                <img id="videoStream" src="/video_feed" alt="Camera Stream">
            </div>
            <div class="controls">
                <button class="btn" onclick="refreshStream()">🔄 Refresh</button>
                <button class="btn" onclick="toggleFullscreen()">🖥️ Fullscreen</button>
                <button class="btn" onclick="checkStatus()">📊 Status</button>
            </div>
            <div class="status" id="status">
                Status: Streaming active (Lightweight Mode)
            </div>
            <div class="info">
                Optimized for smartphones • Uses minimal resources
            </div>
        </div>

        <script>
            function refreshStream() {
                const img = document.getElementById('videoStream');
                img.src = '/video_feed?' + new Date().getTime();
                updateStatus('Stream refreshed');
            }

            function toggleFullscreen() {
                const img = document.getElementById('videoStream');
                if (img.requestFullscreen) {
                    img.requestFullscreen();
                } else if (img.webkitRequestFullscreen) {
                    img.webkitRequestFullscreen();
                } else if (img.msRequestFullscreen) {
                    img.msRequestFullscreen();
                }
            }

            async function checkStatus() {
                try {
                    const response = await fetch('/status');
                    const data = await response.json();
                    updateStatus(`Status: ${data.status} | FPS: ${data.fps} | Mode: ${data.camera_type}`);
                } catch (error) {
                    updateStatus('Status: Error fetching status');
                }
            }

            function updateStatus(message) {
                document.getElementById('status').textContent = message;
            }

            // Auto-refresh status every 10 seconds
            setInterval(checkStatus, 10000);

            // Handle image load errors
            document.getElementById('videoStream').onerror = function() {
                updateStatus('Status: Stream connection lost');
            };
        </script>
    </body>
    </html>
    """
    return html_content

@app.route("/video_feed")
def video_feed():
    """Video streaming endpoint"""
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/status")
def get_status():
    """Get streaming status"""
    return jsonify({
        "status": "active" if camera_streamer.is_streaming else "inactive",
        "fps": camera_streamer.fps,
        "uptime": int(time.time() - camera_streamer.last_time),
        "termux_available": camera_streamer.is_termux_available(),
        "camera_type": "termux" if camera_streamer.is_termux_available() else "test_mode"
    })

@app.route("/restart", methods=["POST"])
def restart_stream():
    """Restart the camera stream"""
    camera_streamer.stop_streaming()
    time.sleep(1)
    success = camera_streamer.start_streaming()
    return jsonify({"success": success, "message": "Stream restarted" if success else "Failed to restart stream"})

if __name__ == "__main__":
    # Initialize camera on startup
    logger.info("Starting Lightweight Android Camera Stream Server on port 5000...")
    logger.info("Access the stream at: http://localhost:5000")
    logger.info("Or from your PC at: http://[PHONE_IP]:5000")
    
    camera_streamer.start_streaming()
    
    try:
        app.run(
            host="0.0.0.0",  # Allow connections from any IP
            port=5000,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down camera stream...")
        camera_streamer.stop_streaming()
