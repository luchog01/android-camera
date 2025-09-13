# 30 FPS Video Stream Server Makefile

CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O3 -march=native -flto -DNDEBUG
TARGET = video_stream_server
SOURCE = camera_stream.cpp
LIBS = -lpthread -static-libgcc

# Optimization flags for maximum performance
OPTFLAGS = -ffast-math -funroll-loops -finline-functions -fomit-frame-pointer

# Default target
all: $(TARGET)

# Compile the video stream server
$(TARGET): $(SOURCE)
	@echo "🎬 Compiling 30 FPS video stream server..."
	$(CXX) $(CXXFLAGS) $(OPTFLAGS) -o $(TARGET) $(SOURCE) $(LIBS)
	@echo "✅ Build complete!"

# Clean build files
clean:
	@echo "🧹 Cleaning build files..."
	rm -f $(TARGET)
	rm -f /data/data/com.termux/files/home/camera_stream.h264
	rm -rf /data/data/com.termux/files/home/stream_output*

# Install all required dependencies
install-deps:
	@echo "📦 Installing video streaming dependencies..."
	pkg update
	pkg install -y clang make termux-api ffmpeg
	@echo "✅ All dependencies installed!"

# Set up camera permissions and test video recording
setup-permissions:
	@echo "🔐 Setting up camera permissions..."
	@echo "Please allow camera permission when prompted!"
	termux-camera-info
	@echo "🎥 Testing video recording capability..."
	termux-camera-record -c 0 -s 5 -l 1 /data/data/com.termux/files/home/test_video.mp4
	@echo "✅ Permissions and video recording test complete!"

# Test video recording
test-video:
	@echo "🎬 Testing 5-second video recording..."
	termux-camera-record -c 0 -s 5 -l 1 /data/data/com.termux/files/home/test_recording.mp4
	@echo "✅ Test recording saved to test_recording.mp4"

# Check FFmpeg installation
test-ffmpeg:
	@echo "🔧 Testing FFmpeg installation..."
	ffmpeg -version | head -1
	@echo "✅ FFmpeg is working!"

# Full system test
test-system: test-video test-ffmpeg
	@echo "🎯 System test complete! Ready for 30 FPS streaming."

# Quick build and run
quick: clean $(TARGET) run

# Run the video stream server
run: $(TARGET)
	@echo "🚀 Starting 30 FPS video stream server..."
	./$(TARGET)

# Build with debug info (for troubleshooting)
debug: CXXFLAGS = -std=c++17 -Wall -Wextra -g -DDEBUG
debug: $(TARGET)

# Show system info
info:
	@echo "📱 System Information:"
	@echo "Termux version: $(pkg show termux-api | grep Version || echo 'Unknown')"
	@echo "FFmpeg version: $(ffmpeg -version 2>/dev/null | head -1 || echo 'Not installed')"
	@echo "Camera info: $(termux-camera-info 2>/dev/null || echo 'Permission needed')"
	@echo "Available space: $(df -h ~ | tail -1)"

# Show help
help:
	@echo "🎬 30 FPS Video Stream Server"
	@echo ""
	@echo "Available commands:"
	@echo "  make install-deps      - Install required packages (clang, ffmpeg, termux-api)"
	@echo "  make setup-permissions - Setup camera permissions and test recording"
	@echo "  make test-system      - Test video recording and FFmpeg"
	@echo "  make                  - Compile the server"
	@echo "  make run              - Run the server"
	@echo "  make quick            - Clean, build, and run"
	@echo "  make debug            - Build with debug info"
	@echo "  make clean            - Remove all build and temp files"
	@echo "  make info             - Show system information"
	@echo "  make help             - Show this help"
	@echo ""
	@echo "🎯 For 30 FPS streaming, make sure:"
	@echo "  1. Camera permissions are granted"
	@echo "  2. FFmpeg is installed and working"
	@echo "  3. Good lighting conditions"
	@echo "  4. Stable device position"

.PHONY: all clean install-deps setup-permissions test-video test-ffmpeg test-system run quick debug info help