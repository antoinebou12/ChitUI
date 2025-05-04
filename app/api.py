# app/api.py

from __future__ import annotations
import os
import time
import uuid
from datetime import datetime
from typing import Dict, Any

import requests
from flask import Blueprint, current_app, request, jsonify, abort, Response
from flask_login import current_user, login_required
from loguru import logger
from marshmallow import Schema, fields, ValidationError

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

# ─── Blueprint ────────────────────────────────────────────────────────────────

api_bp = Blueprint('api', __name__)


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AddPrinterSchema(Schema):
    name = fields.String(required=True)
    ip = fields.IP(required=True)
    model = fields.String(missing="unknown")
    brand = fields.String(missing="unknown")


class PrintRequestSchema(Schema):
    filename = fields.String(required=True)
    queue = fields.Boolean(missing=False)


class DiagnoseSchema(Schema):
    ip = fields.IP(required=True)


class JobCreateSchema(Schema):
    printer_id = fields.String(required=True)
    filename = fields.String(required=True)
    datetime = fields.DateTime(required=True)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_success(data: Any = None) -> Any:
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    return jsonify(payload)


def make_error(code: str, message: str, http_status: int = 400) -> Any:
    return jsonify({"success": False, "error": {"code": code, "message": message}}), http_status


def get_last_log_lines(log_path: str, num_lines: int = 500) -> list[str]:
    """
    Read the last `num_lines` from the given log file.
    Raises FileNotFoundError if the file does not exist.
    """
    if not os.path.exists(log_path):
        raise FileNotFoundError(f"Log file not found at {log_path}")
    with open(log_path, 'r') as f:
        # read all lines and slice
        lines = f.readlines()
    return lines[-num_lines:]


# ─── Swagger JSON ─────────────────────────────────────────────────────────────

