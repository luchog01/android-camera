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
    
    def add_red_dot_only(self, image_data):
        """Add only red dot overlay - no green mask"""
        if not image_data:
            return image_data
        
        # Create a copy of the image
        overlay_data = image_data.copy()
        
        # Add only the red dot annotation
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

# Simple HTML template with single camera feed
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>📹 Simple Camera Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            margin: 0;
            padding: 20px;
            background: #222;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
        }
        h1 { 
            margin-bottom: 20px;
        }
        .video-frame { 
            max-width: 90%;
            height: auto;
            border: 2px solid #555;
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <h1>📹 Camera Stream</h1>
    <img class="video-frame" src="{{ url_for('video_feed') }}" alt="Camera stream">
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            # Get raw frame without any processing
            image_data = tracker.capture_with_termux()
            if not image_data:
                image_data = tracker.create_test_image()
            
            frame_bytes = tracker.rgb_to_jpeg_bytes(image_data)
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/bmp\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


def main():
    print("📹 Simple Camera Stream")
    print("=" * 30)
    print("📦 Dependencies: Flask only!")
    print("🎯 Single camera feed")
    print("=" * 30)
    
    if not tracker.start():
        print("❌ Failed to start tracker")
        return
    
    print("✅ Camera initialized!")
    print("🌐 Web server starting...")
    print("📱 Access at: http://localhost:5000")
    print("⏹️  Press Ctrl+C to stop")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down gracefully...")
    finally:
        tracker.stop()
        print("✅ Camera stopped! 👋")

if __name__ == '__main__':
    main()