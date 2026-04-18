from flask import Blueprint, request, jsonify
from rag.llama_index import LLaMAIndexRAG

from app.services.translate_service import Translate

import json
import time

api = Blueprint('api', __name__)

# Load roles configuration from JSON file
with open('npc_role_config.json', 'r') as f:
    roles_config = json.load(f)

# ─── Room Management REST Endpoints ───────────────────────────────

from app.services.session_service import SessionManager

@api.route('/rooms', methods=['GET'])
def list_rooms():
    """
    List all active chat rooms.
    ---
    tags:
      - Rooms
    responses:
      200:
        description: A list of active room IDs.
        content:
          application/json:
            schema:
              type: object
              properties:
                rooms:
                  type: array
                  items:
                    type: string
    """
    session_mgr = SessionManager()
    rooms = session_mgr.list_rooms()
    return jsonify({'rooms': rooms})

@api.route('/rooms/<room_id>', methods=['GET'])
def get_room(room_id):
    """
    Get info for a specific room.
    ---
    tags:
      - Rooms
    parameters:
      - in: path
        name: room_id
        required: true
        schema:
          type: string
    responses:
      200:
        description: Room details.
        content:
          application/json:
            schema:
              type: object
              properties:
                room_id:
                  type: string
                npc_role:
                  type: string
                lang:
                  type: string
                users:
                  type: array
                  items:
                    type: string
                message_count:
                  type: integer
                created_at:
                  type: string
      404:
        description: Room not found.
    """
    session_mgr = SessionManager()
    room = session_mgr.get_room(room_id)
    if room is None:
        return jsonify({'error': f'Room {room_id} not found'}), 404
    return jsonify({
        'room_id': room_id,
        'npc_role': room['npc_role'],
        'lang': room['lang'],
        'users': list(room['users'].values()),
        'message_count': len(room['history']),
        'created_at': room['created_at'],
    })

# AI助理
@api.route('/generate', methods=['POST'])
def generate():
    """
    Generate a response using the RAG model (museum guide role).
    ---
    tags:
      - AI
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - query
            properties:
              query:
                type: string
                example: 這把劍是哪個朝代的？
              lang:
                type: string
                default: en
                example: zh-TW
              personality:
                type: string
                example: friendly
    responses:
      200:
        description: Generated response.
        content:
          application/json:
            schema:
              type: object
              properties:
                parsed_query:
                  type: string
                response:
                  type: string
                metadata:
                  type: object
                RAG_response_time:
                  type: number
    """
    data = request.json
    query = data.get('query', '')
    lang = data.get('lang', 'en')
    personality = data.get("personality", "")

    if query.strip() == '':
        return jsonify({
            'error': 'Query field is required'
        })
    
    ########## Detect and Translate ##########
    # Translate to Chinese and plug in target language to the prompt
    translator = Translate()
    chi_query = translator.translate(query, "zh-TW")

    lang_chinese_name = translator.get_language_name_in_chinese(lang)
    if lang_chinese_name is None:
        return jsonify({
            'error': 'Error in your language code. Please use a valid language code.'
        })
    # chi_query += f"。請用{lang_chinese_name}回答"

    # 預設AI助理使用博物館導覽員
    role = '博物館導覽員'
    role_features = roles_config.get(role, {})
    tone = role_features.get("tone", "中立")
    style = role_features.get("style", "正常")
    background = role_features.get("background", "")
    dynasty = role_features.get("dynasty", "現代")

    query_info = {
        'query': chi_query,
        'target_lang_code': lang,
        'target_lang': lang_chinese_name,
        'role': role,
        'dynasty': dynasty,
        'background': background,
        'tone': tone,
        'style': style,
        'personality': personality,
        'is_rag': True  # Default to RAG
    }

    ########## LLaMA Index RAG ##########
    # Start timing before the API call
    start_time = time.time()

    rag = LLaMAIndexRAG()
    response = rag.generate_response_with_retrieval(query_info)
    response_text, metadata = response.response, response.metadata

    # End timing after the API call
    end_time = time.time()
    total_time = end_time - start_time

    # Google translate doesn't work well for specific terms
    # translator = Translate()
    # response_text = translator.translate(response_text, lang)

    return jsonify({
        'parsed_query': chi_query,
        'response': response_text,
        'metadata': metadata,
        'RAG_response_time': total_time
    })

