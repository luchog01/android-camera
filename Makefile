# High-Speed Camera Stream Server Makefile

CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O3 -march=native -flto -DNDEBUG
TARGET = high_speed_camera_stream
SOURCE = camera_stream.cpp
LIBS = -lpthread -static-libgcc

# Optimization flags for maximum performance
OPTFLAGS = -ffast-math -funroll-loops -finline-functions -fomit-frame-pointer

# Default target
all: $(TARGET)

# Compile the high-speed camera streamer
$(TARGET): $(SOURCE)
	@echo "🔨 Compiling high-speed camera streamer..."
	$(CXX) $(CXXFLAGS) $(OPTFLAGS) -o $(TARGET) $(SOURCE) $(LIBS)
	@echo "✅ Build complete!"

# Clean build files
clean:
	@echo "🧹 Cleaning build files..."
	rm -f $(TARGET)

# Install all required dependencies
install-deps:
	@echo "📦 Installing dependencies..."
	pkg update
	pkg install -y clang make termux-api
	@echo "✅ Dependencies installed!"

# Set up camera permissions
setup-permissions:
	@echo "🔐 Setting up camera permissions..."
	@echo "Please allow camera permission when prompted!"
	termux-camera-info
	@echo "✅ Permissions check complete!"

# Quick build and run
quick: clean $(TARGET) run

# Run the high-speed server
run: $(TARGET)
	@echo "🚀 Starting high-speed camera server..."
	./$(TARGET)

# Build with debug info (for troubleshooting)
debug: CXXFLAGS = -std=c++17 -Wall -Wextra -g -DDEBUG
debug: $(TARGET)

# Show help
help:
	@echo "📚 High-Speed Camera Stream Server"
	@echo ""
	@echo "Available commands:"
	@echo "  make install-deps    - Install required packages"
	@echo "  make setup-permissions - Setup camera permissions"
	@echo "  make                 - Compile the server"
	@echo "  make run             - Run the server"
	@echo "  make quick           - Clean, build, and run"
	@echo "  make debug           - Build with debug info"
	@echo "  make clean           - Remove build files"
	@echo "  make help            - Show this help"

.PHONY: all clean install-deps setup-permissions run quick debug help