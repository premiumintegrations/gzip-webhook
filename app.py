from flask import Flask, request, jsonify
import requests
import gzip
from io import BytesIO
import os

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def gzip_and_forward():
    data = request.get_json()
    pdf_url = data.get('file_url')
    api_url = data.get('api_url') or os.environ.get("EXTERNAL_API_URL")

    if not pdf_url or not api_url:
        return jsonify({'error': 'Missing file_url or api_url'}), 400

    try:
        # Download the PDF
        response = requests.get(pdf_url)
        response.raise_for_status()
        pdf_data = response.content

        # Gzip it
        gzipped = BytesIO()
        with gzip.GzipFile(fileobj=gzipped, mode='wb') as f:
            f.write(pdf_data)
        gzipped.seek(0)

        # Send to external API
        headers = {
            'Content-Encoding': 'gzip',
            'Content-Type': 'application/pdf',
        }

        api_response = requests.post(api_url, data=gzipped, headers=headers)

        return jsonify({
            'message': "File processed successfully",
            'status': api_response.status_code,
            'sent_to': api_url
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    return '✅ Gzip webhook is running!'
