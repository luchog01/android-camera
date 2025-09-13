#!/bin/bash

# High-Speed Camera Stream Server Setup Script
# This script will guide you through the complete setup process

echo "🚀 High-Speed Camera Stream Server Setup 🚀"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Step 1: Check if we're in Termux
print_step "Checking Termux environment..."
if [[ "$PREFIX" != *"com.termux"* ]]; then
    print_error "This script must be run in Termux!"
    print_warning "Please install Termux from F-Droid or Google Play Store"
    exit 1
fi
print_success "Termux environment detected"

# Step 2: Update packages and install dependencies
print_step "Installing required packages..."
pkg update -y
pkg install -y clang make termux-api git

if [ $? -eq 0 ]; then
    print_success "All packages installed successfully"
else
    print_error "Failed to install packages"
    exit 1
fi

# Step 3: Create project directory
print_step "Creating project directory..."
PROJECT_DIR="$HOME/camera-stream-server"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"
print_success "Project directory created: $PROJECT_DIR"

# Step 4: Create the source files
print_step "Creating source files..."

# Check if files need to be created
if [ ! -f "camera_stream.cpp" ]; then
    echo "Please save the C++ code as 'camera_stream.cpp' in this directory:"
    echo "$PROJECT_DIR"
    echo ""
    print_warning "After saving the C++ file, run this script again or continue manually"
fi

if [ ! -f "Makefile" ]; then
    echo "Please save the Makefile in this directory:"
    echo "$PROJECT_DIR"
    echo ""
    print_warning "After saving the Makefile, run this script again or continue manually"
fi

# Step 5: Set up camera permissions
print_step "Setting up camera permissions..."
echo "The next command will request camera permission."
echo "Please ALLOW camera access when prompted!"
read -p "Press Enter to continue..."

termux-camera-info 2>/dev/null
if [ $? -eq 0 ]; then
    print_success "Camera permissions are working"
else
    print_warning "Camera permission might need to be granted manually"
    print_warning "Go to Android Settings > Apps > Termux > Permissions > Camera > Allow"
fi

# Step 6: Test camera capture
print_step "Testing camera capture..."
TEST_IMG="$HOME/test_camera.jpg"
termux-camera-photo -c 0 "$TEST_IMG" 2>/dev/null
if [ -f "$TEST_IMG" ] && [ -s "$TEST_IMG" ]; then
    print_success "Camera capture test successful"
    rm -f "$TEST_IMG"
else
    print_error "Camera capture test failed"
    print_warning "Make sure:"
    print_warning "1. Camera permission is granted"
    print_warning "2. No other app is using the camera"
    print_warning "3. Your device has a back camera"
fi

# Step 7: Build the project (if files exist)
if [ -f "camera_stream.cpp" ] && [ -f "Makefile" ]; then
    print_step "Building the project..."
    make clean
    make
    
    if [ $? -eq 0 ]; then
        print_success "Project built successfully!"
    else
        print_error "Build failed. Check the error messages above."
        exit 1
    fi
else
    print_warning "Source files not found. Please add them and run 'make' manually."
fi

# Step 8: Get device IP address
print_step "Getting device IP address..."
DEVICE_IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+')
if [ -z "$DEVICE_IP" ]; then
    DEVICE_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

echo ""
echo "🎉 Setup Complete! 🎉"
echo "===================="
echo ""
print_success "Project location: $PROJECT_DIR"
print_success "Executable: high_speed_camera_stream"
echo ""
echo "📱 To start the server:"
echo "   cd $PROJECT_DIR"
echo "   ./high_speed_camera_stream"
echo ""
echo "🌐 Access URLs:"
echo "   Local:    http://localhost:5000"
if [ ! -z "$DEVICE_IP" ]; then
echo "   Network:  http://$DEVICE_IP:5000"
fi
echo "   Stream:   http://localhost:5000/stream"
echo ""
echo "💡 Tips for maximum FPS:"
echo "   • Close other apps using the camera"
echo "   • Ensure good lighting conditions"
echo "   • Use a stable network connection"
echo "   • Keep Termux in the foreground"
echo ""
echo "🔧 Useful commands:"
echo "   make help          - Show all available commands"
echo "   make quick         - Quick rebuild and run"
echo "   make clean         - Clean build files"
echo ""

# Final check
if [ -f "$PROJECT_DIR/high_speed_camera_stream" ]; then
    print_success "Ready to run! Execute: ./high_speed_camera_stream"
else
    print_warning "Executable not found. Run 'make' to build the project."
fi