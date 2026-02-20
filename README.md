# File Chat — Claude-powered chatbot with file uploads

A web-based chatbot that lets you upload files and chat over them using Claude and the Anthropic Files API.

## Features

- Upload PDFs, text files, Markdown, CSV, HTML, images (JPEG/PNG/GIF/WebP)
- Files are stored via the Anthropic Files API — no re-upload on each message
- Select which uploaded files to include per conversation
- Streaming responses from Claude Opus 4.6
- Clean dark-mode UI

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_api_key_here
python app.py
```

Then open [http://localhost:5000](http://localhost:5000) in your browser.

## Usage

1. Drag-and-drop or click to upload files in the left sidebar
2. Click a file to select/deselect it — selected files are sent with each message
3. Type your question in the chat box and press Enter
