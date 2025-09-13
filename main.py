#!/usr/bin/env python3
"""
Android Camera Stream Server for Termux
Streams camera feed via Flask web server on port 5000
"""

import cv2
import threading
import time
from flask import Flask, render_template_string, Response
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables for camera
camera = None
camera_lock = threading.Lock()
frame = None

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Android Camera Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            margin: 0;
            padding: 20px;
            background-color: #1a1a1a;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
        }
        h1 {
            color: #4CAF50;
            margin-bottom: 30px;
        }
        .container {
            max-width: 100%;
            margin: 0 auto;
        }
        #camera-feed {
            max-width: 100%;
            height: auto;
            border: 3px solid #4CAF50;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
        .info {
            margin-top: 20px;
            background-color: #333;
            padding: 15px;
            border-radius: 5px;
        }
        .status {
            color: #4CAF50;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📱 Android Camera Stream</h1>
        <div class="info">
            <p class="status">● LIVE STREAM</p>
            <p>Camera feed from Termux</p>
        </div>
        <br>
        <img id="camera-feed" src="{{ url_for('video_feed') }}" alt="Camera feed loading...">
    </div>
    
    <script>
        // Add error handling for image loading
        document.getElementById('camera-feed').onerror = function() {
            this.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMzMzIi8+CiAgPHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCwgc2Fucy1zZXJpZiIgZm9udC1zaXplPSIxOCIgZmlsbD0iI2ZmZiIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkNhbWVyYSBub3QgYXZhaWxhYmxlPC90ZXh0Pgo8L3N2Zz4K';
        };
    </script>
</body>
</html>
"""


def initialize_camera():
    """Initialize camera with fallback options for Android/Termux"""
    global camera

    # Try different camera indices and backends for Android
    camera_indices = [0, 1, 2, -1]  # -1 sometimes works for default camera
    backends = [cv2.CAP_V4L2, cv2.CAP_ANDROID, cv2.CAP_ANY]

    for backend in backends:
        for index in camera_indices:
            try:
                logger.info(f"Trying camera index {index} with backend {backend}")
                test_camera = cv2.VideoCapture(index, backend)

                if test_camera.isOpened():
                    # Test if we can actually read a frame
                    ret, test_frame = test_camera.read()
                    if ret and test_frame is not None:
                        camera = test_camera

                        # Set camera properties for better performance
                        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        camera.set(cv2.CAP_PROP_FPS, 30)

                        logger.info(
                            f"Successfully initialized camera {index} with backend {backend}"
                        )
                        return True
                    else:
                        test_camera.release()
                else:
                    test_camera.release()

            except Exception as e:
                logger.error(f"Error with camera {index}, backend {backend}: {e}")
                continue

    logger.error("Failed to initialize any camera")
    return False


def capture_frames():
    """Continuously capture frames from camera"""
    global frame, camera

    if not initialize_camera():
        return

    while True:
        try:
            with camera_lock:
                if camera and camera.isOpened():
                    ret, new_frame = camera.read()
                    if ret and new_frame is not None:
                        # Flip frame horizontally for mirror effect (typical for front-facing camera)
                        frame = cv2.flip(new_frame, 1)
                    else:
                        logger.warning("Failed to read frame from camera")
                        time.sleep(0.1)
                else:
                    logger.error("Camera not available")
                    time.sleep(1)
                    if not initialize_camera():
                        time.sleep(5)  # Wait longer before retrying
        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            time.sleep(1)
            # Try to reinitialize camera
            if camera:
                camera.release()
            if not initialize_camera():
                time.sleep(5)


def generate_frames():
    """Generate frames for streaming"""
    global frame

    while True:
        if frame is not None:
            try:
                # Encode frame as JPEG
                ret, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                )
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                    )
                else:
                    logger.warning("Failed to encode frame")
            except Exception as e:
                logger.error(f"Error generating frame: {e}")

        time.sleep(0.033)  # ~30 FPS


@app.route("/")
def index():
    """Main page with camera feed"""
    return render_template_string(HTML_TEMPLATE)


@app.route("/video_feed")
def video_feed():
    """Video streaming route"""
    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/health")
def health_check():
    """Health check endpoint"""
    camera_status = "OK" if camera and camera.isOpened() else "ERROR"
    return {"status": "running", "camera": camera_status, "port": 5000}


if __name__ == "__main__":
    logger.info("Starting Android Camera Stream Server...")

    # Start camera capture in a separate thread
    capture_thread = threading.Thread(target=capture_frames, daemon=True)
    capture_thread.start()

    # Give camera time to initialize
    time.sleep(2)

    logger.info("Camera stream server starting on http://0.0.0.0:5000")
    logger.info("Access from any device on your network using your phone's IP address")

    try:
        # Start Flask server
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    finally:
        # Clean up camera
        if camera:
            camera.release()
        cv2.destroyAllWindows()
