"""
REST API endpoints for ChitUI
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Dict, Any

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    request,
)
from flask_login import current_user, login_required
from loguru import logger

from app import printers, sched, upload_progress
from app.models import JobStatus, PrintJob, db
from app.printer_manager import (
    add_printer_manually,
    debug_printer_connection,
    delete_file,
    get_printer_files,
    pause_print,
    rename_printer,
    resume_print,
    set_camera_status,
    start_print,
    stop_print,
    queue_print,
    remove_printer
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
                                    },
                                    "queue": {
                                        "type": "boolean",
                                        "description": "Add to queue if printer is busy"
                                    }
                                },
                                "required": ["filename"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Print started or queued"
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
            "/printer/{id}/delete": {
                "post": {
                    "summary": "Delete file",
                    "description": "Delete a file from the printer",
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
                                        "description": "File to delete"
                                    }
                                },
                                "required": ["filename"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "File deleted"
                        },
                        "404": {
                            "description": "Printer or file not found"
                        }
                    }
                }
            },
            "/printer/{id}/rename": {
                "post": {
                    "summary": "Rename printer",
                    "description": "Change the display name of a printer",
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
                                    "name": {
                                        "type": "string",
                                        "description": "New printer name"
                                    }
                                },
                                "required": ["name"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Printer renamed"
                        },
                        "404": {
                            "description": "Printer not found"
                        }
                    }
                }
            },
            "/printer/diagnostics": {
                "post": {
                    "summary": "Run diagnostics",
                    "description": "Test connectivity to a printer IP address",
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "ip": {
                                        "type": "string",
                                        "description": "IP address to test"
                                    }
                                },
                                "required": ["ip"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Diagnostic results"
                        },
                        "400": {
                            "description": "Invalid IP address"
                        }
                    }
                }
            },
            "/camera/{id}/frame": {
                "get": {
                    "summary": "Get camera frame",
                    "description": "Retrieve a single camera frame from a printer",
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
                            "description": "JPEG image"
                        },
                        "404": {
                            "description": "Printer or camera not found"
                        }
                    }
                }
            },
            "/camera/{id}/stream": {
                "get": {
                    "summary": "Camera stream",
                    "description": "Stream camera feed from a printer (MJPEG)",
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
                            "description": "MJPEG stream"
                        },
                        "404": {
                            "description": "Printer or camera not found"
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
            },
            "/jobs": {
                "get": {
                    "summary": "List jobs",
                    "description": "Get scheduled print jobs",
                    "parameters": [
                        {
                            "name": "history",
                            "in": "query",
                            "required": False,
                            "type": "boolean",
                            "description": "Include job history"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of jobs"
                        }
                    }
                },
                "post": {
                    "summary": "Create job",
                    "description": "Schedule a print job",
                    "parameters": [
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "printer_id": {
                                        "type": "string",
                                        "description": "Printer ID"
                                    },
                                    "filename": {
                                        "type": "string",
                                        "description": "File to print"
                                    },
                                    "datetime": {
                                        "type": "string",
                                        "description": "ISO8601 datetime"
                                    }
                                },
                                "required": ["printer_id", "filename", "datetime"]
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Job created"
                        },
                        "400": {
                            "description": "Invalid request"
                        }
                    }
                }
            },
            "/health": {
                "get": {
                    "summary": "API health",
                    "description": "Check API health and uptime",
                    "responses": {
                        "200": {
                            "description": "Health status"
                        }
                    }
                }
            }
        }
    })


def validate_ip(ip: str) -> bool:
    """Validate IP address format with proper error handling."""
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        return all(0 <= int(p) <= 255 for p in parts)
    except (ValueError, TypeError):
        return False


# ───────────────────────────────────────── Printer Management ──

@api_bp.route("/printer/list")
@login_required
def list_printers():
    """Return the current in-memory printer registry."""
    return jsonify({pid: dict(d) for pid, d in printers.items()})


@api_bp.route('/printer/discover', methods=['POST'])
@login_required
def discover_printers():
    """Initiate printer discovery in background thread."""
    from app.socket_handlers import discovery_task
    from threading import Thread
    
    Thread(target=discovery_task, daemon=True).start()
    
    return jsonify({
        "success": True,
        "message": "Discovery initiated"
    })


@api_bp.route('/printer/<printer_id>')
@login_required
def get_printer(printer_id):
    """Get details for a specific printer."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    return jsonify(printers[printer_id])


@api_bp.route("/printer/add", methods=["POST"])
@login_required
def add_printer():
    """Manually add a printer by IP address."""
    data: Dict = request.get_json(force=True)
    name = data.get("name")
    ip = data.get("ip")
    model = data.get("model", "unknown")
    brand = data.get("brand", "unknown")

    if not name or not ip:
        return jsonify(success=False, error="Name and IP address are required"), 400
    if not validate_ip(ip):
        return jsonify(success=False, error="Invalid IP address"), 400

    printer = add_printer_manually(name, ip, model, brand)
    if not printer:
        return (
            jsonify(success=False, error=f"Failed to reach printer at {ip}"),
            500,
        )

    logger.info(f"Printer added manually: {name} ({ip})")
    return jsonify(success=True, printer_id=printer["id"])


