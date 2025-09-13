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
#include <atomic>
#include <memory>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>

class VideoStreamServer {
private:
    int server_socket;
    std::atomic<bool> running;
    std::atomic<bool> ffmpeg_running;
    const int PORT = 5000;
    const std::string BOUNDARY = "frame";
    
    pid_t ffmpeg_pid = -1;
    std::string fifo_path = "/data/data/com.termux/files/home/camera_stream.h264";
    std::string output_path = "/data/data/com.termux/files/home/stream_output";
    
public:
    VideoStreamServer() : server_socket(-1), running(false), ffmpeg_running(false) {}
    
    ~VideoStreamServer() {
        stop();
    }
    
    bool start() {
        // Create socket
        server_socket = socket(AF_INET, SOCK_STREAM, 0);
        if (server_socket < 0) {
            std::cerr << "Error creating socket" << std::endl;
            return false;
        }
        
        // Optimize socket settings
        int opt = 1;
        setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        setsockopt(server_socket, SOL_SOCKET, SO_REUSEPORT, &opt, sizeof(opt));
        
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
        if (listen(server_socket, 10) < 0) {
            std::cerr << "Error listening on socket" << std::endl;
            close(server_socket);
            return false;
        }
        
        running = true;
        
        // Start video streaming pipeline
        if (!startVideoStream()) {
            std::cerr << "Failed to start video streaming pipeline" << std::endl;
            stop();
            return false;
        }
        
        std::cout << "🚀 Real-time video stream server started on port " << PORT << std::endl;
        std::cout << "📹 30 FPS H.264 video streaming active" << std::endl;
        std::cout << "🌐 Access: http://localhost:" << PORT << std::endl;
        
        return true;
    }
    
    void stop() {
        running = false;
        ffmpeg_running = false;
        
        // Stop FFmpeg process
        if (ffmpeg_pid > 0) {
            kill(ffmpeg_pid, SIGTERM);
            int status;
            waitpid(ffmpeg_pid, &status, 0);
            ffmpeg_pid = -1;
        }
        
        if (server_socket >= 0) {
            close(server_socket);
            server_socket = -1;
        }
        
        // Clean up files
        unlink(fifo_path.c_str());
        std::string cmd = "rm -rf " + output_path + "*";
        system(cmd.c_str());
    }
    
    void run() {
        fd_set read_fds;
        struct timeval timeout;
        
        while (running) {
            FD_ZERO(&read_fds);
            FD_SET(server_socket, &read_fds);
            
            timeout.tv_sec = 0;
            timeout.tv_usec = 100000;
            
            int activity = select(server_socket + 1, &read_fds, nullptr, nullptr, &timeout);
            
            if (activity < 0 && errno != EINTR) {
                break;
            }
            
            if (FD_ISSET(server_socket, &read_fds)) {
                struct sockaddr_in client_addr;
                socklen_t client_len = sizeof(client_addr);
                
                int client_socket = accept(server_socket, (struct sockaddr*)&client_addr, &client_len);
                if (client_socket >= 0) {
                    std::thread client_thread(&VideoStreamServer::handleClient, this, client_socket);
                    client_thread.detach();
                }
            }
        }
    }
    
private:
    bool startVideoStream() {
        std::cout << "🎬 Starting video streaming pipeline..." << std::endl;
        
        // Create output directory
        mkdir(output_path.c_str(), 0755);
        
        // Create FIFO pipe for communication
        unlink(fifo_path.c_str());
        if (mkfifo(fifo_path.c_str(), 0666) != 0) {
            std::cerr << "Failed to create FIFO pipe" << std::endl;
            return false;
        }
        
        // Start the streaming pipeline in background
        std::thread stream_thread(&VideoStreamServer::runStreamingPipeline, this);
        stream_thread.detach();
        
        // Wait a moment for pipeline to initialize
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        return true;
    }
    
