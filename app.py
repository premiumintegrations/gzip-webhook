from flask import Flask, request, jsonify
import requests
import gzip
from io import BytesIO
import os

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def gzip_and_upload_to_airtable():
    data = request.get_json()
    file_url = data.get('file_url')
    record_id = data.get('record_id')

    # Get Airtable config from environment
    airtable_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME")
    airtable_field = "G-Zipped File"

    if not all([file_url, record_id, airtable_key, base_id, table_name]):
        return jsonify({'error': 'Missing required parameters or env variables'}), 400

    try:
        # Step 1: Download the original file
        response = requests.get(file_url)
        response.raise_for_status()
        original_data = response.content

        # Step 2: Gzip the file
        gzipped_io = BytesIO()
        with gzip.GzipFile(fileobj=gzipped_io, mode='wb') as gz:
            gz.write(original_data)
        gzipped_io.seek(0)

        # Step 3: Upload to file.io (anonymous)
        upload_response = requests.post(
            'https://api.file.io/v2/files',
            files={'file': ('document.pdf.gz', gzipped_io)},
            data={
                'expires': '1d'  # Expires in 1 day or after 1 download
            }
        )

        upload_json = upload_response.json()
        if not upload_json.get('data') or not upload_json['data'].get('link'):
            return jsonify({'error': 'Failed to upload to file.io', 'details': upload_json}), 500

        public_url = upload_json['data']['link']

        # Step 4: PATCH Airtable record with the .gz file link
        airtable_api_url = f'https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}'
        headers = {
            'Authorization': f'Bearer {airtable_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            "fields": {
                airtable_field: [{"url": public_url}]
            }
        }

        airtable_response = requests.patch(airtable_api_url, headers=headers, json=payload)
        airtable_response.raise_for_status()

        return jsonify({
            'message': 'Gzipped file uploaded and Airtable updated',
            'gzipped_url': public_url,
            'record_id': record_id
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