@api_bp.route('/printer/<printer_id>/files')
@login_required
def get_printer_files(printer_id):
    """Get files from a printer."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    path = request.args.get('path', '/local')
    
    # Request files from printer
    get_printer_files(printer_id, path)
    
    # Return files if available
    files = printers[printer_id].get("files", {}).get(path, [])
    return jsonify(files)


@api_bp.route('/printer/<printer_id>/print', methods=['POST'])
@login_required
def print_file(printer_id):
    """Start or queue a print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename is required"}), 400
    
    filename = data['filename']
    use_queue = data.get('queue', False)
    
    # Start or queue print
    if use_queue:
        queue_print(printer_id, filename)
        return jsonify({
            "success": True, 
            "message": f"File queued: {filename}"
        })
    else:
        result = start_print(printer_id, filename)
        if result:
            return jsonify({
                "success": True, 
                "message": f"Print started: {filename}"
            })
        else:
            return jsonify({
                "error": "Failed to start print"
            }), 500


@api_bp.route('/printer/<printer_id>/pause', methods=['POST'])
@login_required
def pause_print_job(printer_id):
    """Pause a print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    result = pause_print(printer_id)
    
    if result:
        return jsonify({
            "success": True, 
            "message": "Print paused"
        })
    else:
        return jsonify({
            "error": "Failed to pause print"
        }), 500


@api_bp.route('/printer/<printer_id>/resume', methods=['POST'])
@login_required
def resume_print_job(printer_id):
    """Resume a paused print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    result = resume_print(printer_id)
    
    if result:
        return jsonify({
            "success": True, 
            "message": "Print resumed"
        })
    else:
        return jsonify({
            "error": "Failed to resume print"
        }), 500


@api_bp.route('/printer/<printer_id>/stop', methods=['POST'])
@login_required
def stop_print_job(printer_id):
    """Stop a print job."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    result = stop_print(printer_id)
    
    if result:
        return jsonify({
            "success": True, 
            "message": "Print stopped"
        })
    else:
        return jsonify({
            "error": "Failed to stop print"
        }), 500


@api_bp.route('/printer/<printer_id>/camera', methods=['POST'])
@login_required
def set_printer_camera(printer_id):
    """Control printer camera."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'enable' not in data:
        return jsonify({"error": "Enable parameter is required"}), 400
    
    enable = data['enable']
    
    result = set_camera_status(printer_id, enable)
    
    if result:
        return jsonify({
            "success": True, 
            "message": f"Camera {'enabled' if enable else 'disabled'}"
        })
    else:
        return jsonify({
            "error": "Failed to update camera status"
        }), 500