@api.route('/npc/ask', methods=['POST'])
def npc_ask():
    """
    Ask an NPC a question using the RAG model.
    ---
    tags:
      - AI
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - query
            properties:
              query:
                type: string
                example: 你是誰？
              lang:
                type: string
                default: en
                example: zh-TW
              npc_role:
                type: string
                default: 博物館導覽員
                example: 白起
              personality:
                type: string
                example: serious
              is_rag:
                type: boolean
                default: true
    responses:
      200:
        description: NPC response.
        content:
          application/json:
            schema:
              type: object
              properties:
                parsed_query:
                  type: string
                response:
                  type: string
                metadata:
                  type: object
                RAG_response_time:
                  type: number
    """
    data = request.json
    query = data.get('query', '')
    lang = data.get('lang', 'en')
    npc_role = data.get('npc_role', '博物館導覽員')
    personality = data.get("personality", "")
    is_rag = data.get("is_rag", True)

    # Translate to Chinese and plug in target language to the prompt
    translator = Translate()
    chi_query = translator.translate(query, "zh-TW")

    lang_chinese_name = translator.get_language_name_in_chinese(lang)
    if lang_chinese_name is None:
        return jsonify({
            'error': 'Error in your language code. Please use a valid language code.'
        })
    # chi_query += f"。請用'{lang_chinese_name}'回答"

    # Get the role features
    role_features = roles_config.get(npc_role, {})
    tone = role_features.get("tone", "中立")
    style = role_features.get("style", "正常")
    background = role_features.get("background", "")
    dynasty = role_features.get("dynasty", "現代")
    
    # Apply the role features to the query
    # 讓NPC query內多加一點NPC的資訊，這樣retrive document會更準確（和prompt template無關）
    # 這邊的資訊要和document相關，例如朝代
    chi_query = f"({npc_role}-{dynasty})"+chi_query

    query_info = {
        'query': chi_query,
        'target_lang_code': lang,
        'target_lang': lang_chinese_name,
        'role': npc_role,
        'dynasty': dynasty,
        'background': background,
        'tone': tone,
        'style': style,
        'personality': personality,
        "is_rag": is_rag
    }


    # Start timing before the API call
    start_time = time.time()

    rag = LLaMAIndexRAG()
    response = rag.generate_response_with_retrieval(query_info)

    if is_rag:
        response_text, metadata = response.response, response.metadata
    else:
        response_text, metadata = response["response"], response["metadata"]

    # End timing after the API call
    end_time = time.time()
    total_time = end_time - start_time


    return jsonify({
        'parsed_query': chi_query,
        'response': response_text,
        'metadata': metadata,
        'RAG_response_time': total_time
    })


@api.route('/translate', methods=['POST'])
def translate():
    """
    Translate text to a target language.
    ---
    tags:
      - Utilities
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - text
            properties:
              text:
                type: string
                example: Hello, how are you?
              target_language:
                type: string
                default: en
                example: zh-TW
    responses:
      200:
        description: Translated text.
    """
    data = request.json
    text = data.get('text', '')
    target_language = data.get('target_language', 'en')

    # Set up translator
    translator = Translate()
    response = translator.translate(text, target_language)

    return jsonify(response)

########## ARCHIVED ##########
########## LangChain RAG ##########
# # Set up vector store
# loader = DirectoryLoader(path="assets", glob="./*.txt", loader_cls=TextLoader) 
# text_splitter = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=20)

# model_name = "sentence-transformers/all-MiniLM-L6-v2"
# model_kwargs = {'device': 'cpu'}
# embedding = HuggingFaceEmbeddings(
#     model_name=model_name, 
#     model_kwargs=model_kwargs
# )

# persist_directory = 'chroma'

# store = VectorDB(loader, text_splitter, embedding, persist_directory)
# # vectordb = store.init_vectordb()
# vectordb = store.get_vectordb_from_disk()

# # Generate response
# rag = LangChainRAG(vectordb)
# response = rag.generate_response_with_retrieval(query)

# response = {
#     "query": response["query"],
#     "result": response["result"],
#     "source_documents": [doc.metadata["source"] for doc in response["source_documents"]],
#     "source_content": [doc.page_content for doc in response["source_documents"]]
# }