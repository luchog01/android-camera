import cv2
import threading
import time
from flask import Flask, Response, render_template_string
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PCCameraStreamer:
    def __init__(self, camera_index=0, fps=30, resolution=(640, 480), port=3000):
        self.camera_index = camera_index
        self.fps = fps
        self.resolution = resolution
        self.port = port
        self.cap = None
        self.frame = None
        self.is_streaming = False
        self.lock = threading.Lock()
        
        # Performance tracking
        self.frame_count = 0
        self.start_time = time.time()
        self.actual_fps = 0
        
    def initialize_camera(self):
        """Initialize the camera with optimal settings"""
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera {self.camera_index}")
                return False
            
            # Set camera properties for optimal performance
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            
            # Optimize buffer size to reduce latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Set MJPEG codec for better performance
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            
            # Verify settings
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            logger.info(f"Camera initialized: {actual_width}x{actual_height} @ {actual_fps} FPS")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing camera: {e}")
            return False
    
    def capture_frames(self):
        """Continuously capture frames from camera"""
        frame_time = 1.0 / self.fps
        
        while self.is_streaming:
            start_capture = time.time()
            
            ret, frame = self.cap.read()
            if ret:
                # Resize frame if needed (for consistency)
                if frame.shape[:2][::-1] != self.resolution:
                    frame = cv2.resize(frame, self.resolution, interpolation=cv2.INTER_LINEAR)
                
                # Update frame with thread safety
                with self.lock:
                    self.frame = frame.copy()
                    self.frame_count += 1
                
                # Calculate actual FPS
                if self.frame_count % 30 == 0:
                    elapsed = time.time() - self.start_time
                    self.actual_fps = self.frame_count / elapsed if elapsed > 0 else 0
            
            # Maintain target FPS
            capture_time = time.time() - start_capture
            sleep_time = max(0, frame_time - capture_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def get_frame(self):
        """Get the latest frame as JPEG bytes"""
        with self.lock:
            if self.frame is not None:
                # Encode frame as JPEG with optimized quality
                ret, buffer = cv2.imencode('.jpg', self.frame, 
                                         [cv2.IMWRITE_JPEG_QUALITY, 80,
                                          cv2.IMWRITE_JPEG_OPTIMIZE, 1])
                if ret:
                    return buffer.tobytes()
        return None
    
    def generate_frames(self):
        """Generator function for Flask streaming"""
        while self.is_streaming:
            frame_bytes = self.get_frame()
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.01)  # Small delay to prevent excessive CPU usage
    
    def start_streaming(self):
        """Start the camera streaming"""
        if not self.initialize_camera():
            return False
        
        self.is_streaming = True
        self.start_time = time.time()
        
        # Start capture thread
        capture_thread = threading.Thread(target=self.capture_frames, daemon=True)
        capture_thread.start()
        
        logger.info("Camera streaming started")
        return True
    
    def stop_streaming(self):
        """Stop the camera streaming"""
        self.is_streaming = False
        if self.cap:
            self.cap.release()
        logger.info("Camera streaming stopped")
    
    def get_stats(self):
        """Get streaming statistics"""
        return {
            'fps': round(self.actual_fps, 2),
            'resolution': f"{self.resolution[0]}x{self.resolution[1]}",
            'frames_captured': self.frame_count,
            'uptime': round(time.time() - self.start_time, 2)
        }

# Flask application
app = Flask(__name__)
streamer = PCCameraStreamer(fps=30, resolution=(640, 480), port=3000)

# HTML template for the web interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>PC Camera Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: white;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            text-align: center;
        }
        h1 {
            margin-bottom: 30px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .video-container {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            margin: 20px 0;
            backdrop-filter: blur(10px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        #videoStream {
            max-width: 100%;
            height: auto;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .stat-card {
            background: rgba(255,255,255,0.15);
            padding: 15px;
            border-radius: 10px;
            backdrop-filter: blur(5px);
        }
        .stat-value {
            font-size: 1.5em;
            font-weight: bold;
            color: #fff;
        }
        .stat-label {
            font-size: 0.9em;
            opacity: 0.8;
            margin-top: 5px;
        }
        .controls {
            margin: 20px 0;
        }
        button {
            background: rgba(255,255,255,0.2);
            border: 2px solid rgba(255,255,255,0.3);
            color: white;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 16px;
            margin: 0 10px;
            transition: all 0.3s ease;
        }
        button:hover {
            background: rgba(255,255,255,0.3);
            transform: translateY(-2px);
        }
        .status {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            margin: 10px;
        }
        .status.online {
            background: #4CAF50;
        }
        .status.offline {
            background: #f44336;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎥 PC Camera Stream</h1>
        
        <div class="status online" id="status">● STREAMING</div>
        
        <div class="video-container">
            <img id="videoStream" src="{{ url_for('video_feed') }}" alt="Camera Stream">
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="fps">--</div>
                <div class="stat-label">FPS</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="resolution">--</div>
                <div class="stat-label">Resolution</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="frames">--</div>
                <div class="stat-label">Frames Captured</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="uptime">--</div>
                <div class="stat-label">Uptime (s)</div>
            </div>
        </div>
        
        <div class="controls">
            <button onclick="refreshStream()">🔄 Refresh</button>
            <button onclick="toggleFullscreen()">⛶ Fullscreen</button>
        </div>
    </div>

    <script>
        function updateStats() {
            fetch('/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('fps').textContent = data.fps;
                    document.getElementById('resolution').textContent = data.resolution;
                    document.getElementById('frames').textContent = data.frames_captured;
                    document.getElementById('uptime').textContent = data.uptime;
                })
                .catch(error => {
                    console.error('Error fetching stats:', error);
                    document.getElementById('status').textContent = '● OFFLINE';
                    document.getElementById('status').className = 'status offline';
                });
        }
        
        function refreshStream() {
            const img = document.getElementById('videoStream');
            const src = img.src;
            img.src = '';
            setTimeout(() => { img.src = src; }, 100);
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
        
        // Update stats every 2 seconds
        setInterval(updateStats, 2000);
        updateStats(); // Initial call
        
        // Handle image load errors
        document.getElementById('videoStream').onerror = function() {
            document.getElementById('status').textContent = '● OFFLINE';
            document.getElementById('status').className = 'status offline';
        };
        
        document.getElementById('videoStream').onload = function() {
            document.getElementById('status').textContent = '● STREAMING';
            document.getElementById('status').className = 'status online';
        };
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Main page with video stream"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(streamer.generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stats')
def stats():
    """API endpoint for streaming statistics"""
    return streamer.get_stats()

@app.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'ok', 'streaming': streamer.is_streaming}

def main():
    """Main function to start the camera streaming server"""
    try:
        logger.info("Starting PC Camera Streaming Server...")
        
        if not streamer.start_streaming():
            logger.error("Failed to start camera streaming")
            return
        
        logger.info("Server starting on http://localhost:3000")
        logger.info("Press Ctrl+C to stop the server")
        
        # Start Flask server
        app.run(host='0.0.0.0', port=3000, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        streamer.stop_streaming()
        logger.info("Server stopped")

if __name__ == '__main__':
    main()
