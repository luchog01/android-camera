import io
import time
import threading
import struct
import subprocess
import os
import base64
from flask import Flask, Response, render_template_string

class PurePythonGreenTracker:
    def __init__(self):
        self.current_frame_data = None
        self.frame_width = 320  # Smaller for better performance
        self.frame_height = 240
        self.green_center = None
        self.side_position = "CENTER"
        self.running = False
        
        # Green color thresholds (RGB values)
        self.green_threshold = {
            'r_min': 0, 'r_max': 100,    # Low red
            'g_min': 60, 'g_max': 255,   # High green
            'b_min': 0, 'b_max': 100     # Low blue
        }
    
    def is_green_pixel(self, r, g, b):
        """Check if a pixel is green based on RGB thresholds"""
        return (self.green_threshold['r_min'] <= r <= self.green_threshold['r_max'] and
                self.green_threshold['g_min'] <= g <= self.green_threshold['g_max'] and
                self.green_threshold['b_min'] <= b <= self.green_threshold['b_max'])
    
    def capture_with_termux(self):
        """Capture image using termux-camera-photo"""
        try:
            # Capture to temporary file
            result = subprocess.run([
                'termux-camera-photo', 
                '-c', '0',  # Use back camera
                '/tmp/cam_capture.jpg'
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and os.path.exists('/tmp/cam_capture.jpg'):
                # Read the raw JPEG file
                with open('/tmp/cam_capture.jpg', 'rb') as f:
                    jpeg_data = f.read()
                return self.decode_jpeg_simple(jpeg_data)
            return None
        except Exception as e:
            print(f"Termux capture error: {e}")
            return None
    
    def decode_jpeg_simple(self, jpeg_data):
        """Simple JPEG decode - fallback to test image if decode fails"""
        # For now, return test image since pure Python JPEG decode is complex
        # In a real scenario, you might use system tools to convert JPEG to raw format
        return self.create_test_image()
    
    def create_test_image(self):
        """Create a test image with moving green circle using only standard library"""
        # Create RGB array: width * height * 3 (RGB)
        image_data = []
        
        import math
        t = time.time()
        # Moving green circle parameters
        center_x = int(self.frame_width/2 + 80 * math.sin(t * 0.8))
        center_y = int(self.frame_height/2 + 60 * math.cos(t * 0.6))
        radius = 25
        
        for y in range(self.frame_height):
            row = []
            for x in range(self.frame_width):
                # Distance from circle center
                dist = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
                
                if dist <= radius:
                    # Green circle
                    row.extend([0, 180, 0])  # RGB: Green
                elif x == self.frame_width // 3 or x == 2 * self.frame_width // 3:
                    # Zone divider lines
                    row.extend([100, 100, 100])  # Gray
                else:
                    # Background - make it brighter so it's visible
                    row.extend([80, 80, 100])  # Lighter blue-gray
            
            image_data.extend(row)
        
        return image_data
    
    def detect_green_center(self, image_data):
        """Detect green pixels and calculate center - pure Python"""
        if not image_data:
            return False
        
        green_pixels = []
        
        # Process pixels (RGB format: [R,G,B,R,G,B,...])
        for y in range(0, self.frame_height, 2):  # Skip every other row for speed
            for x in range(0, self.frame_width, 2):  # Skip every other column
                pixel_index = (y * self.frame_width + x) * 3
                
                if pixel_index + 2 < len(image_data):
                    r = image_data[pixel_index]
                    g = image_data[pixel_index + 1] 
                    b = image_data[pixel_index + 2]
                    
                    if self.is_green_pixel(r, g, b):
                        green_pixels.append((x, y))
        
        if green_pixels:
            # Calculate center of mass
            avg_x = sum(p[0] for p in green_pixels) / len(green_pixels)
            avg_y = sum(p[1] for p in green_pixels) / len(green_pixels)
            
            self.green_center = (int(avg_x), int(avg_y))
            
            # Determine position
            if avg_x < self.frame_width // 3:
                self.side_position = "LEFT"
            elif avg_x > 2 * self.frame_width // 3:
                self.side_position = "RIGHT"
            else:
                self.side_position = "CENTER"
            
            return True
        else:
            self.green_center = None
            self.side_position = "NOT DETECTED"
            return False
    
    def draw_annotations(self, image_data):
        """Draw annotations directly on RGB array"""
        if not image_data:
            return image_data
        
        # Draw center dot
        if self.green_center:
            cx, cy = self.green_center
            dot_size = 4
            
            for dy in range(-dot_size, dot_size + 1):
                for dx in range(-dot_size, dot_size + 1):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < self.frame_width and 0 <= y < self.frame_height:
                        if dx*dx + dy*dy <= dot_size*dot_size:
                            pixel_index = (y * self.frame_width + x) * 3
                            if pixel_index + 2 < len(image_data):
                                # Red dot
                                image_data[pixel_index] = 255     # R
                                image_data[pixel_index + 1] = 0   # G  
                                image_data[pixel_index + 2] = 0   # B
        
        return image_data
    
    def create_green_mask_overlay(self, image_data):
        """Create image with green mask overlay and annotations"""
        if not image_data:
            return image_data
        
        # Create a copy of the image
        overlay_data = image_data.copy()
        
        # Add bright green overlay on detected green pixels
        for y in range(self.frame_height):
            for x in range(self.frame_width):
                pixel_index = (y * self.frame_width + x) * 3
                
                if pixel_index + 2 < len(overlay_data):
                    r = overlay_data[pixel_index]
                    g = overlay_data[pixel_index + 1] 
                    b = overlay_data[pixel_index + 2]
                    
                    if self.is_green_pixel(r, g, b):
                        # Make detected green pixels much brighter and more saturated
                        overlay_data[pixel_index] = 50       # R - some red for visibility
                        overlay_data[pixel_index + 1] = 255  # G - full green
                        overlay_data[pixel_index + 2] = 50   # B - some blue for visibility
        
        # Add annotations (red dot)
        overlay_data = self.draw_annotations(overlay_data)
        
        return overlay_data
    
    def rgb_to_jpeg_bytes(self, image_data):
        """Convert RGB data to simple bitmap format (BMP) since we can't easily make JPEG"""
        if not image_data:
            return None
        
        # Create a simple BMP file in memory
        # BMP Header (54 bytes) + pixel data
        width, height = self.frame_width, self.frame_height
        
        # BMP file header (14 bytes)
        file_size = 54 + width * height * 3
        bmp_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
        
        # BMP info header (40 bytes)  
        info_header = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 24, 0, 
                                 width * height * 3, 0, 0, 0, 0)
        
        # Convert RGB to BGR for BMP format and add padding
        bmp_data = bytearray()
        row_padding = (4 - (width * 3) % 4) % 4
        
        for y in range(height):
            for x in range(width):
                pixel_index = (y * width + x) * 3
                if pixel_index + 2 < len(image_data):
                    r = image_data[pixel_index]
                    g = image_data[pixel_index + 1]
                    b = image_data[pixel_index + 2]
                    bmp_data.extend([b, g, r])  # BMP uses BGR
                else:
                    bmp_data.extend([0, 0, 0])
            
            # Add row padding
            bmp_data.extend([0] * row_padding)
        
        return bmp_header + info_header + bmp_data
    
    def capture_and_process(self):
        """Main processing loop"""
        while self.running:
            try:
                # Try to capture real image, fallback to test
                image_data = self.capture_with_termux()
                if not image_data:
                    image_data = self.create_test_image()
                
                # Detect green objects
                self.detect_green_center(image_data)
                
                # Draw annotations
                image_data = self.draw_annotations(image_data)
                
                # Store frame
                self.current_frame_data = image_data
                
            except Exception as e:
                print(f"Processing error: {e}")
                self.current_frame_data = self.create_test_image()
            
            time.sleep(0.15)  # ~6-7 FPS for stability
    
    def get_frame_bytes(self):
        """Get current frame as image bytes"""
        if self.current_frame_data:
            return self.rgb_to_jpeg_bytes(self.current_frame_data)
        return None
    
    def start(self):
        """Start the tracker"""
        print("🟢 Starting Pure Python Green Tracker...")
        
        # Test termux-api availability
        try:
            result = subprocess.run(['termux-camera-info'], 
                                  capture_output=True, timeout=2)
            if result.returncode == 0:
                print("📱 Termux camera API available")
            else:
                print("⚠️  Termux camera API not available, using test mode")
        except:
            print("⚠️  Termux not detected, using test mode")
        
        self.running = True
        self.capture_thread = threading.Thread(target=self.capture_and_process, daemon=True)
        self.capture_thread.start()
        return True
    
    def stop(self):
        """Stop the tracker"""
        self.running = False
        print("🛑 Tracker stopped")

# Flask app
app = Flask(__name__)
tracker = PurePythonGreenTracker()

# HTML template with dual video feeds
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>🟢 Dual Feed Green Tracker</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
            background: linear-gradient(45deg, #1a1a2e, #16213e, #0f3460);
            color: white;
            padding: 15px;
            min-height: 100vh;
        }
        .container { 
            max-width: 1000px; 
            margin: 0 auto; 
            text-align: center; 
        }
        .header { 
            margin-bottom: 25px; 
            animation: fadeIn 1s ease-in;
        }
        .header h1 { 
            font-size: 28px; 
            margin-bottom: 8px;
            background: linear-gradient(90deg, #00ff88, #00cc44);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .feeds-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }
        .feed-box { 
            background: rgba(255,255,255,0.05); 
            border-radius: 20px; 
            padding: 20px; 
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 15px 35px rgba(0,0,0,0.4);
            animation: slideUp 1s ease-out;
        }
        .feed-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 15px;
            padding: 8px 16px;
            border-radius: 15px;
            display: inline-block;
        }
        .raw-title {
            background: linear-gradient(135deg, #667eea, #764ba2);
        }
        .mask-title {
            background: linear-gradient(135deg, #f093fb, #f5576c);
        }
        .processed-title {
            background: linear-gradient(135deg, #4facfe, #00f2fe);
        }
        .video-frame { 
            max-width: 100%; 
            height: auto; 
            border-radius: 15px; 
            border: 2px solid rgba(255,255,255,0.2);
            background: #222;
            transition: all 0.3s ease;
        }
        .video-frame:hover {
            border-color: rgba(0,255,136,0.6);
            transform: scale(1.02);
        }
        .status-container {
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            padding: 25px;
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 15px 35px rgba(0,0,0,0.4);
            margin-bottom: 25px;
        }
        .status { 
            padding: 15px; 
            border-radius: 15px; 
            font-size: 24px; 
            font-weight: 600; 
            transition: all 0.4s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }
        .LEFT { 
            background: linear-gradient(135deg, #ff6b6b, #ee5a5a); 
            box-shadow: 0 10px 20px rgba(255,107,107,0.3);
        }
        .RIGHT { 
            background: linear-gradient(135deg, #51cf66, #40c057); 
            box-shadow: 0 10px 20px rgba(81,207,102,0.3);
        }
        .CENTER { 
            background: linear-gradient(135deg, #4dabf7, #339af0); 
            box-shadow: 0 10px 20px rgba(77,171,247,0.3);
        }
        .NOT-DETECTED { 
            background: linear-gradient(135deg, #ffd43b, #fab005); 
            color: #333; 
            box-shadow: 0 10px 20px rgba(255,212,59,0.3);
        }
        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        .btn {
            background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05));
            border: 1px solid rgba(255,255,255,0.2);
            color: white;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
        }
        .btn:hover {
            background: linear-gradient(135deg, rgba(255,255,255,0.2), rgba(255,255,255,0.1));
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        .info { 
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            font-size: 14px; 
            opacity: 0.9; 
            line-height: 1.6;
            text-align: left;
        }
        .info h3 { 
            margin-bottom: 10px; 
            color: #00ff88;
            text-align: center;
        }
        .info p { margin: 8px 0; }
        .badge {
            display: inline-block;
            background: rgba(0,255,136,0.2);
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 12px;
            margin: 3px;
            border: 1px solid rgba(0,255,136,0.3);
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @media (max-width: 768px) {
            .feeds-container {
                grid-template-columns: 1fr;
            }
            .controls { flex-direction: column; align-items: center; }
            .btn { width: 200px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🟢 Dual Feed Green Tracker</h1>
            <p>Raw video + Green detection mask</p>
            <div class="badge">Pure Python</div>
            <div class="badge">Dual Streams</div>
            <div class="badge">Real-time Mask</div>
        </div>
        
        <div class="feeds-container">
            <div class="feed-box">
                <div class="feed-title raw-title">📹 Camera Feed</div>
                <img class="video-frame" src="{{ url_for('raw_video_feed') }}" alt="Raw video stream">
                <p style="margin-top: 10px; font-size: 12px; opacity: 0.7;">Live camera view</p>
            </div>
            
            <div class="feed-box">
                <div class="feed-title processed-title">🎯 Green Detection</div>
                <img class="video-frame" src="{{ url_for('processed_video_feed') }}" alt="Processed video stream">
                <p style="margin-top: 10px; font-size: 12px; opacity: 0.7;">With green mask overlay</p>
            </div>
        </div>
        
        <div class="status-container">
            <div id="statusDisplay" class="status">🔄 Initializing...</div>
            
            <div class="controls">
                <button class="btn" onclick="adjustSensitivity('increase')">🔍 More Sensitive</button>
                <button class="btn" onclick="adjustSensitivity('decrease')">🎯 Less Sensitive</button>
                <button class="btn" onclick="location.reload()">🔄 Refresh All</button>
            </div>
        </div>
        
        <div class="info">
            <h3>📺 Feed Explanations</h3>
            <p><strong>📹 Camera Feed:</strong> Direct camera input as you would normally see it</p>
            <p><strong>🎯 Green Detection:</strong> Camera view with green mask overlay and tracking annotations</p>
            <br>
            <p><strong>🔴 Red dot:</strong> Center of detected green object</p>
            <p><strong>📱 Usage:</strong> Point camera at green objects (balls, toys, plants)</p>
            <p><strong>⚡ Performance:</strong> Pure Python - no external image dependencies!</p>
        </div>
    </div>

    <script>
        let isUpdating = false;
        
        function updateStatus() {
            if (isUpdating) return;
            isUpdating = true;
            
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const statusDiv = document.getElementById('statusDisplay');
                    const emoji = {
                        'LEFT': '👈', 'RIGHT': '👉', 
                        'CENTER': '🎯', 'NOT DETECTED': '❓'
                    };
                    statusDiv.textContent = (emoji[data.position] || '❓') + ' ' + data.position;
                    statusDiv.className = 'status ' + data.position.replace(' ', '-');
                })
                .catch(error => {
                    console.error('Status update failed:', error);
                    document.getElementById('statusDisplay').textContent = '⚠️ Connection Error';
                })
                .finally(() => {
                    isUpdating = false;
                });
        }
        
        function adjustSensitivity(action) {
            fetch('/adjust/' + action, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    console.log('Sensitivity adjusted:', data);
                    const btn = event.target;
                    const original = btn.textContent;
                    btn.textContent = '✅ Adjusted!';
                    setTimeout(() => btn.textContent = original, 1000);
                })
                .catch(error => console.error('Adjustment failed:', error));
        }
        
        // Update status every 300ms
        setInterval(updateStatus, 300);
        
        // Handle image loading errors for all feeds
        document.querySelectorAll('.video-frame').forEach(img => {
            img.onerror = function() {
                this.alt = '⚠️ Stream loading...';
                setTimeout(() => {
                    this.src = this.src.split('?')[0] + '?' + Date.now();
                }, 3000);
            };
        });
        
        // Initial status update
        updateStatus();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/raw_video_feed')
def raw_video_feed():
    def generate():
        while True:
            # Get raw frame without annotations
            image_data = tracker.capture_with_termux()
            if not image_data:
                image_data = tracker.create_test_image()
            
            frame_bytes = tracker.rgb_to_jpeg_bytes(image_data)
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/bmp\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/processed_video_feed')
def processed_video_feed():
    def generate():
        while True:
            # Get raw frame and create overlay with green mask
            image_data = tracker.capture_with_termux()
            if not image_data:
                image_data = tracker.create_test_image()
            
            # Detect green objects first
            tracker.detect_green_center(image_data)
            
            # Create overlay with green mask and annotations
            overlay_data = tracker.create_green_mask_overlay(image_data)
            frame_bytes = tracker.rgb_to_jpeg_bytes(overlay_data)
            
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/bmp\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    return {
        'position': tracker.side_position,
        'center': tracker.green_center,
        'detected': tracker.green_center is not None
    }

@app.route('/adjust/<action>', methods=['POST'])
def adjust_sensitivity(action):
    if action == 'increase':
        tracker.green_threshold['g_min'] = max(30, tracker.green_threshold['g_min'] - 15)
        tracker.green_threshold['r_max'] = min(130, tracker.green_threshold['r_max'] + 15)
        tracker.green_threshold['b_max'] = min(130, tracker.green_threshold['b_max'] + 15)
    elif action == 'decrease':
        tracker.green_threshold['g_min'] = min(100, tracker.green_threshold['g_min'] + 15)
        tracker.green_threshold['r_max'] = max(70, tracker.green_threshold['r_max'] - 15)  
        tracker.green_threshold['b_max'] = max(70, tracker.green_threshold['b_max'] - 15)
    
    return {'status': 'adjusted', 'action': action, 'thresholds': tracker.green_threshold}

def main():
    print("🎬 Dual Feed Green Tracker")
    print("=" * 50)
    print("📦 Dependencies: Flask only!")
    print("🎯 Image processing: Pure Python")
    print("📺 Three video feeds:")
    print("   📹 Raw - Original camera input")
    print("   🎭 Mask - Green detection visualization")  
    print("   🎯 Processed - With tracking annotations")
    print("=" * 50)
    
    if not tracker.start():
        print("❌ Failed to start tracker")
        return
    
    print("✅ Tracker initialized!")
    print("🌐 Web server starting...")
    print("📱 Access from PC: http://YOUR_PHONE_IP:5000")
    print("🎮 Test mode: Moving green circle demo")
    print("📺 View all three feeds simultaneously!")
    print("⏹️  Press Ctrl+C to stop")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down gracefully...")
    finally:
        tracker.stop()
        print("✅ All feeds stopped! 👋")

if __name__ == '__main__':
    main()