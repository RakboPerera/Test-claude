import os
import json
from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
import anthropic

app = Flask(__name__, static_folder="static")

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# In-memory store: session_id -> list of file_ids
uploaded_files: dict[str, list[dict]] = {}


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    """Upload a file to the Anthropic Files API and return its file_id."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    session_id = request.form.get("session_id", "default")

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename
    mime_type = file.content_type or "application/octet-stream"

    # Determine content type for the API
    supported_doc_types = [
        "application/pdf",
        "text/plain",
        "text/html",
        "text/csv",
        "text/xml",
        "application/xml",
        "text/markdown",
    ]
    supported_image_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]

    if mime_type not in supported_doc_types + supported_image_types:
        # Try to infer from filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        ext_map = {
            "pdf": "application/pdf",
            "txt": "text/plain",
            "md": "text/markdown",
            "html": "text/html",
            "csv": "text/csv",
            "xml": "text/xml",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        mime_type = ext_map.get(ext, "text/plain")

    try:
        uploaded = client.beta.files.upload(
            file=(filename, file.read(), mime_type),
        )

        if session_id not in uploaded_files:
            uploaded_files[session_id] = []

        file_info = {
            "file_id": uploaded.id,
            "filename": filename,
            "mime_type": mime_type,
        }
        uploaded_files[session_id].append(file_info)

        return jsonify({
            "file_id": uploaded.id,
            "filename": filename,
            "mime_type": mime_type,
        })
    except Exception as e:
        print(f"UPLOAD ERROR: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/files/<session_id>", methods=["GET"])
def list_files(session_id):
    """List uploaded files for a session."""
    files = uploaded_files.get(session_id, [])
    return jsonify({"files": files})


@app.route("/files/<session_id>/<file_id>", methods=["DELETE"])
def delete_file(session_id, file_id):
    """Delete a file from the Anthropic Files API and from session."""
    try:
        client.beta.files.delete(file_id)
        if session_id in uploaded_files:
            uploaded_files[session_id] = [
                f for f in uploaded_files[session_id] if f["file_id"] != file_id
            ]
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chat", methods=["POST"])
def chat():
    """Send a chat message, optionally referencing uploaded files."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    messages_history = data.get("messages", [])
    session_id = data.get("session_id", "default")
    selected_file_ids = data.get("file_ids", [])  # specific file IDs to include

    if not messages_history:
        return jsonify({"error": "No messages provided"}), 400

    # Build the message list for the API
    api_messages = []

    # Get the last user message and attach files to it
    last_user_msg = None
    history_without_last = []

    for i, msg in enumerate(messages_history):
        if i == len(messages_history) - 1 and msg["role"] == "user":
            last_user_msg = msg["content"]
        else:
            api_messages.append(msg)

    if last_user_msg is None:
        return jsonify({"error": "Last message must be from user"}), 400

    # Build content array for the last user message
    content = []

    # Attach selected files (or all session files if none specified)
    session_files = uploaded_files.get(session_id, [])
    files_to_include = []

    if selected_file_ids:
        files_to_include = [f for f in session_files if f["file_id"] in selected_file_ids]
    else:
        files_to_include = session_files

    for file_info in files_to_include:
        mime = file_info["mime_type"]
        file_id = file_info["file_id"]
        filename = file_info["filename"]

        if mime.startswith("image/"):
            content.append({
                "type": "image",
                "source": {"type": "file", "file_id": file_id},
            })
        else:
            content.append({
                "type": "document",
                "source": {"type": "file", "file_id": file_id},
                "title": filename,
                "citations": {"enabled": True},
            })

    content.append({"type": "text", "text": last_user_msg})
    api_messages.append({"role": "user", "content": content})

    def generate():
        try:
            with client.beta.messages.stream(
                model="claude-opus-4-6",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=(
                    "You are a helpful assistant. When files are provided, analyze them "
                    "thoroughly and answer questions about their content. Cite specific "
                    "parts of the documents when relevant."
                ),
                messages=api_messages,
                betas=["files-api-2025-04-14"],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
                yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