    void runStreamingPipeline() {
        std::cout << "📡 Starting camera and FFmpeg pipeline..." << std::endl;
        
        // Start termux-camera-record to stream to FIFO
        std::string camera_cmd = 
            "termux-camera-record -c 0 -s 30 -l 0 " + fifo_path + " &";
        
        system(camera_cmd.c_str());
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
        
        // Start FFmpeg to convert H.264 to MJPEG stream
        std::string ffmpeg_cmd = 
            "ffmpeg -y -f h264 -i " + fifo_path + 
            " -f image2 -vf scale=640:480 -q:v 3 -r 30 "
            "-strftime 1 " + output_path + "_%Y%m%d_%H%M%S_%f.jpg"
            " > /dev/null 2>&1 &";
        
        std::cout << "🔄 FFmpeg command: " << ffmpeg_cmd << std::endl;
        
        ffmpeg_pid = fork();
        if (ffmpeg_pid == 0) {
            // Child process - run FFmpeg
            execl("/data/data/com.termux/files/usr/bin/sh", "sh", "-c", ffmpeg_cmd.c_str(), (char*)nullptr);
            exit(1);
        } else if (ffmpeg_pid > 0) {
            ffmpeg_running = true;
            std::cout << "✅ FFmpeg pipeline started (PID: " << ffmpeg_pid << ")" << std::endl;
        } else {
            std::cerr << "❌ Failed to start FFmpeg" << std::endl;
            return;
        }
        
        // Monitor the pipeline
        while (running && ffmpeg_running) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            
            // Check if FFmpeg is still running
            if (kill(ffmpeg_pid, 0) != 0) {
                std::cerr << "⚠️  FFmpeg process died, restarting..." << std::endl;
                ffmpeg_running = false;
                std::this_thread::sleep_for(std::chrono::seconds(2));
                runStreamingPipeline(); // Restart
                break;
            }
        }
    }
    
    void handleClient(int client_socket) {
        int opt = 1;
        setsockopt(client_socket, IPPROTO_TCP, TCP_NODELAY, &opt, sizeof(opt));
        
        char buffer[1024];
        int bytes_received = recv(client_socket, buffer, sizeof(buffer) - 1, 0);
        
        if (bytes_received <= 0) {
            close(client_socket);
            return;
        }
        
        buffer[bytes_received] = '\0';
        std::string request(buffer);
        
        if (request.find("GET /stream") != std::string::npos) {
            streamMJPEGVideo(client_socket);
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
            "Connection: close\r\n"
            "Cache-Control: no-cache\r\n\r\n"
            "<!DOCTYPE html>\n"
            "<html>\n"
            "<head>\n"
            "    <title>🚀 30 FPS Video Stream</title>\n"
            "    <meta charset='utf-8'>\n"
            "    <meta name='viewport' content='width=device-width, initial-scale=1'>\n"
            "    <style>\n"
            "        body { \n"
            "            font-family: 'Courier New', monospace;\n"
            "            text-align: center;\n"
            "            background: linear-gradient(45deg, #000428, #004e92);\n"
            "            color: #00ff41;\n"
            "            margin: 0;\n"
            "            padding: 20px;\n"
            "            min-height: 100vh;\n"
            "        }\n"
            "        .container {\n"
            "            max-width: 1200px;\n"
            "            margin: 0 auto;\n"
            "        }\n"
            "        h1 {\n"
            "            font-size: 2.5em;\n"
            "            text-shadow: 0 0 20px #00ff41;\n"
            "            margin-bottom: 20px;\n"
            "        }\n"
            "        .stream-container {\n"
            "            background: rgba(0,0,0,0.7);\n"
            "            border: 2px solid #00ff41;\n"
            "            border-radius: 10px;\n"
            "            padding: 20px;\n"
            "            margin: 20px 0;\n"
            "            box-shadow: 0 0 30px rgba(0,255,65,0.3);\n"
            "        }\n"
            "        img {\n"
            "            max-width: 100%;\n"
            "            height: auto;\n"
            "            border-radius: 5px;\n"
            "            box-shadow: 0 0 20px rgba(0,255,65,0.5);\n"
            "        }\n"
            "        .stats {\n"
            "            display: flex;\n"
            "            justify-content: space-around;\n"
            "            margin: 20px 0;\n"
            "            flex-wrap: wrap;\n"
            "        }\n"
            "        .stat {\n"
            "            background: rgba(0,255,65,0.1);\n"
            "            border: 1px solid #00ff41;\n"
            "            border-radius: 5px;\n"
            "            padding: 10px 20px;\n"
            "            margin: 5px;\n"
            "        }\n"
            "        .blink {\n"
            "            animation: blink 1s infinite;\n"
            "        }\n"
            "        @keyframes blink {\n"
            "            0%, 50% { opacity: 1; }\n"
            "            51%, 100% { opacity: 0.3; }\n"
            "        }\n"
            "    </style>\n"
            "</head>\n"
            "<body>\n"
            "    <div class='container'>\n"
            "        <h1>🚀 HIGH-SPEED VIDEO STREAM 🚀</h1>\n"
            "        <div class='stats'>\n"
            "            <div class='stat'>📹 H.264 Video Pipeline</div>\n"
            "            <div class='stat'>⚡ 30 FPS Target</div>\n"
            "            <div class='stat'>🎯 640x480 Resolution</div>\n"
            "            <div class='stat blink'>🔴 LIVE</div>\n"
            "        </div>\n"
            "        <div class='stream-container'>\n"
            "            <img src='/stream' alt='30 FPS Video Stream' id='videoStream'>\n"
            "        </div>\n"
            "        <div class='stats'>\n"
            "            <div class='stat'>🌐 Real-time MJPEG Stream</div>\n"
            "            <div class='stat'>📡 Ultra-low Latency</div>\n"
            "        </div>\n"
            "    </div>\n"
            "    <script>\n"
            "        // Auto-refresh on connection loss\n"
            "        document.getElementById('videoStream').onerror = function() {\n"
            "            setTimeout(() => {\n"
            "                this.src = '/stream?' + new Date().getTime();\n"
            "            }, 1000);\n"
            "        };\n"
            "    </script>\n"
            "</body>\n"
            "</html>\n";
        
        send(client_socket, html.c_str(), html.length(), 0);
    }
    
    void streamMJPEGVideo(int client_socket) {
        // Send MJPEG headers
        std::string headers = 
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: multipart/x-mixed-replace; boundary=" + BOUNDARY + "\r\n"
            "Cache-Control: no-cache, no-store, must-revalidate\r\n"
            "Pragma: no-cache\r\n"
            "Expires: 0\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n\r\n";
        
        if (send(client_socket, headers.c_str(), headers.length(), 0) < 0) {
            return;
        }
        
        std::cout << "📺 Client connected for 30 FPS video stream" << std::endl;
        
        std::string last_file = "";
        auto last_check = std::chrono::steady_clock::now();
        
        while (running) {
            // Find the latest frame file
            std::string latest_file = getLatestFrame();
            
            if (!latest_file.empty() && latest_file != last_file) {
                // Read and send the frame
                std::ifstream file(latest_file, std::ios::binary | std::ios::ate);
                if (file.is_open()) {
                    size_t file_size = file.tellg();
                    file.seekg(0, std::ios::beg);
                    
                    if (file_size > 0) {
                        std::vector<char> frame_data(file_size);
                        file.read(frame_data.data(), file_size);
                        file.close();
                        
                        // Send frame boundary
                        std::string boundary_header = 
                            "--" + BOUNDARY + "\r\n"
                            "Content-Type: image/jpeg\r\n"
                            "Content-Length: " + std::to_string(frame_data.size()) + "\r\n\r\n";
                        
                        if (send(client_socket, boundary_header.c_str(), boundary_header.length(), MSG_NOSIGNAL) < 0) {
                            break;
                        }
                        
                        if (send(client_socket, frame_data.data(), frame_data.size(), MSG_NOSIGNAL) < 0) {
                            break;
                        }
                        
                        if (send(client_socket, "\r\n", 2, MSG_NOSIGNAL) < 0) {
                            break;
                        }
                        
                        last_file = latest_file;
                    }
                }
            }
            
            // Clean old files periodically
            auto now = std::chrono::steady_clock::now();
            if (std::chrono::duration_cast<std::chrono::seconds>(now - last_check).count() > 5) {
                cleanOldFrames();
                last_check = now;
            }
            
            // Small delay to prevent excessive file system polling
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        
        std::cout << "📺 Client disconnected from video stream" << std::endl;
    }
    
    std::string getLatestFrame() {
        std::string cmd = "ls -t " + output_path + "*.jpg 2>/dev/null | head -1";
        FILE* pipe = popen(cmd.c_str(), "r");
        if (!pipe) return "";
        
        char buffer[256];
        std::string latest_file = "";
        if (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            latest_file = buffer;
            // Remove newline
            if (!latest_file.empty() && latest_file.back() == '\n') {
                latest_file.pop_back();
            }
        }
        pclose(pipe);
        
        return latest_file;
    }
    
    void cleanOldFrames() {
        // Keep only the latest 10 frames
        std::string cmd = "ls -t " + output_path + "*.jpg 2>/dev/null | tail -n +11 | xargs -r rm -f";
        system(cmd.c_str());
    }
    
    void send404(int client_socket) {
        std::string response = 
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n\r\n"
            "<html><body style='background:#000;color:#00ff41;text-align:center;font-family:monospace;'>"
            "<h1>404 - Stream Not Found</h1>"
            "<p>Available endpoints:</p>"
            "<p><a href='/' style='color:#00ff41;'>🏠 Home</a> | "
            "<a href='/stream' style='color:#00ff41;'>📺 Direct Stream</a></p>"
            "</body></html>";
        
        send(client_socket, response.c_str(), response.length(), 0);
    }
};

VideoStreamServer* g_server = nullptr;

void signalHandler(int signal) {
    std::cout << "\n🛑 Received signal " << signal << ", shutting down video server..." << std::endl;
    if (g_server) {
        g_server->stop();
    }
    exit(0);
}

int main() {
    std::cout << "🎬 30 FPS Video Stream Server 🎬" << std::endl;
    std::cout << "Real H.264 video pipeline with FFmpeg" << std::endl;
    
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);
    
    VideoStreamServer server;
    g_server = &server;
    
    if (!server.start()) {
        std::cerr << "❌ Failed to start video stream server" << std::endl;
        return 1;
    }
    
    std::cout << "🎯 Press Ctrl+C to stop streaming" << std::endl;
    
    server.run();
    
    return 0;
}