@api_bp.route('/printer/<printer_id>/delete', methods=['POST'])
@login_required
def delete_printer_file(printer_id):
    """Delete a file from printer."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename is required"}), 400
    
    filename = data['filename']
    
    result = delete_file(printer_id, filename)
    
    if result:
        return jsonify({
            "success": True, 
            "message": f"File deleted: {filename}"
        })
    else:
        return jsonify({
            "error": "Failed to delete file"
        }), 500


@api_bp.route('/printer/<printer_id>/rename', methods=['POST'])
@login_required
def rename_printer_name(printer_id):
    """Rename a printer."""
    if printer_id not in printers:
        return jsonify({"error": "Printer not found"}), 404
    
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({"error": "Name is required"}), 400
    
    new_name = data['name']
    
    result = rename_printer(printer_id, new_name)
    
    if result:
        return jsonify({
            "success": True, 
            "message": f"Printer renamed to: {new_name}"
        })
    else:
        return jsonify({
            "error": "Failed to rename printer"
        }), 500


@api_bp.route('/printer/diagnostics', methods=['POST'])
@login_required
def run_printer_diagnostics():
    """Run connection diagnostics on a printer IP."""
    data = request.json
    
    if not data or 'ip' not in data:
        return jsonify({
            "success": False, 
            "error": "IP address is required"
        }), 400
    
    ip = data.get('ip')
    
    if not validate_ip(ip):
        return jsonify({
            "success": False, 
            "error": "Invalid IP address format"
        }), 400
    
    results = debug_printer_connection(ip)
    
    return jsonify({
        "success": True,
        "results": results
    })


# ───────────────────────────────────────── Camera Access ──

@api_bp.route("/camera/<printer_id>/frame")
@login_required
def get_camera_frame(printer_id):
    """Get a single camera frame from a printer."""
    printer = printers.get(printer_id)
    if not printer or "camera_config" not in printer:
        return abort(404)
    
    url = printer["camera_config"]["snapshot"].format(ip=printer["ip"])
    
    try:
        r = requests.get(url, stream=True, timeout=3)
        return Response(r.iter_content(4096), mimetype="image/jpeg")
    except Exception as e:
        logger.error(f"Camera frame error: {e}")
        return jsonify({"error": "Failed to get camera frame"}), 500


@api_bp.route("/camera/<printer_id>/stream")
@login_required
def stream_camera(printer_id):
    """Stream camera feed from a printer."""
    printer = printers.get(printer_id)
    if not printer or "camera_config" not in printer:
        return abort(404)
    
    url = printer["camera_config"]["mjpeg"].format(ip=printer["ip"])

    def generate_stream():
        try:
            with requests.get(url, stream=True, timeout=3) as r:
                for chunk in r.iter_content(1024):
                    yield chunk
        except Exception as e:
            logger.error(f"Camera stream error: {e}")
            yield b""

    return Response(
        generate_stream(), 
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ───────────────────────────────────────── Uploads ──

@api_bp.route("/uploads")
@login_required
def list_uploads():
    """Get all upload tasks."""
    return jsonify(upload_progress)


# ───────────────────────────────────────── Jobs ──

@api_bp.route("/jobs", methods=["POST"])
@login_required
def create_job():
    """Schedule a print job."""
    data = request.get_json(force=True)
    
    # Validate required fields
    required_fields = ["printer_id", "filename", "datetime"]
    missing_fields = [f for f in required_fields if f not in data]
    
    if missing_fields:
        return jsonify({
            "success": False,
            "error": f"Missing required fields: {', '.join(missing_fields)}"
        }), 400
    
    try:
        job = PrintJob(
            id=str(uuid.uuid4()),
            printer_id=data["printer_id"],
            user_id=current_user.id,
            filename=data["filename"],
            status=JobStatus.QUEUED,
            scheduled=datetime.fromisoformat(data["datetime"]),
        )
        
        db.session.add(job)
        db.session.commit()

        # Schedule the job
        sched.add_job(
            func=start_print,
            trigger="date",
            run_date=job.scheduled,
            args=[job.printer_id, job.filename],
            id=str(job.id),
        )
        
        return jsonify({
            "success": True,
            "id": job.id
        })
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to create job: {str(e)}"
        }), 500


@api_bp.route("/jobs")
@login_required
def list_jobs():
    """Get scheduled print jobs."""
    show_history = request.args.get("history", "false").lower() == "true"
    
    query = PrintJob.query
    if not show_history:
        query = query.filter(PrintJob.status == JobStatus.QUEUED)
    
    jobs = query.order_by(PrintJob.scheduled.desc()).all()
    return jsonify([job.to_dict() for job in jobs])


# ───────────────────────────────────────── Health ──

_start_time = time.time()

@api_bp.route("/health")
def health_check():
    """Check API health and uptime."""
    return jsonify({
        "status": "ok",
        "uptime": round(time.time() - _start_time),
        "printers": len(printers),
    })

@api_bp.route('/printer/<printer_id>/camera/status')
@login_required
def get_camera_status(printer_id):
    """Get the status of the printer camera."""
    if printer_id not in printers:
        return jsonify({"success": False, "error": "Printer not found"}), 404
    
    printer = printers[printer_id]
    
    # Check if the printer supports camera
    if not printer.get("supports_camera", False):
        return jsonify({"success": False, "error": "Printer does not support camera"}), 400
    
    # Return camera status from printer data
    camera_enabled = printer.get("camera_status", False)
    
    return jsonify({
        "success": True,
        "enabled": camera_enabled
    })

@api_bp.route('/printer/<printer_id>/remove', methods=['POST'])
@login_required
def remove_printer_endpoint(printer_id):
    """Remove a printer from the system."""
    if printer_id not in printers:
        return jsonify({"success": False, "error": "Printer not found"}), 404
    
    # Get printer name before removal for response
    printer_name = printers[printer_id].get('name', 'Unknown printer')
    
    # Use the printer_manager function
    from app.printer_manager import remove_printer
    result = remove_printer(printer_id)
    
    if result:
        # Try database cleanup if needed
        try:
            from app.models import Printer, db
            db_printer = Printer.query.filter_by(id=printer_id).first()
            if db_printer:
                db.session.delete(db_printer)
                db.session.commit()
                logger.info(f"Removed printer {printer_id} from database")
        except Exception as db_err:
            logger.warning(f"Database removal failed for printer {printer_id}: {db_err}")
        
        return jsonify({
            "success": True, 
            "message": f"Printer '{printer_name}' removed successfully"
        })
    else:
        return jsonify({
            "success": False, 
            "error": f"Failed to remove printer"
        }), 500