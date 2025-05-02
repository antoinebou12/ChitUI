"""
REST API endpoints for ChitUI
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from loguru import logger
import json
from app import printers, upload_progress
from app.printer_manager import (
    debug_printer_connection, discover_printers, add_printer_manually, connect_printer,
    get_printer_status, get_printer_attributes, get_printer_files,
    start_print, pause_print, resume_print, stop_print, delete_file,
    set_camera_status, rename_printer
)

# Create blueprint
api_bp = Blueprint('api', __name__)


@api_bp.route('/swagger.json')
def swagger_json():
    """Serve Swagger specification JSON."""
    return jsonify({
        "swagger": "2.0",
        "info": {
            "title": "ChitUI API",
            "description": "API for controlling 3D printers with ChitUI",
            "version": "1.0.0"
        },
        "basePath": "/api",
        "schemes": ["http", "https"],
        "consumes": ["application/json"],
        "produces": ["application/json"],
        "paths": {
            "/printer/list": {
                "get": {
                    "summary": "Get list of printers",
                    "description": "Returns all connected printers",
                    "responses": {
                        "200": {
                            "description": "List of printers"
                        }
                    }
                }
            },
            "/printer/discover": {
                "post": {
                    "summary": "Discover printers",
                    "description": "Initiate printer discovery on the network",
                    "responses": {
                        "200": {
                            "description": "Discovery initiated"
                        }
                    }
                }
            },
            "/printer/{id}": {
                "get": {
                    "summary": "Get printer details",
                    "description": "Returns details for a specific printer",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Printer details"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/printer/add": {
                "post": {
                    "summary": "Add printer manually",
                    "description": "Add a printer by IP address",
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "Printer name"
                                    },
                                    "ip": {
                                        "type": "string",
                                        "description": "Printer IP address"
                                    },
                                    "model": {
                                        "type": "string",
                                        "description": "Printer model (optional)"
                                    },
                                    "brand": {
                                        "type": "string",
                                        "description": "Printer brand (optional)"
                                    }
                                },
                                "required": ["name", "ip"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Printer added successfully"
                        },
                        "400": {
                            "description": "Invalid request"
                        },
                        "500": {
                            "description": "Failed to add printer"
                        }
                    }
                }
            },
            "/printer/{id}/files": {
                "get": {
                    "summary": "Get printer files",
                    "description": "Returns list of files on the printer",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        },
                        {
                            "name": "path",
                            "in": "query",
                            "required": False,
                            "type": "string",
                            "description": "File path (default: /local)"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of files"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/printer/{id}/print": {
                "post": {
                    "summary": "Start print",
                    "description": "Start printing a file",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        },
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "filename": {
                                        "type": "string",
                                        "description": "File to print"
                                    }
                                },
                                "required": ["filename"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Print started"
                        },
                        "404": {
                            "description": "Printer or file not found"
                        }
                    }
                }
            },
            "/printer/{id}/pause": {
                "post": {
                    "summary": "Pause print",
                    "description": "Pause the current print job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Print paused"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/printer/{id}/resume": {
                "post": {
                    "summary": "Resume print",
                    "description": "Resume a paused print job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Print resumed"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/printer/{id}/stop": {
                "post": {
                    "summary": "Stop print",
                    "description": "Stop the current print job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Print stopped"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/printer/{id}/camera": {
                "post": {
                    "summary": "Control camera",
                    "description": "Enable or disable the printer camera",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "type": "string",
                            "description": "Printer ID"
                        },
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "enable": {
                                        "type": "boolean",
                                        "description": "Enable or disable camera"
                                    }
                                },
                                "required": ["enable"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Camera status updated"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/uploads": {
                "get": {
                    "summary": "Get upload tasks",
                    "description": "List all upload tasks",
                    "responses": {
                        "200": {
                            "description": "List of upload tasks"
                        }
                    }
                }
            }
        }
    })


@api_bp.route('/printer/list')
@login_required
def list_printers():
    """List all printers."""
    return jsonify(printers)


@api_bp.route('/printer/discover', methods=['POST'])
@login_required
def discover():
    """Initiate printer discovery."""
    from app.socket_handlers import discovery_task
    from threading import Thread
    
    # Start discovery in a background thread
    Thread(target=discovery_task, daemon=True).start()
    
    return jsonify({
        "success": True,
        "message": "Discovery initiated"
    })


@api_bp.route('/printer/<printer_id>')
@login_required
def get_printer(printer_id):
    """Get printer details."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    return jsonify(printers[printer_id])


