# simple_server.py - Простой HTTP сервер для проверки порта
import os
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple_server")

PORT = int(os.getenv("PORT", 5000))

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Hello from Render! Server is working.')
        
    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'POST received')

def main():
    server = HTTPServer(('0.0.0.0', PORT), SimpleHandler)
    logger.info(f"🚀 Starting simple HTTP server on port {PORT}")
    logger.info(f"🌐 Server will be available at http://0.0.0.0:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    main()