@api_bp.route('/swagger.json')
def swagger_json():
    return jsonify({
        "swagger": "2.0",
        "info": {
            "title": "ChitUI API",
            "description": "API for controlling 3D printers with ChitUI",
            "version": "1.0.0"
        },
        "basePath": "/api",
        "schemes": ["http", "https"],
        "consumes": ["application/json", "application/x-www-form-urlencoded"],
        "produces": ["application/json"],
        "tags": [
            { "name": "Authentication", "description": "User login/logout" },
            { "name": "Printers",       "description": "Printer management" },
            { "name": "PrintJobs",      "description": "Job scheduling" },
            { "name": "System",         "description": "System info & logs" }
        ],
        "paths": {
            "/auth/login": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "User login",
                    "description": "Authenticate with username & password (sets session cookie)",
                    "consumes": ["application/x-www-form-urlencoded"],
                    "parameters": [
                        {
                            "in": "formData",
                            "name": "username",
                            "type": "string",
                            "required": True,
                            "description": "Your username"
                        },
                        {
                            "in": "formData",
                            "name": "password",
                            "type": "string",
                            "required": True,
                            "description": "Your password"
                        },
                        {
                            "in": "formData",
                            "name": "remember",
                            "type": "boolean",
                            "required": False,
                            "description": "Stay logged in (optional)"
                        }
                    ],
                    "responses": {
                        "200": { "description": "Login successful" },
                        "401": { "description": "Invalid credentials" }
                    }
                }
            },
            "/auth/logout": {
                "get": {
                    "tags": ["Authentication"],
                    "summary": "User logout",
                    "description": "Clear session and log out",
                    "responses": {
                        "302": { "description": "Redirect to login page" }
                    }
                }
            },
            "/printer/list": {
                "get": {
                    "tags": ["Printers"],
                    "summary": "Get list of printers",
                    "responses": { "200": { "description": "Success" } }
                }
            },
            "/printer/discover": {
                "post": {
                    "tags": ["Printers"],
                    "summary": "Discover printers",
                    "responses": { "200": { "description": "Discovery initiated" } }
                }
            },
            "/printer/{id}": {
                "get": {
                    "tags": ["Printers"],
                    "summary": "Get printer details",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "Printer details" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/add": {
                "post": {
                    "tags": ["Printers"],
                    "summary": "Add printer manually",
                    "parameters": [
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name":  { "type": "string" },
                                    "ip":    { "type": "string" },
                                    "model": { "type": "string" },
                                    "brand": { "type": "string" }
                                },
                                "required": ["name", "ip"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Printer added" },
                        "400": { "description": "Invalid input" },
                        "500": { "description": "Failed to add" }
                    }
                }
            },
            "/printer/{id}/files": {
                "get": {
                    "tags": ["Printers"],
                    "summary": "List files",
                    "parameters": [
                        { "name": "id", "in": "path",  "required": True,  "type": "string" },
                        { "name": "path","in": "query", "required": False, "type": "string", "default": "/local" }
                    ],
                    "responses": {
                        "200": { "description": "File list" },
                        "404": { "description": "Printer not found" }
                    }
                }
            },
            "/printer/{id}/print": {
                "post": {
                    "tags": ["PrintJobs"],
                    "summary": "Start or queue a print",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" },
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "filename": { "type": "string" },
                                    "queue":    { "type": "boolean", "default": False }
                                },
                                "required": ["filename"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Print started or queued" },
                        "404": { "description": "Printer or file not found" }
                    }
                }
            },
            "/printer/{id}/pause": {
                "post": {
                    "tags": ["PrintJobs"],
                    "summary": "Pause print",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "Paused" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/{id}/resume": {
                "post": {
                    "tags": ["PrintJobs"],
                    "summary": "Resume print",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "Resumed" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/{id}/stop": {
                "post": {
                    "tags": ["PrintJobs"],
                    "summary": "Stop print",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "Stopped" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/{id}/camera": {
                "post": {
                    "tags": ["Printers"],
                    "summary": "Enable/disable camera",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" },
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "enable": { "type": "boolean" }
                                },
                                "required": ["enable"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Updated" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/{id}/camera/status": {
                "get": {
                    "tags": ["Printers"],
                    "summary": "Get camera status",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "Camera status" },
                        "400": { "description": "Not supported" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/{id}/delete": {
                "post": {
                    "tags": ["Printers"],
                    "summary": "Delete file",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" },
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": { "filename": { "type": "string" } },
                                "required": ["filename"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Deleted" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/{id}/rename": {
                "post": {
                    "tags": ["Printers"],
                    "summary": "Rename printer",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" },
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": { "name": { "type": "string" } },
                                "required": ["name"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Renamed" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/printer/diagnostics": {
                "post": {
                    "tags": ["System"],
                    "summary": "Run diagnostics",
                    "parameters": [
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": { "ip": { "type": "string" } },
                                "required": ["ip"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Results" },
                        "400": { "description": "Invalid IP" }
                    }
                }
            },
            "/camera/{id}/frame": {
                "get": {
                    "tags": ["System"],
                    "summary": "Single camera frame",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "JPEG" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/camera/{id}/stream": {
                "get": {
                    "tags": ["System"],
                    "summary": "Camera MJPEG stream",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "MJPEG" },
                        "404": { "description": "Not found" }
                    }
                }
            },
            "/uploads": {
                "get": {
                    "tags": ["System"],
                    "summary": "List uploads",
                    "responses": { "200": { "description": "Upload tasks" } }
                }
            },
            "/jobs": {
                "get": {
                    "tags": ["PrintJobs"],
                    "summary": "List jobs",
                    "parameters": [
                        { "name": "history", "in": "query", "required": False, "type": "boolean" }
                    ],
                    "responses": { "200": { "description": "Scheduled jobs" } }
                },
                "post": {
                    "tags": ["PrintJobs"],
                    "summary": "Create job",
                    "parameters": [
                        {
                            "in": "body", "name": "body", "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "printer_id": { "type": "string" },
                                    "filename":   { "type": "string" },
                                    "datetime":   { "type": "string" }
                                },
                                "required": ["printer_id", "filename", "datetime"]
                            }
                        }
                    ],
                    "responses": {
                        "200": { "description": "Job created" },
                        "400": { "description": "Bad request" }
                    }
                }
            },
            "/printer/{id}/remove": {
                "post": {
                    "tags": ["Printers"],
                    "summary": "Remove printer",
                    "parameters": [
                        { "name": "id", "in": "path", "required": True, "type": "string" }
                    ],
                    "responses": {
                        "200": { "description": "Removed" },
                        "404": { "description": "Not found" },
                        "500": { "description": "Failed" }
                    }
                }
            },
            "/logs": {
                "get": {
                    "tags": ["System"],
                    "summary": "Get last N log lines",
                    "responses": {
                        "200": { "description": "Log lines" },
                        "404": { "description": "No log file" }
                    }
                }
            },
            "/health": {
                "get": {
                    "tags": ["System"],
                    "summary": "API health & uptime",
                    "responses": { "200": { "description": "Health info" } }
                }
            }
        }
    })




# ─── Endpoints ────────────────────────────────────────────────────────────────

@api_bp.route("/printer/list")
@login_required
def list_printers():
    return make_success({pid: dict(d) for pid, d in printers.items()})


@api_bp.route('/printer/discover', methods=['POST'])
@login_required
def discover_printers():
    """Kick off discovery in background."""
    from app.socket_handlers import discovery_task
    from threading import Thread
    Thread(target=discovery_task, daemon=True).start()
    return make_success({"message": "Discovery initiated"})


@api_bp.route('/printer/<printer_id>')
@login_required
def get_printer(printer_id):
    printer = printers.get(printer_id)
    if not printer:
        return make_error("NOT_FOUND", "Printer not found", 404)
    return make_success(printer)


@api_bp.route("/printer/add", methods=["POST"])
@login_required
def add_printer():
    try:
        payload = AddPrinterSchema().load(request.get_json(force=True))
    except ValidationError as err:
        return make_error("INVALID_INPUT", err.messages, 400)

    printer = add_printer_manually(**payload)
    if not printer:
        return make_error("ADD_FAILED", f"Cannot reach printer at {payload['ip']}", 500)

    logger.info(f"Printer added: {printer['name']} ({printer['ip']})")
    return make_success({"printer_id": printer["id"]})


@api_bp.route('/printer/<printer_id>/files')
@login_required
def api_get_printer_files(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)

    path = request.args.get('path', '/local')
    get_printer_files(printer_id, path)
    files = printers[printer_id].get("files", {}).get(path, [])
    return make_success(files)


@api_bp.route('/printer/<printer_id>/print', methods=['POST'])
@login_required
def api_print_file(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)

    try:
        payload = PrintRequestSchema().load(request.get_json(force=True))
    except ValidationError as err:
        return make_error("INVALID_INPUT", err.messages, 400)

    if payload["queue"]:
        queue_print(printer_id, payload["filename"])
        return make_success({"message": "File queued"})
    else:
        ok = start_print(printer_id, payload["filename"])
        if not ok:
            return make_error("PRINT_FAILED", "Failed to start print", 500)
        return make_success({"message": "Print started"})


@api_bp.route('/printer/<printer_id>/pause', methods=['POST'])
@login_required
def api_pause_print(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    if not pause_print(printer_id):
        return make_error("PAUSE_FAILED", "Failed to pause print", 500)
    return make_success()


@api_bp.route('/printer/<printer_id>/resume', methods=['POST'])
@login_required
def api_resume_print(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    if not resume_print(printer_id):
        return make_error("RESUME_FAILED", "Failed to resume print", 500)
    return make_success()


@api_bp.route('/printer/<printer_id>/stop', methods=['POST'])
@login_required
def api_stop_print(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    if not stop_print(printer_id):
        return make_error("STOP_FAILED", "Failed to stop print", 500)
    return make_success()


@api_bp.route('/printer/<printer_id>/camera', methods=['POST'])
@login_required
def api_set_camera(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    try:
        payload = DiagnoseSchema().load(request.get_json(force=True))
    except ValidationError as err:
        return make_error("INVALID_INPUT", err.messages, 400)

    ok = set_camera_status(printer_id, payload["ip"])
    if not ok:
        return make_error("CAMERA_FAILED", "Failed to update camera", 500)
    return make_success()


@api_bp.route('/printer/<printer_id>/delete', methods=['POST'])
@login_required
def api_delete_file(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    filename = request.json.get("filename")
    if not filename:
        return make_error("INVALID_INPUT", "Filename is required", 400)

    if not delete_file(printer_id, filename):
        return make_error("DELETE_FAILED", "Failed to delete file", 500)
    return make_success()


@api_bp.route('/printer/<printer_id>/rename', methods=['POST'])
@login_required
def api_rename_printer(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    new_name = request.json.get("name")
    if not new_name:
        return make_error("INVALID_INPUT", "Name is required", 400)

    if not rename_printer(printer_id, new_name):
        return make_error("RENAME_FAILED", "Failed to rename printer", 500)
    return make_success()


@api_bp.route('/printer/diagnostics', methods=['POST'])
@login_required
def api_diagnostics():
    try:
        payload = DiagnoseSchema().load(request.get_json(force=True))
    except ValidationError as err:
        return make_error("INVALID_INPUT", err.messages, 400)

    results = debug_printer_connection(payload["ip"])
    return make_success(results)


@api_bp.route("/camera/<printer_id>/frame")
@login_required
def api_camera_frame(printer_id):
    p = printers.get(printer_id)
    if not p or "camera_config" not in p:
        abort(404)
    url = p["camera_config"]["snapshot"].format(ip=p["ip"])
    r = requests.get(url, stream=True, timeout=5)
    return Response(r.iter_content(4096), mimetype="image/jpeg")


@api_bp.route("/camera/<printer_id>/stream")
@login_required
def api_camera_stream(printer_id):
    p = printers.get(printer_id)
    if not p or "camera_config" not in p:
        abort(404)
    url = p["camera_config"]["mjpeg"].format(ip=p["ip"])

    def gen():
        with requests.get(url, stream=True, timeout=5) as r:
            for chunk in r.iter_content(1024):
                yield chunk
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@api_bp.route("/uploads")
@login_required
def api_list_uploads():
    return make_success(upload_progress)


@api_bp.route("/jobs", methods=["POST"])
@login_required
def api_create_job():
    try:
        payload = JobCreateSchema().load(request.get_json(force=True))
    except ValidationError as err:
        return make_error("INVALID_INPUT", err.messages, 400)

    try:
        job = PrintJob(
            id=str(uuid.uuid4()),
            printer_id=payload["printer_id"],
            user_id=current_user.id,
            filename=payload["filename"],
            status=JobStatus.QUEUED,
            scheduled=payload["datetime"],
        )
        db.session.add(job)
        db.session.commit()

        sched.add_job(
            func=start_print,
            trigger="date",
            run_date=job.scheduled,
            args=[job.printer_id, job.filename],
            id=str(job.id),
        )
        return make_success({"job_id": job.id})
    except Exception as e:
        logger.error(f"Job creation failed: {e}")
        return make_error("JOB_FAILED", str(e), 500)


@api_bp.route("/jobs")
@login_required
def api_list_jobs():
    history = request.args.get("history", "false").lower() == "true"
    q = PrintJob.query
    if not history:
        q = q.filter(PrintJob.status == JobStatus.QUEUED)
    jobs = q.order_by(PrintJob.scheduled.desc()).all()
    return make_success([j.to_dict() for j in jobs])


@api_bp.route('/printer/<printer_id>/remove', methods=['POST'])
@login_required
def api_remove_printer(printer_id):
    if printer_id not in printers:
        return make_error("NOT_FOUND", "Printer not found", 404)
    name = printers[printer_id].get("name", printer_id)
    if not remove_printer(printer_id):
        return make_error("REMOVE_FAILED", "Failed to remove printer", 500)

    # Clean up in DB as well
    try:
        from app.models import Printer as DBPrinter
        dbp = DBPrinter.query.get(printer_id)
        if dbp:
            db.session.delete(dbp)
            db.session.commit()
    except Exception as db_e:
        logger.warning(f"DB cleanup failed: {db_e}")

    return make_success({"message": f"Printer '{name}' removed"})


@api_bp.route('/logs')
@login_required
def api_get_logs():
    """
    Return the last N lines of the application log.
    Configuration key: LOG_FILE (must be set in app.config).
    """
    log_path = current_app.config.get('LOG_FILE', 'logs/chitui.log')
    try:
        lines = get_last_log_lines(log_path, num_lines=500)
    except FileNotFoundError as e:
        return make_error('NOT_FOUND', str(e), 404)

    return make_success({'lines': lines})


@api_bp.route("/health")
def api_health():
    start = current_app.config.get('_start_time', time.time())
    uptime = round(time.time() - start)
    return make_success({
        "uptime": uptime,
        "printers": len(printers),
    })


@api_bp.route('/printer/<printer_id>/camera/status')
@login_required
def api_camera_status(printer_id):
    p = printers.get(printer_id)
    if not p:
        return make_error('NOT_FOUND', "Printer not found", 404)
    if 'camera_config' not in p:
        return make_error('BAD_REQUEST', "Printer has no camera", 400)
    return make_success({'enabled': p.get('camera_config', {}).get('enabled', False)})