@api_bp.route('/printer/add', methods=['POST'])
@login_required
def add_printer():
    """Add a printer manually."""
    data = request.json
    
    if not data:
        return jsonify({"success": False, "error": "Invalid request"}), 400
    
    name = data.get('name')
    ip = data.get('ip')
    model = data.get('model', 'unknown')
    brand = data.get('brand', 'unknown')
    
    if not name or not ip:
        return jsonify({"success": False, "error": "Name and IP address are required"}), 400
    
    # Validate IP address format
    if not validate_ip(ip):
        return jsonify({"success": False, "error": "Invalid IP address format"}), 400
    
    # Add printer
    printer = add_printer_manually(name, ip, model, brand)
    
    if printer:
        logger.info(f"Printer added manually: {name} ({ip})")
        return jsonify({
            "success": True,
            "message": f"Printer {name} added successfully",
            "printer_id": printer["id"]
        })
    else:
        logger.error(f"Failed to add printer manually: {name} ({ip})")
        return jsonify({
            "success": False,
            "error": f"Failed to connect to printer at {ip}"
        }), 500


@api_bp.route('/printer/<printer_id>/files')
@login_required
def get_files(printer_id):
    """Get printer files."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    path = request.args.get('path', '/local')
    
    # Get files
    get_printer_files(printer_id, path)
    
    # Return files if available
    if 'files' in printers[printer_id] and path in printers[printer_id]['files']:
        return jsonify(printers[printer_id]['files'][path])
    else:
        return jsonify([])


@api_bp.route('/printer/<printer_id>/print', methods=['POST'])
@login_required
def print_file(printer_id):
    """Start a print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename is required"}), 400
    
    filename = data['filename']
    
    # Start print
    result = start_print(printer_id, filename)
    
    if result:
        return jsonify({"success": True, "message": f"Print started: {filename}"})
    else:
        return jsonify({"error": "Failed to start print"}), 500


@api_bp.route('/printer/<printer_id>/pause', methods=['POST'])
@login_required
def pause(printer_id):
    """Pause a print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    # Pause print
    result = pause_print(printer_id)
    
    if result:
        return jsonify({"success": True, "message": "Print paused"})
    else:
        return jsonify({"error": "Failed to pause print"}), 500


@api_bp.route('/printer/<printer_id>/resume', methods=['POST'])
@login_required
def resume(printer_id):
    """Resume a paused print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    # Resume print
    result = resume_print(printer_id)
    
    if result:
        return jsonify({"success": True, "message": "Print resumed"})
    else:
        return jsonify({"error": "Failed to resume print"}), 500


@api_bp.route('/printer/<printer_id>/stop', methods=['POST'])
@login_required
def stop(printer_id):
    """Stop a print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    # Stop print
    result = stop_print(printer_id)
    
    if result:
        return jsonify({"success": True, "message": "Print stopped"})
    else:
        return jsonify({"error": "Failed to stop print"}), 500


@api_bp.route('/printer/<printer_id>/camera', methods=['POST'])
@login_required
def camera(printer_id):
    """Control printer camera."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'enable' not in data:
        return jsonify({"error": "Enable parameter is required"}), 400
    
    enable = data['enable']
    
    # Set camera status
    result = set_camera_status(printer_id, enable)
    
    if result:
        return jsonify({
            "success": True, 
            "message": f"Camera {'enabled' if enable else 'disabled'}"
        })
    else:
        return jsonify({"error": "Failed to update camera status"}), 500


@api_bp.route('/printer/<printer_id>/delete', methods=['POST'])
@login_required
def delete(printer_id):
    """Delete a file from printer."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename is required"}), 400
    
    filename = data['filename']
    
    # Delete file
    result = delete_file(printer_id, filename)
    
    if result:
        return jsonify({"success": True, "message": f"File deleted: {filename}"})
    else:
        return jsonify({"error": "Failed to delete file"}), 500


@api_bp.route('/printer/<printer_id>/rename', methods=['POST'])
@login_required
def rename(printer_id):
    """Rename a printer."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    
    new_name = data['name']
    
    # Rename printer
    result = rename_printer(printer_id, new_name)
    
    if result:
        return jsonify({"success": True, "message": f"Printer renamed to: {new_name}"})
    else:
        return jsonify({"error": "Failed to rename printer"}), 500


@api_bp.route('/uploads')
@login_required
def get_uploads():
    """Get upload tasks."""
    return jsonify(upload_progress)


def validate_ip(ip):
    """Validate IP address format."""
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            num = int(part)
            if num < 0 or num > 255:
                return False
        return True
    except (ValueError, AttributeError):
        return False
    
@api_bp.route('/printer/diagnostics', methods=['POST'])
@login_required
def run_printer_diagnostics():
    """Run connection diagnostics on a printer IP."""
    data = request.json
    
    if not data or 'ip' not in data:
        return jsonify({"success": False, "error": "IP address is required"}), 400
    
    ip = data.get('ip')
    
    # Validate IP format
    if not validate_ip(ip):
        return jsonify({"success": False, "error": "Invalid IP address format"}), 400
    
    # Run diagnostics
    results = debug_printer_connection(ip)
    
    return jsonify({
        "success": True,
        "results": results
    })