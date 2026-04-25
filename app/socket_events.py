"""
WebSocket event handlers for group chat.

Registers SocketIO events: join_room, leave_room, send_message,
get_history, and disconnect.
"""
from flask_socketio import join_room, leave_room, emit
from app.services.session_service import SessionManager
from app.services.translate_service import Translate
from rag.llama_index import LLaMAIndexRAG

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Configure handler to output logs to stdout
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Load roles configuration
with open('npc_role_config.json', 'r') as f:
    roles_config = json.load(f)


def register_socket_events(socketio):
    """Register all SocketIO event handlers on the given socketio instance."""

    session_mgr = SessionManager()

    @socketio.on('connect')
    def handle_connect():
        logger.info(f"Client connected: {_sid()}")
        emit('connected', {'message': 'Connected to group chat server'})

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = _sid()
        room_id, user_name = session_mgr.leave_room(sid)
        if room_id:
            leave_room(room_id)
            emit('system_message', {
                'message': f'{user_name} 已離開聊天室',
                'users': session_mgr.get_room_users(room_id),
            }, to=room_id)
            logger.info(f"{user_name} disconnected from room {room_id}")

    @socketio.on('join')
    def handle_join(data):
        """
        Join or create a room.
        
        Expected data:
        {
            "room_id": "abc123",          # optional — auto-generated if missing
            "user_name": "Alice",         # required
            "npc_role": "白起",            # optional, default "博物館導覽員"
            "lang": "zh-TW",             # optional, default "zh-TW"
            "personality": "extrovert",   # optional, default ""
            "is_rag": true               # optional, default true
        }
        """
        sid = _sid()
        user_name = data.get('user_name', f'user_{sid[:6]}')
        room_id = data.get('room_id', None)
        npc_role = data.get('npc_role', '博物館導覽員')
        lang = data.get('lang', 'zh-TW')
        personality = data.get('personality', '')
        is_rag = data.get('is_rag', True)

        # Create room if it doesn't exist
        room_id = session_mgr.create_room(
            room_id=room_id,
            npc_role=npc_role,
            lang=lang,
            personality=personality,
            is_rag=is_rag,
        )

        # Join the room
        success = session_mgr.join_room(sid, room_id, user_name)
        if not success:
            emit('error', {'message': f'無法加入聊天室 {room_id}'})
            return

        join_room(room_id)

        # Notify all users in the room
        room = session_mgr.get_room(room_id)
        emit('system_message', {
            'message': f'{user_name} 加入了聊天室',
            'users': session_mgr.get_room_users(room_id),
            'room_id': room_id,
            'npc_role': room['npc_role'],
        }, to=room_id)

        # Send room info back to the joiner
        emit('room_joined', {
            'room_id': room_id,
            'npc_role': room['npc_role'],
            'lang': room['lang'],
            'users': session_mgr.get_room_users(room_id),
            'history': session_mgr.get_history(room_id),
        })

        logger.info(f"{user_name} joined room {room_id}")

    @socketio.on('leave')
    def handle_leave():
        """Leave the current room."""
        sid = _sid()
        room_id, user_name = session_mgr.leave_room(sid)
        if room_id:
            leave_room(room_id)
            emit('system_message', {
                'message': f'{user_name} 離開了聊天室',
                'users': session_mgr.get_room_users(room_id),
            }, to=room_id)
            emit('room_left', {'room_id': room_id})
            logger.info(f"{user_name} left room {room_id}")

    @socketio.on('send_chat_message')
    def handle_send_chat_message(data):
        """
        Send a message to the group. Triggers NPC response.
        
        Expected data:
        {
            "message": "這把劍是什麼朝代的？",   # required
            "lang": "zh-TW"                    # optional override
        }
        """
        from flask import request
        sid = request.sid
        user_info = session_mgr.get_user(sid)
        if user_info is None:
            emit('error', {'message': '你尚未加入任何聊天室'})
            return

        room_id = user_info['room_id']
        user_name = user_info['user_name']
        message = data.get('message', '').strip()

        if not message:
            emit('error', {'message': '訊息不可為空'})
            return

        room = session_mgr.get_room(room_id)
        if room is None:
            emit('error', {'message': '聊天室不存在'})
            return

        lang = data.get('lang', room['lang'])

        # 1. Broadcast user message to all in the room
        session_mgr.append_message(room_id, 'user', user_name, message, lang)
        emit('user_message', {
            'user_name': user_name,
            'message': message,
            'lang': lang,
        }, to=room_id)

        # 2. Generate NPC response with conversation history
        npc_role = room['npc_role']
        personality = room['personality']
        is_rag = room['is_rag']

        # Translate to Chinese if needed
        translator = Translate()
        chi_query = translator.translate(message, "zh-TW")

        lang_chinese_name = translator.get_language_name_in_chinese(lang)
        if lang_chinese_name is None:
            lang_chinese_name = "中文"

        # Get role features
        role_features = roles_config.get(npc_role, {})
        tone = role_features.get("tone", "中立")
        style = role_features.get("style", "正常")
        background = role_features.get("background", "")
        dynasty = role_features.get("dynasty", "現代")
        game_prompt = role_features.get("game_prompt", None)

        # Prepend NPC info for better retrieval
        chi_query_with_context = f"({npc_role}-{dynasty}){chi_query}"

        # Get conversation history for prompt
        conversation_history = session_mgr.format_history_for_prompt(room_id, last_n=20)

        query_info = {
            'query': chi_query_with_context,
            'target_lang_code': lang,
            'target_lang': lang_chinese_name,
            'role': npc_role,
            'dynasty': dynasty,
            'background': background,
            'tone': tone,
            'style': style,
            'personality': personality,
            'is_rag': is_rag,
            'conversation_history': conversation_history,
            'game_prompt': game_prompt,
        }

        # 3. Call RAG to generate NPC response
        try:
            emit('npc_typing', {'npc_role': npc_role}, to=room_id)

            rag = LLaMAIndexRAG()
            response = rag.generate_group_response(query_info)

            if is_rag:
                response_text = response.response
                metadata = response.metadata
            else:
                response_text = response["response"]
                metadata = response["metadata"]

            # 4. Append NPC response to history and broadcast
            session_mgr.append_message(room_id, 'npc', npc_role, response_text, lang)
            emit('npc_response', {
                'npc_role': npc_role,
                'response': response_text,
                'metadata': metadata,
            }, to=room_id)

        except Exception as e:
            logger.error(f"Error generating NPC response: {e}")
            emit('error', {
                'message': f'NPC 回應產生錯誤: {str(e)}'
            })

    @socketio.on('get_history')
    def handle_get_history(data=None):
        """Return conversation history for the current room."""
        from flask import request
        sid = request.sid
        user_info = session_mgr.get_user(sid)
        if user_info is None:
            emit('error', {'message': '你尚未加入任何聊天室'})
            return

        room_id = user_info['room_id']
        last_n = (data or {}).get('last_n', 50)
        history = session_mgr.get_history(room_id, last_n)
        emit('chat_history', {'history': history, 'room_id': room_id})


def _sid():
    """Get the current socket ID."""
    from flask import request
    return request.sid
