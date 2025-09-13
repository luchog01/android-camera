#!/usr/bin/env python3
"""
Super Efficient Video Streamer for Termux
Captures back camera feed and streams via Flask with minimal overhead
"""

import subprocess
import threading
import time
import io
from flask import Flask, Response, render_template_string
import queue
import signal
import sys
import os

app = Flask(__name__)

# Global variables
frame_queue = queue.Queue(maxsize=2)  # Small buffer to reduce latency
camera_process = None
streaming = False

# HTML template for the viewer
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Termux Camera Stream</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            margin: 0;
            padding: 10px;
            background: #000;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            font-family: Arial, sans-serif;
        }
        .container {
            text-align: center;
        }
        .stream {
            max-width: 100%;
            max-height: 90vh;
            border: 2px solid #333;
            border-radius: 8px;
        }
        .controls {
            margin: 10px 0;
            color: white;
        }
        button {
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
        button:hover {
            background: #0056b3;
        }
        .status {
            color: #28a745;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2 style="color: white;">Termux Camera Stream</h2>
        <div class="status">● LIVE</div>
        <img src="/video_feed" alt="Video Stream" class="stream" id="videoStream">
        <div class="controls">
            <button onclick="location.reload()">Refresh Stream</button>
        </div>
    </div>
    <script>
        // Auto-refresh if stream fails
        document.getElementById('videoStream').onerror = function() {
            setTimeout(() => location.reload(), 2000);
        };
    </script>
</body>
</html>
"""


def capture_video():
    """
    Continuously capture video frames using termux-api
    Uses termux-camera-photo in a loop for efficiency
    """
    global streaming, camera_process

    print("Starting video capture thread...")

    while streaming:
        try:
            # Use termux-camera-photo with optimized settings
            # -c 0 = back camera, -s = size (smaller for efficiency)
            cmd = [
                "termux-camera-photo",
                "-c",
                "0",  # Back camera
                "-s",
                "640x480",  # Lower resolution for efficiency
                "/dev/stdout",  # Output to stdout
            ]

            # Start camera process
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            # Read the image data
            image_data, error = process.communicate(timeout=5)

            if process.returncode == 0 and image_data:
                # Add frame to queue (non-blocking)
                try:
                    frame_queue.put_nowait(image_data)
                except queue.Full:
                    # Remove old frame if queue is full
                    try:
                        frame_queue.get_nowait()
                        frame_queue.put_nowait(image_data)
                    except queue.Empty:
                        pass
            else:
                print(f"Camera error: {error.decode() if error else 'Unknown error'}")
                time.sleep(0.1)

        except subprocess.TimeoutExpired:
            print("Camera timeout, retrying...")
            if process:
                process.kill()
            time.sleep(0.1)
        except Exception as e:
            print(f"Capture error: {e}")
            time.sleep(0.1)

    print("Video capture thread stopped")


def generate_frames():
    """
    Generator function to yield frames for streaming
    """
    print("Starting frame generator...")

    while streaming:
        try:
            # Get frame from queue with timeout
            frame_data = frame_queue.get(timeout=1.0)

            # Yield frame in multipart format
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n"
            )

        except queue.Empty:
            # Send a placeholder if no frames available
            continue
        except Exception as e:
            print(f"Frame generation error: {e}")
            break


@app.route("/")
def index():
    """Serve the main viewer page"""
    return render_template_string(HTML_TEMPLATE)


@app.route("/video_feed")
def video_feed():
    """Video streaming route"""
    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status")
def status():
    """Status endpoint"""
    return {
        "streaming": streaming,
        "queue_size": frame_queue.qsize(),
        "uptime": time.time(),
    }


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global streaming
    print("\nShutting down gracefully...")
    streaming = False
    sys.exit(0)


def check_termux_api():
    """Check if termux-api is available"""
    try:
        result = subprocess.run(
            ["termux-camera-info"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print("✓ Termux API camera access confirmed")
            print("Available cameras:")
            print(result.stdout)
            return True
        else:
            print("✗ Termux API camera access failed")
            return False
    except Exception as e:
        print(f"✗ Error checking termux-api: {e}")
        return False


def main():
    global streaming

    print("=" * 50)
    print("Termux Super Efficient Video Streamer")
    print("=" * 50)

    # Check termux-api availability
    if not check_termux_api():
        print("\nPlease install termux-api:")
        print("pkg install termux-api")
        print("Also install the Termux:API app from F-Droid or Google Play")
        return

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start streaming
    streaming = True

    # Start video capture thread
    capture_thread = threading.Thread(target=capture_video, daemon=True)
    capture_thread.start()

    print(f"\n🎥 Starting video stream server...")
    print(f"📱 Camera: Back camera (0)")
    print(f"🌐 Access your stream at:")
    print(f"   Local: http://127.0.0.1:5000")
    print(f"   Network: http://0.0.0.0:5000")
    print(f"   Status: http://0.0.0.0:5000/status")
    print(f"\n⚡ Optimized for Termux with minimal overhead")
    print(f"📊 Resolution: 640x480 for efficiency")
    print(f"🔄 Press Ctrl+C to stop\n")

    try:
        # Run Flask app
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,  # Disable debug for better performance
            threaded=True,
            use_reloader=False,
        )
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        streaming = False


if __name__ == "__main__":
    main()
