#!/usr/bin/env python3
"""
Lightweight Android Camera Streaming Server using FastAPI and Pillow
Designed to run on Termux for Android devices with minimal dependencies
"""

import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn
import threading
import time
import subprocess
from typing import Generator
from PIL import Image, ImageDraw
import io
import os
import math

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Android Camera Stream", description="Lightweight video streaming from Android camera via Termux")

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
            result = subprocess.run(['which', 'termux-camera-photo'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
    
    def capture_termux_frame(self) -> bytes:
        """Capture frame using Termux camera API"""
        try:
            # Use termux-camera-photo to capture image
            result = subprocess.run([
                'termux-camera-photo', 
                '-c', '0',  # Use back camera
                self.temp_file
            ], capture_output=True, timeout=3)
            
            if result.returncode == 0 and os.path.exists(self.temp_file):
                with open(self.temp_file, 'rb') as f:
                    frame_data = f.read()
                # Clean up temp file
                try:
                    os.remove(self.temp_file)
                except (OSError, FileNotFoundError):
                    pass
                return frame_data
            else:
                logger.error(f"Termux camera error: {result.stderr}")
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
        """Generate a test frame using Pillow"""
        try:
            # Create a simple test pattern
            width, height = 640, 480
            image = Image.new('RGB', (width, height), color='navy')
            draw = ImageDraw.Draw(image)
            
            # Add some moving elements
            t = time.time()
            x = int((math.sin(t) + 1) * width / 2)
            y = int((math.cos(t) + 1) * height / 2)
            
            # Draw moving circle
            circle_radius = 30
            draw.ellipse([x-circle_radius, y-circle_radius, x+circle_radius, y+circle_radius], 
                        fill='lime', outline='white', width=2)
            
            # Draw timestamp
            timestamp = time.strftime('%H:%M:%S')
            draw.text((10, 10), f"Test Frame - {timestamp}", fill='white')
            draw.text((10, 40), f"Frame: {self.frame_count}", fill='white')
            
            # Draw grid pattern
            for i in range(0, width, 50):
                draw.line([(i, 0), (i, height)], fill='gray', width=1)
            for i in range(0, height, 50):
                draw.line([(0, i), (width, i)], fill='gray', width=1)
            
            # Convert to JPEG bytes
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=70, optimize=True)
            self.frame_count += 1
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Test frame generation failed: {e}")
            # Return minimal fallback frame
            return self.create_minimal_frame()
    
    def create_minimal_frame(self) -> bytes:
        """Create minimal fallback frame"""
        try:
            image = Image.new('RGB', (320, 240), color='red')
            draw = ImageDraw.Draw(image)
            draw.text((10, 10), "Camera Error", fill='white')
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=50)
            return buffer.getvalue()
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

@app.on_event("startup")
async def startup_event():
    """Initialize camera on startup"""
    logger.info("Starting Lightweight Android Camera Stream Server...")
    camera_streamer.start_streaming()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down camera stream...")
    camera_streamer.stop_streaming()

@app.get("/", response_class=HTMLResponse)
async def index():
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
    return HTMLResponse(content=html_content)

@app.get("/video_feed")
async def video_feed():
    """Video streaming endpoint"""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/status")
async def get_status():
    """Get streaming status"""
    return {
        "status": "active" if camera_streamer.is_streaming else "inactive",
        "fps": camera_streamer.fps,
        "uptime": int(time.time() - camera_streamer.last_time),
        "termux_available": camera_streamer.is_termux_available(),
        "camera_type": "termux" if camera_streamer.is_termux_available() else "test_mode"
    }

@app.post("/restart")
async def restart_stream():
    """Restart the camera stream"""
    camera_streamer.stop_streaming()
    await asyncio.sleep(1)
    success = camera_streamer.start_streaming()
    return {"success": success, "message": "Stream restarted" if success else "Failed to restart stream"}

if __name__ == "__main__":
    # Run the server
    logger.info("Starting Lightweight Android Camera Stream Server on port 5000...")
    logger.info("Access the stream at: http://localhost:5000")
    logger.info("Or from your PC at: http://[PHONE_IP]:5000")
    
    uvicorn.run(
        app,
        host="0.0.0.0",  # Allow connections from any IP
        port=5000,
        log_level="info",
        access_log=False  # Reduce logging overhead
    )
