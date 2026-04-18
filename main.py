from gevent import monkey
monkey.patch_all()

from flask import Flask
from flask_socketio import SocketIO
from flasgger import Swagger
from app.api import api
from app.socket_events import register_socket_events
import os
import sys

app = Flask(__name__)

app.config['SWAGGER'] = {
    'title': 'Intelligent Museum API',
    'uiversion': 3,
    'openapi': '3.0.0',
}
Swagger(app)

# Initialize SocketIO with CORS support
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Register the REST API blueprint
app.register_blueprint(api, url_prefix='/api')

# Register WebSocket event handlers
register_socket_events(socketio)

# development mode and production mode
debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'

@app.route("/")
def index():
    return "Hello World!"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5050))
    print(f" * Running on http://0.0.0.0:{port}  (async_mode=gevent, debug={debug_mode})", flush=True)
    print(f" * Press CTRL+C to quit", flush=True)
    # 0.0.0.0 make flask use all available network interfaces
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)