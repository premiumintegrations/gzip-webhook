from flask import Flask, request, jsonify
import requests
import gzip
from io import BytesIO
import os

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    """Simple endpoint to confirm the service is live."""
    return jsonify({"status": "ok", "message": "gzip webhook is running"}), 200


@app.route('/webhook', methods=['POST'])
def gzip_and_upload_to_airtable():
    """Main webhook: receives file_url and record_id from Airtable, gzips file, uploads to file.io, and updates Airtable."""
    data = request.get_json() or {}

    # --- Extract incoming values from request ---
    file_url = data.get('file_url')
    record_id = data.get('record_id')

    # --- Load Airtable environment variables ---
    airtable_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME")

    # The Airtable field where gzipped file will be stored
    airtable_field = "G-Zipped File"

    # --- Validate and show debug info if something is missing ---
    missing = []
    if not file_url:
        missing.append("file_url (from Airtable POST body)")
    if not record_id:
        missing.append("record_id (from Airtable POST body)")
    if not airtable_key:
        missing.append("AIRTABLE_API_KEY (from Render environment)")
    if not base_id:
        missing.append("AIRTABLE_BASE_ID (from Render environment)")
    if not table_name:
        missing.append("AIRTABLE_TABLE_NAME (from Render environment)")

    if missing:
        # Return helpful diagnostics
        return jsonify({
            "error": "Missing required parameters or environment variables",
            "missing_items": missing,
            "debug_values": {
                "file_url": file_url,
                "record_id": record_id,
                "AIRTABLE_API_KEY_present": bool(airtable_key),
                "AIRTABLE_BASE_ID_present": bool(base_id),
                "AIRTABLE_TABLE_NAME_present": bool(table_name)
            }
        }), 400

    try:
        # --- Step 1: Download the original file ---
        response = requests.get(file_url)
        response.raise_for_status()
        original_data = response.content

        # --- Step 2: Gzip the file ---
        gzipped_io = BytesIO()
        with gzip.GzipFile(fileobj=gzipped_io, mode='wb') as gz:
            gz.write(original_data)
        gzipped_io.seek(0)

        # --- Step 3: Upload to file.io anonymously ---
        upload_response = requests.post(
            'https://api.file.io/v2/files',
            files={'file': ('document.pdf.gz', gzipped_io)},
            data={'expires': '1d'}  # file expires after 1 day or 1 download
        )

        upload_json = upload_response.json()
        if not upload_json.get('data') or not upload_json['data'].get('link'):
            return jsonify({
                'error': 'Failed to upload to file.io',
                'details': upload_json
            }), 500

        public_url = upload_json['data']['link']

        # --- Step 4: Update Airtable record with the new file link ---
        airtable_api_url = f"https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}"
        headers = {
            "Authorization": f"Bearer {airtable_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "fields": {
                airtable_field: [{"url": public_url}]
            }
        }

        airtable_response = requests.patch(airtable_api_url, headers=headers, json=payload)
        airtable_response.raise_for_status()

        # --- Step 5: Return success response ---
        return jsonify({
            "message": "Gzipped file uploaded and Airtable updated successfully",
            "gzipped_url": public_url,
            "record_id": record_id
        }), 200

    except Exception as e:
        # Catch-all error handler
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Flask debug server (for local testing)
    app.run(host="0.0.0.0", port=5000, debug=True)
