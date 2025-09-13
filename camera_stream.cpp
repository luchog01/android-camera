#include <iostream>
#include <string>
#include <thread>
#include <chrono>
#include <vector>
#include <fstream>
#include <sstream>
#include <cstdlib>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <signal.h>
#include <cstring>

class CameraStreamer {
private:
    int server_socket;
    bool running;
    const int PORT = 5000;
    const std::string BOUNDARY = "frame";
    
public:
    CameraStreamer() : server_socket(-1), running(false) {}
    
    ~CameraStreamer() {
        stop();
    }
    
    bool start() {
        // Create socket
        server_socket = socket(AF_INET, SOCK_STREAM, 0);
        if (server_socket < 0) {
            std::cerr << "Error creating socket" << std::endl;
            return false;
        }
        
        // Allow socket reuse
        int opt = 1;
        setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        
        // Setup server address
        struct sockaddr_in server_addr;
        memset(&server_addr, 0, sizeof(server_addr));
        server_addr.sin_family = AF_INET;
        server_addr.sin_addr.s_addr = INADDR_ANY;
        server_addr.sin_port = htons(PORT);
        
        // Bind socket
        if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
            std::cerr << "Error binding socket" << std::endl;
            close(server_socket);
            return false;
        }
        
        // Listen for connections
        if (listen(server_socket, 5) < 0) {
            std::cerr << "Error listening on socket" << std::endl;
            close(server_socket);
            return false;
        }
        
        running = true;
        std::cout << "Camera stream server started on port " << PORT << std::endl;
        std::cout << "Access stream at: http://localhost:" << PORT << "/stream" << std::endl;
        
        return true;
    }
    
    void stop() {
        running = false;
        if (server_socket >= 0) {
            close(server_socket);
            server_socket = -1;
        }
    }
    
    void run() {
        while (running) {
            struct sockaddr_in client_addr;
            socklen_t client_len = sizeof(client_addr);
            
            int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_len);
            if (client_socket < 0) {
                if (running) {
                    std::cerr << "Error accepting connection" << std::endl;
                }
                continue;
            }
            
            // Handle client in a separate thread
            std::thread client_thread(&CameraStreamer::handleClient, this, client_socket);
            client_thread.detach();
        }
    }
    
private:
    void handleClient(int client_socket) {
        char buffer[1024];
        int bytes_received = recv(client_socket, buffer, sizeof(buffer) - 1, 0);
        
        if (bytes_received <= 0) {
            close(client_socket);
            return;
        }
        
        buffer[bytes_received] = '\0';
        std::string request(buffer);
        
        // Check if it's a request for the stream
        if (request.find("GET /stream") != std::string::npos) {
            sendMJPEGStream(client_socket);
        } else if (request.find("GET /") != std::string::npos) {
            sendHTML(client_socket);
        } else {
            send404(client_socket);
        }
        
        close(client_socket);
    }
    
    void sendHTML(int client_socket) {
        std::string html = 
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n\r\n"
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "    <title>Camera Stream</title>\n"
            "    <style>\n"
            "        body { font-family: Arial, sans-serif; text-align: center; }\n"
            "        img { max-width: 100%; height: auto; border: 2px solid #333; }\n"
            "    </style>\n"
            "</head>\n"
            "<body>\n"
            "    <h1>Phone Camera Stream</h1>\n"
            "    <img src=\"/stream\" alt=\"Camera Stream\">\n"
            "    <p>Live stream from back camera</p>\n"
            "</body>\n"
            "</html>\n";
        
        send(client_socket, html.c_str(), html.length(), 0);
    }
    
    void sendMJPEGStream(int client_socket) {
        // Send MJPEG headers
        std::string headers = 
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: multipart/x-mixed-replace; boundary=" + BOUNDARY + "\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: close\r\n\r\n";
        
        send(client_socket, headers.c_str(), headers.length(), 0);
        
        // Stream frames
        while (running) {
            std::vector<char> frame_data = captureFrame();
            if (frame_data.empty()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
                continue;
            }
            
            // Send frame boundary
            std::string boundary_header = 
                "--" + BOUNDARY + "\r\n"
                "Content-Type: image/jpeg\r\n"
                "Content-Length: " + std::to_string(frame_data.size()) + "\r\n\r\n";
            
            if (send(client_socket, boundary_header.c_str(), boundary_header.length(), 0) < 0) {
                break;
            }
            
            // Send frame data
            if (send(client_socket, frame_data.data(), frame_data.size(), 0) < 0) {
                break;
            }
            
            // Send frame end
            std::string frame_end = "\r\n";
            if (send(client_socket, frame_end.c_str(), frame_end.length(), 0) < 0) {
                break;
            }
            
            // Control frame rate (adjust as needed)
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
    
    void send404(int client_socket) {
        std::string response = 
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n\r\n"
            "<html><body><h1>404 - Not Found</h1></body></html>";
        
        send(client_socket, response.c_str(), response.length(), 0);
    }
    
    std::vector<char> captureFrame() {
        // Use termux-api to capture photo from back camera
        // Save to temporary file
        std::string temp_file = "/data/data/com.termux/files/home/temp_camera.jpg";
        std::string command = "termux-camera-photo -c 0 " + temp_file + " 2>/dev/null";
        
        // Execute camera capture
        int result = system(command.c_str());
        if (result != 0) {
            return std::vector<char>();
        }
        
        // Read the captured image
        std::ifstream file(temp_file, std::ios::binary);
        if (!file.is_open()) {
            return std::vector<char>();
        }
        
        // Get file size
        file.seekg(0, std::ios::end);
        size_t file_size = file.tellg();
        file.seekg(0, std::ios::beg);
        
        // Read file data
        std::vector<char> data(file_size);
        file.read(data.data(), file_size);
        file.close();
        
        // Clean up temporary file
        unlink(temp_file.c_str());
        
        return data;
    }
};

// Global streamer instance for signal handling
CameraStreamer* g_streamer = nullptr;

void signalHandler(int signal) {
    std::cout << "\nReceived signal " << signal << ", shutting down..." << std::endl;
    if (g_streamer) {
        g_streamer->stop();
    }
    exit(0);
}

int main() {
    // Setup signal handlers
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);
    
    CameraStreamer streamer;
    g_streamer = &streamer;
    
    if (!streamer.start()) {
        std::cerr << "Failed to start camera streamer" << std::endl;
        return 1;
    }
    
    std::cout << "Starting camera stream server..." << std::endl;
    std::cout << "Press Ctrl+C to stop" << std::endl;
    
    streamer.run();
    
    return 0;
}