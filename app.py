from flask import Flask, request, jsonify
import requests
import gzip
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Airtable configuration - set as environment variables in Render
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = os.environ.get('AIRTABLE_TABLE_NAME')

def gzip_file(input_path, output_path):
    with open(input_path, 'rb') as f_in:
        with gzip.open(output_path, 'wb') as f_out:
            f_out.writelines(f_in)

def upload_to_transfersh(file_path):
    with open(file_path, 'rb') as f:
        response = requests.put(
            f'https://transfer.sh/{os.path.basename(file_path)}',
            data=f
        )
        if response.status_code == 200:
            return response.text.strip()
        else:
            print("Transfer.sh upload failed:", response.text)
            return None

def update_airtable_record(record_id, download_url):
    headers = {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        "fields": {
            "G-Zipped File": [
                {
                    "url": download_url
                }
            ]
        }
    }
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}/{record_id}"
    response = requests.patch(url, json=data, headers=headers)
    return response.status_code, response.json()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    file_url = data.get('file_url')
    record_id = data.get('record_id')

    # Validate inputs and env vars
    missing = []
    if not file_url:
        missing.append("file_url (from Airtable POST body)")
    if not record_id:
        missing.append("record_id (from Airtable POST body)")
    if not AIRTABLE_API_KEY:
        missing.append("AIRTABLE_API_KEY (env)")
    if not AIRTABLE_BASE_ID:
        missing.append("AIRTABLE_BASE_ID (env)")
    if not AIRTABLE_TABLE_NAME:
        missing.append("AIRTABLE_TABLE_NAME (env)")

    if missing:
        return jsonify({
            "error": "Missing required parameters or environment variables",
            "missing_items": missing,
            "debug_values": {
                "file_url": file_url,
                "record_id": record_id,
                "AIRTABLE_API_KEY_present": AIRTABLE_API_KEY is not None,
                "AIRTABLE_BASE_ID_present": AIRTABLE_BASE_ID is not None,
                "AIRTABLE_TABLE_NAME_present": AIRTABLE_TABLE_NAME is not None,
            }
        }), 400

    try:
        # Download the file
        original_filename = secure_filename(file_url.split("/")[-1])
        local_pdf = f"/tmp/{original_filename}"
        response = requests.get(file_url)
        response.raise_for_status()

        with open(local_pdf, 'wb') as f:
            f.write(response.content)

        # Gzip the file
        local_gz = f"{local_pdf}.gz"
        gzip_file(local_pdf, local_gz)

        # Upload to transfer.sh
        gz_url = upload_to_transfersh(local_gz)
        if not gz_url:
            return jsonify({"error": "Failed to upload to transfer.sh"}), 500

        # Update Airtable with the new link
        status, airtable_response = update_airtable_record(record_id, gz_url)

        return jsonify({
            "status": "success",
            "gz_url": gz_url,
            "airtable_response": airtable_response
        }), status

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "gzip webhook is running"})
