"""
Web routes for ChitUI
"""
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, Response, send_from_directory, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import time
import json
import uuid
import requests
from threading import Thread
from loguru import logger
from app import printers, upload_progress
from app.printer_manager import get_printer_files, upload_file_to_printer, set_camera_status
from app.utils import is_allowed_file, get_config

# Create blueprint - THIS VARIABLE NAME MUST MATCH THE IMPORT IN __init__.py
routes_bp = Blueprint('routes', __name__)


@routes_bp.route('/')
@login_required
def index():
    """Render the main application page."""
    return render_template('index.html', 
                           user=current_user, 
                           is_admin=current_user.is_admin())


@routes_bp.route('/admin')
@login_required
def admin():
    """Render the admin page."""
    if not current_user.is_admin():
        return redirect(url_for('routes.index'))
    
    return render_template('admin.html', user=current_user)


@routes_bp.route('/progress')
@login_required
def progress():
    """Stream upload progress as a server-sent event."""
    def publish_progress():
        last_progress = {}
        while True:
            for task_id, task in list(upload_progress.items()):
                # Only send updates when progress changes or for new tasks
                if task_id not in last_progress or last_progress[task_id] != task['progress']:
                    last_progress[task_id] = task['progress']
                    yield f"data:{json.dumps(task)}\n\n"
            
            # Remove completed tasks after a while
            current_time = time.time()
            for task_id in list(upload_progress.keys()):
                task = upload_progress[task_id]
                if task['status'] in ['complete', 'error'] and current_time - task['updated_at'] > 60:
                    del upload_progress[task_id]
                    if task_id in last_progress:
                        del last_progress[task_id]
            
            time.sleep(1)
    
    return Response(publish_progress(), mimetype="text/event-stream")


@routes_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """Handle file upload to a printer."""
    if 'file' not in request.files:
        logger.error("No 'file' parameter in request.")
        return jsonify({"success": False, "error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        logger.error("No file selected to be uploaded.")
        return jsonify({"success": False, "error": "No file selected"}), 400
    
    printer_id = request.form.get('printer')
    if not printer_id or printer_id not in printers:
        logger.error(f"Invalid printer ID: {printer_id}")
        return jsonify({"success": False, "error": "Invalid printer ID"}), 400
    
    if not is_allowed_file(file.filename):
        logger.error(f"Invalid file type: {file.filename}")
        return jsonify({"success": False, "error": "Invalid file type"}), 400
    
    # Save file temporarily
    filename = secure_filename(file.filename)
    
    # Get upload folder from config
    config = get_config()
    upload_folder = config.get('upload_folder', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    
    filepath = os.path.join(upload_folder, filename)
    try:
        file.save(filepath)
        
        # Check if file was saved successfully
        if not os.path.exists(filepath):
            logger.error(f"Failed to save file: {filepath}")
            return jsonify({"success": False, "error": "Failed to save file"}), 500
            
        # Check file size
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            logger.error(f"File is empty: {filepath}")
            os.remove(filepath)
            return jsonify({"success": False, "error": "File is empty"}), 400
            
        logger.info(f"File saved successfully: {filepath} ({file_size} bytes)")
        
        # Start upload in background thread
        task_id = str(uuid.uuid4())
        upload_progress[task_id] = {
            'id': task_id,
            'filename': filename,
            'printer_id': printer_id,
            'printer_name': printers[printer_id]['name'],
            'status': 'starting',
            'progress': 0,
            'created_at': time.time(),
            'updated_at': time.time()
        }
        
        Thread(target=upload_file_to_printer, args=(task_id, printer_id, filepath), daemon=True).start()
        
        return jsonify({
            "success": True, 
            "message": "Upload started", 
            "task_id": task_id,
            "file_size": file_size
        })
        
    except Exception as e:
        logger.error(f"Error during file upload: {e}")
        # Clean up partial file if it exists
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
        return jsonify({"success": False, "error": f"Upload error: {str(e)}"}), 500


@routes_bp.route('/camera/<printer_id>/stream')
@login_required
def camera_stream(printer_id):
    """Proxy the camera stream from the printer."""
    if printer_id not in printers:
        logger.error(f"Invalid printer ID for camera stream: {printer_id}")
        abort(404)
    
    printer = printers[printer_id]
    
    # Check if printer supports camera
    if not printer.get('supports_camera', False):
        logger.error(f"Printer {printer_id} does not support camera")
        abort(404)
    
    # Enable camera if it's off
    if not printer.get('camera_status', False):
        set_camera_status(printer_id, True)
    
    # Get camera config
    camera_config = printer.get('camera_config', {})
    camera_url = camera_config.get('camera_url', '/camera/stream')
    
    # Proxy the request to the printer
    try:
        stream_url = f"http://{printer['ip']}:3030{camera_url}"
        response = requests.get(stream_url, stream=True, timeout=2)
        
        if response.status_code != 200:
            logger.error(f"Failed to get camera stream from printer {printer_id}: {response.status_code}")
            abort(response.status_code)
        
        # Forward the content type
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        
        # Stream the response
        def generate():
            for chunk in response.iter_content(chunk_size=1024):
                yield chunk
        
        return Response(generate(), content_type=content_type)
        
    except Exception as e:
        logger.error(f"Error proxying camera stream for printer {printer_id}: {e}")
        abort(500)


@routes_bp.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory('../static', filename)