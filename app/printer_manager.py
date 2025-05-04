"""
Printer management module for ChitUI
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
import time
import uuid
from collections import defaultdict
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

import requests
import websocket
from loguru import logger
from tqdm import tqdm
import threading

from app import printers, websockets, upload_progress
from app.constants import CAMERA_ENABLED_MODELS, CMD, MACHINE_STATUS, PRINTER_ICONS

# Configure logging
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler('printer_debug.log'),
        logging.StreamHandler()
    ]
)

try:
    import netifaces
    _HAS_NETIFACES = True
except ImportError:
    _HAS_NETIFACES = False
    logger.warning("netifaces not installed; falling back to RFC1918 subnets")

# ─────────────────────────── Globals ──
printer_lock = Lock()
job_queues: Dict[str, List[str]] = defaultdict(list)  # printer_id → queue of filenames

WS_PORTS = (3030, 3031)  # Elegoo 14 K listens on 3031
UDP_DISCOVERY_PORT = 3000
UDP_LISTEN_PORT = 54781
UDP_MSG = b"M99999"
WS_TIMEOUT = 6
CHUNK_SIZE = 1048576  # 1MB chunks for file uploads
SOCKET_TIMEOUT = 2
DEFAULT_TIMEOUT = 2
MAX_RETRIES = 2
MAX_WORKERS = 8

# ============================================================================
# Low‑level helpers
# ----------------------------------------------------------------------------

def _ping(ip: str) -> bool:
    """Return *True* if host responds to a single ICMP ping."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    return subprocess.run(["ping", param, "1", ip], capture_output=True).returncode == 0


def _ws_send(pid: str, cmd: int | str, data: dict | None = None) -> bool:
    """Serialize and send an SDCP command over the cached WebSocket."""
    if pid not in websockets:
        logger.warning(f"No WS for {pid}")
        return False
    ws = websockets[pid]
    cmd_code = CMD[cmd] if isinstance(cmd, str) else cmd
    payload = {
        "Id": printers[pid]["connection"],
        "Data": {
            "Cmd": cmd_code,
            "Data": data or {},
            "RequestID": os.urandom(8).hex(),
            "MainboardID": pid,
            "TimeStamp": int(time.time()),
            "From": 0,
        },
        "Topic": f"sdcp/request/{pid}",
    }
    try:
        ws.send(json.dumps(payload))
        logger.debug(f"→ {cmd} to {pid}")
        return True
    except Exception as exc:
        logger.error(f"Send {cmd} failed: {exc}")
        return False


# ============================================================================
# Discovery & manual‑add
# ----------------------------------------------------------------------------

def discover_printers(timeout=2):
    """Broadcast UDP packet and collect printer beacons with improved network handling."""
    logger.info("Starting enhanced printer discovery")
    
    discovered = {}
    
    try:
        # Get all network interfaces
        network_interfaces = []
        
        try:
            # Try using netifaces for better network interface detection
            import netifaces
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr and 'broadcast' in addr:
                            network_interfaces.append({
                                'name': iface,
                                'ip': addr['addr'],
                                'broadcast': addr['broadcast']
                            })
                            logger.debug(f"Found interface: {iface} ({addr['addr']}) - broadcast: {addr['broadcast']}")
        except ImportError:
            # Fallback to common broadcast addresses
            logger.info("Netifaces not available, using fallback addresses")
            network_interfaces = [
                {'name': 'default', 'ip': '0.0.0.0', 'broadcast': '255.255.255.255'},
                {'name': 'subnet-0', 'ip': '0.0.0.0', 'broadcast': '192.168.0.255'},
                {'name': 'subnet-1', 'ip': '0.0.0.0', 'broadcast': '192.168.1.255'}
            ]
        
        # If no interfaces found, use default
        if not network_interfaces:
            network_interfaces = [
                {'name': 'default', 'ip': '0.0.0.0', 'broadcast': '255.255.255.255'}
            ]
        
        # Also perform a direct scan to the specific printer IP if provided as environment variable
        specific_ip = os.environ.get('PRINTER_IP')
        if specific_ip:
            logger.info(f"Attempting direct discovery for IP: {specific_ip}")
            direct_result = discover_printer_by_ip(specific_ip, timeout)
            discovered.update(direct_result)
        
        # Scan all interfaces in parallel
        threads = []
        thread_lock = threading.Lock()
        
        for interface in network_interfaces:
            thread = threading.Thread(
                target=scan_interface,
                args=(interface, timeout, discovered, thread_lock)
            )
            thread.daemon = True
            threads.append(thread)
            thread.start()
            
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
            
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
    
    logger.info(f"Discovery completed: {len(discovered)} printers found")
    return discovered

def scan_interface(interface: Dict[str, str],
                   timeout: float,
                   discovered: Dict[str, Any],
                   lock: threading.Lock):
    """
    (Your original logic, unchanged)
    """
    interface_name = interface['name']
    source_ip = interface['ip']
    broadcast = interface['broadcast']
    
    logger.debug(f"Scanning {interface_name}: {source_ip} → {broadcast}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)
            try:
                sock.bind((source_ip, 0))
            except socket.error as e:
                logger.warning(f"Bind {source_ip} failed: {e}; using default")
                sock.bind(('', 0))
            sock.sendto(UDP_MSG, (broadcast, UDP_DISCOVERY_PORT))
            start = time.time()
            while time.time() - start < timeout:
                try:
                    data, addr = sock.recvfrom(8192)
                    j = json.loads(data.decode('utf-8'))
                    pid = (
                        j.get('Data', {}).get('MainboardID')
                        or j.get('Data', {}).get('Attributes', {}).get('MainboardID')
                    )
                    if pid:
                        logger.info(f"Discovered {pid} at {addr[0]} via {interface_name}")
                        with lock:
                            if pid not in discovered:
                                discovered[pid] = save_discovered_printer(data, addr)
                except socket.timeout:
                    break
                except json.JSONDecodeError as je:
                    logger.warning(f"Bad JSON from {addr[0]}: {je}")
                except Exception as e:
                    logger.warning(f"Scan error from {addr[0]}: {e}")
    except Exception as e:
        logger.warning(f"Socket error on {interface_name}: {e}")

def discover_printer_by_ip(ip: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    (Your original direct-IP logic, unchanged)
    """
    logger.info(f"Attempting direct discovery for printer at {ip}")
    discovered = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(UDP_MSG, (ip, UDP_DISCOVERY_PORT))
            try:
                data, addr = sock.recvfrom(8192)
                j = json.loads(data.decode('utf-8'))
                pid = (
                    j.get('Data', {}).get('MainboardID')
                    or j.get('Data', {}).get('Attributes', {}).get('MainboardID')
                )
                if pid:
                    logger.info(f"Directly discovered {pid} at {addr[0]}")
                    discovered[pid] = save_discovered_printer(data, addr)
            except socket.timeout:
                logger.warning(f"No response from {ip}")
    except Exception as e:
        logger.error(f"Direct discovery error for {ip}: {e}")
    return discovered


def save_discovered_printer(data, addr=None):
    """Parse printer data with robust error handling."""
    try:
        if isinstance(data, bytes):
            j = json.loads(data.decode('utf-8'))
        else:
            j = data
        
        # Handle different response formats
        if 'Data' in j:
            if 'Attributes' in j['Data']:
                # Standard format
                printer = {
                    'connection': j['Id'],
                    'name': j['Data']['Attributes'].get('Name', 'Unknown Printer'),
                    'model': j['Data']['Attributes'].get('MachineName', 'Unknown Model'),
                    'brand': j['Data'].get('BrandName', 'ELEGOO'),
                    'ip': j['Data'].get('MainboardIP', addr[0] if addr else 'Unknown'),
                    'protocol': j['Data'].get('ProtocolVersion', 'Unknown'),
                    'firmware': j['Data'].get('FirmwareVersion', 'Unknown'),
                    'status': 'disconnected',
                    'last_seen': time.time(),
                    'files': {}  # Initialize files dictionary
                }
            else:
                # Alternative format
                printer = {
                    'connection': j['Id'],
                    'name': j['Data'].get('Name', 'Unknown Printer'),
                    'model': j['Data'].get('MachineName', 'Unknown Model'),
                    'brand': j['Data'].get('BrandName', 'ELEGOO'),
                    'ip': j['Data'].get('MainboardIP', addr[0] if addr else 'Unknown'),
                    'protocol': j['Data'].get('ProtocolVersion', 'Unknown'),
                    'firmware': j['Data'].get('FirmwareVersion', 'Unknown'),
                    'status': 'disconnected',
                    'last_seen': time.time(),
                    'files': {}  # Initialize files dictionary
                }
        else:
            # Fallback format
            printer = {
                'connection': j.get('Id', 'Unknown'),
                'name': 'Unknown Printer',
                'model': 'Unknown Model',
                'brand': 'ELEGOO',
                'ip': addr[0] if addr else 'Unknown',
                'protocol': 'Unknown',
                'firmware': 'Unknown',
                'status': 'disconnected',
                'last_seen': time.time(),
                'files': {}  # Initialize files dictionary
            }
        
        # Extract printer ID
        if 'Data' in j and 'MainboardID' in j['Data']:
            printer_id = j['Data']['MainboardID']
        elif 'Data' in j and 'Attributes' in j['Data'] and 'MainboardID' in j['Data']['Attributes']:
            printer_id = j['Data']['Attributes']['MainboardID']
        else:
            printer_id = f"unknown_{addr[0]}" if addr else f"unknown_{uuid.uuid4()}"
        
        logger.info(f"Discovered: {printer['name']} ({printer['ip']})")
        
        if printer_id:
            printers[printer_id] = printer
        
        return printer
    except Exception as e:
        logger.error(f"Error parsing printer data: {e}")
        
        # Create minimal printer entry on error
        if addr:
            minimal_printer = {
                'connection': f"manual_{uuid.uuid4().hex[:8]}",
                'name': f"Printer at {addr[0]}",
                'model': 'Unknown Model',
                'brand': 'ELEGOO',
                'ip': addr[0],
                'protocol': 'Unknown',
                'firmware': 'Unknown',
                'status': 'disconnected',
                'last_seen': time.time(),
                'files': {}  # Initialize files dictionary
            }
            return minimal_printer
        return None
def add_printer_manually(name: str, ip: str, model: str = "unknown", brand: str = "unknown") -> Dict[str, Any]:
    """Manually add a printer when UDP broadcast is disabled."""
    pid = hashlib.md5(ip.encode()).hexdigest()

    printer: Dict[str, Any] = {
        "id": pid,
        "connection": f"manual_{uuid.uuid4().hex[:8]}",
        "name": name,
        "model": model.lower(),
        "brand": brand.lower(),
        "ip": ip,
        "protocol": "unknown",
        "firmware": "unknown",
        "status": "disconnected",
        "last_seen": time.time(),
        "machine_status": None,
        "print_status": None,
        "files": {},
        "print_progress": None,
        "current_file": None,
        "remain_time": None,
        "manually_added": True,
        "supports_camera": False,
    }

    icon_key = f"{printer['brand']}_{printer['model']}".replace(" ", "")
    printer["icon"] = PRINTER_ICONS.get(icon_key, PRINTER_ICONS["default"])

    for mdl, cfg in CAMERA_ENABLED_MODELS.items():
        if mdl in printer["model"]:
            printer["supports_camera"] = True
            printer["camera_config"] = cfg
            break

    # Simple reachability check
    if not _ping(ip):
        logger.warning(f"{ip} is not reachable – adding anyway (manual)")

    with printer_lock:
        printers[pid] = printer
    Thread(target=lambda: connect_printer(pid), daemon=True).start()
    return printer

# ============================================================================
# Connection & WebSocket handlers
# ----------------------------------------------------------------------------

def connect_printer(pid: str) -> bool:
    """Connect to a specific printer by ID."""
    if pid not in printers:
        logger.error(f"Unknown printer {pid}")
        return False
    
    printer = printers[pid]
    logger.info(f"Connecting to printer: {printer['name']} ({printer['ip']})")
    
    websocket.setdefaulttimeout(WS_TIMEOUT)
    
    for port in WS_PORTS:
        url = f"ws://{printer['ip']}:{port}/websocket"
        logger.info(f"▶ Trying connection on {url}")
        
        try:
            ws = websocket.WebSocketApp(
                url,
                on_open=lambda *_: _ws_open(pid),
                on_message=lambda _, msg: _ws_message(pid, msg),
                on_close=lambda _, c, m: _ws_close(pid, c, m),
                on_error=lambda _, err: _ws_error(pid, err),
            )
            websockets[pid] = ws
            Thread(target=lambda: ws.run_forever(reconnect=5, ping_interval=30, ping_timeout=10), daemon=True).start()
            return True
        except OSError as exc:
            logger.warning(f"Port {port} failed: {exc}")
            continue
    
    logger.error(f"All WS ports failed for {printer['name']} ({printer['ip']})")
    return False


# — WebSocket event callbacks —

def _ws_open(pid: str):
    """WebSocket open event handler."""
    with printer_lock:
        printers[pid]["status"] = "connected"
        printers[pid]["last_seen"] = time.time()
    
    logger.info(f"WS connected: {printers[pid]['name']}")
    
    # Request initial status and attributes
    _ws_send(pid, "STATUS")
    _ws_send(pid, "ATTRIBUTES")
    _ws_send(pid, "FILE_LIST", {"Url": "/local"})


def _ws_close(pid: str, code: int, msg: str):
    """WebSocket close event handler."""
    with printer_lock:
        printers[pid]["status"] = "disconnected"
    logger.info(f"WS closed ({code}): {printers[pid]['name']} – {msg}")


def _ws_error(pid: str, err: Exception):
    """WebSocket error event handler."""
    logger.error(f"WS error for {pid}: {err}")


def _ws_message(pid: str, raw: str):
    """WebSocket message handler."""
    if pid not in printers:
        logger.warning(f"Received message for unknown printer: {pid}")
        return

    try:
        # Parse message with error handling
        try:
            packet = json.loads(raw)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON message for printer {pid}: {json_err}")
            logger.error(f"Problematic message: {raw}")
            return

        # Log full message for debugging
        logger.debug(f"Received message from printer {pid}: {json.dumps(packet, indent=2)}")

        # Process message topic
        topic = packet.get("Topic", "")
        
        HANDLERS = {
            "sdcp/status/": _on_status,
            "sdcp/attributes/": _on_attributes,
            "sdcp/response/": _on_response,
            "sdcp/error/": _on_error,
            "sdcp/notice/": _on_notice,
        }
        
        # Route message to correct handler
        for prefix, handler in HANDLERS.items():
            if topic.startswith(prefix):
                try:
                    handler(pid, packet)
                except Exception as process_err:
                    logger.error(f"Error processing {topic} message for printer {pid}: {process_err}")
                    logger.error(f"Problematic message data: {json.dumps(packet, indent=2)}")
                return
                
        logger.warning(f"Received unknown message topic: {topic}")

    except Exception as e:
        logger.error(f"Unexpected error in WebSocket message handler for printer {pid}: {e}")
        logger.error(f"Original message: {raw}")


# ============================================================================
# Message processors
# ----------------------------------------------------------------------------

def _on_status(pid: str, packet: Dict[str, Any]):
    """Process printer status messages."""
    status = packet.get("Status", {})
    
    # Parse machine status code
    current_status = status.get("CurrentStatus")
    
    # Normalize current_status to a single integer
    machine_status_code = 0
    if current_status is not None:
        if isinstance(current_status, list):
            # If it's a list, try to get the first element
            try:
                machine_status_code = int(current_status[0]) if current_status else 0
            except (IndexError, ValueError, TypeError):
                machine_status_code = 0
        elif isinstance(current_status, (int, str)):
            try:
                machine_status_code = int(current_status)
            except (ValueError, TypeError):
                machine_status_code = 0
    
    # Get machine status name
    machine_status_name = MACHINE_STATUS.get(
        machine_status_code,
        {"name": "UNKNOWN"}
    )["name"]
    
    # Detect finish transition
    finished = False
    
    with printer_lock:
        p = printers[pid]
        prev = p.get("machine_status")
        p["machine_status"] = machine_status_name
        
        if machine_status_name == "PRINTING":
            info = status.get("PrintInfo", {})
            p["print_status"] = info.get("PrintStatus")
            p["current_file"] = info.get("Filename")
            
            # Calculate progress safely
            try:
                layer = int(info.get("Layer", 0))
                total_layers = int(info.get("TotalLayer", 1)) or 1
                p["print_progress"] = round((layer / total_layers) * 100)
            except (TypeError, ValueError):
                p["print_progress"] = None
            
            p["remain_time"] = info.get("RemainTime")
            
        elif machine_status_name == "PAUSED":
            p["print_status"] = "PAUSED"
            
        elif machine_status_name == "IDLE":
            finished = prev == "PRINTING"  # Just completed a job
            p["print_status"] = None
            p["current_file"] = None
            p["print_progress"] = None
            p["remain_time"] = None
    
    # Emit status update to all clients
    from app import socketio
    socketio.emit("printer_status", {
        "id": pid,
        "status": printers[pid]["status"],
        "machine_status": printers[pid]["machine_status"],
        "print_status": printers[pid]["print_status"],
        "print_progress": printers[pid]["print_progress"],
        "current_file": printers[pid]["current_file"],
        "remain_time": printers[pid]["remain_time"],
    })
    
    # Auto-start next in queue after completion
    if finished:
        _start_next(pid)


def _on_attributes(pid: str, packet: Dict[str, Any]):
    """Process printer attributes messages."""
    attrs = packet.get("Attributes", {})
    
    with printer_lock:
        # Update printer attributes
        printers[pid].update({
            "resolution": attrs.get("Resolution"),
            "build_volume": attrs.get("XYZsize"),
            "camera_status": attrs.get("CameraStatus") == 1,
        })
    
    # Emit attributes update to all clients
    from app import socketio
    socketio.emit("printer_attributes", {"id": pid, "attributes": attrs})


def _on_response(pid: str, packet: Dict[str, Any]):
    """Process printer response messages."""
    cmd_data = packet.get("Data", {})
    cmd = cmd_data.get("Cmd")
    response_data = cmd_data.get("Data", {})
    
    # Process file list response
    if cmd == CMD["FILE_LIST"]:
        url = response_data.get("Url", "/local")
        with printer_lock:
            # Fix: Use FileList from response_data
            printers[pid]["files"][url] = response_data.get("FileList", [])
    
    # Emit response to all clients
    from app import socketio
    socketio.emit("printer_response", {
        "id": pid,
        "cmd": cmd,
        "data": response_data
    })


def _on_error(pid: str, packet: Dict[str, Any]):
    """Process printer error messages."""
    error_data = packet.get("Data", {}).get("Data", {})
    error_code = error_data.get("ErrorCode")
    error_str = error_data.get("ErrorStr", f"Error code: {error_code}")
    
    logger.error(f"Printer error ({pid}): {error_str}")
    
    # Emit error to all clients
    from app import socketio
    socketio.emit("printer_error", {
        "id": pid,
        "error_code": error_code,
        "error_message": error_str
    })


def _on_notice(pid: str, packet: Dict[str, Any]):
    """Process printer notice messages."""
    notice_data = packet.get("Data", {}).get("Data", {})
    message = notice_data.get("Message", "Notification from printer")
    
    logger.info(f"Printer notice ({pid}): {message}")
    
    # Emit notice to all clients
    from app import socketio
    socketio.emit("printer_notice", {
        "id": pid,
        "message": message
    })


# ============================================================================
# Job‑queue helpers
# ----------------------------------------------------------------------------

def queue_print(pid: str, filename: str):
    """Enqueue *filename*; start immediately if printer idle."""
    with printer_lock:
        if printers[pid]["machine_status"] not in ("PRINTING", "PAUSED"):
            # Idle → print immediately
            logger.info(f"Queue empty, starting {filename} on {pid}")
            _ws_send(pid, "START_PRINT", {"Filename": filename, "StartLayer": 0})
        else:
            # Add to queue
            job_queues[pid].append(filename)
            logger.info(f"Queued {filename} on {pid} (len={len(job_queues[pid])})")
    
    _broadcast_queue(pid)


def _start_next(pid: str):
    """Start the next print job in the queue."""
    with printer_lock:
        if job_queues[pid]:
            nxt = job_queues[pid].pop(0)
            logger.info(f"Auto‑starting next job {nxt} on {pid}")
            _ws_send(pid, "START_PRINT", {"Filename": nxt, "StartLayer": 0})
    
    _broadcast_queue(pid)


def _broadcast_queue(pid: str):
    """Broadcast current queue status to clients."""
    from app import socketio
    socketio.emit("printer_queue", {"id": pid, "queue": list(job_queues[pid])})
    
    if not job_queues[pid]:
        socketio.emit("queue_empty", {"id": pid})


# ============================================================================
# Public API wrappers
# ----------------------------------------------------------------------------

def get_printer_status(pid: str) -> bool:
    """Request printer status."""
    return _ws_send(pid, "STATUS")


def get_printer_attributes(pid: str) -> bool:
    """Request printer attributes."""
    return _ws_send(pid, "ATTRIBUTES")


def get_printer_files(pid: str, url: str = "/local") -> bool:
    """Request printer files."""
    return _ws_send(pid, "FILE_LIST", {"Url": url})


def start_print(pid: str, filename: str) -> bool:
    """Start a print job."""
    return _ws_send(pid, "START_PRINT", {"Filename": filename, "StartLayer": 0})


def pause_print(pid: str) -> bool:
    """Pause a print job."""
    return _ws_send(pid, "PAUSE_PRINT")


def resume_print(pid: str) -> bool:
    """Resume a paused print job."""
    return _ws_send(pid, "RESUME_PRINT")


def stop_print(pid: str) -> bool:
    """Stop a print job."""
    return _ws_send(pid, "STOP_PRINT")


def delete_file(pid: str, filename: str) -> bool:
    """Delete a file from the printer."""
    return _ws_send(pid, "DELETE_FILE", {"FileList": [filename]})


def set_camera_status(pid: str, enable: bool = True) -> bool:
    """Enable or disable the camera."""
    return _ws_send(pid, "CAMERA_CONTROL", {"Enable": 1 if enable else 0})


def rename_printer(pid: str, new_name: str) -> bool:
    """Rename a printer."""
    result = _ws_send(pid, "RENAME_PRINTER", {"Name": new_name})
    
    if result and pid in printers:
        with printer_lock:
            printers[pid]['name'] = new_name
    
    return result


# ============================================================================
# Upload and diagnostics utilities
# ----------------------------------------------------------------------------

def upload_file_to_printer(task_id: str, pid: str, filepath: str):
    """
    Upload a file to the printer.
    
    Args:
        task_id (str): Upload task ID
        pid (str): Printer ID
        filepath (str): Path to file
    """
    if pid not in printers:
        logger.error(f"Cannot upload file to printer {pid}: not found")
        update_upload_progress(task_id, 0, "error", f"Printer {pid} not found")
        return

    printer = printers[pid]

    # Verify file exists
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        update_upload_progress(task_id, 0, "error", "File not found")
        return

    # Calculate MD5 hash
    try:
        md5_hash = hashlib.md5()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                md5_hash.update(byte_block)
    except Exception as e:
        logger.error(f"Error calculating MD5 hash: {e}")
        update_upload_progress(task_id, 0, "error", f"File read error: {str(e)}")
        return

    file_stats = os.stat(filepath)
    filename = os.path.basename(filepath)

    # Upload parameters
    post_data = {
        'S-File-MD5': md5_hash.hexdigest(),
        'Check': 1,
        'Offset': 0,
        'Uuid': str(uuid.uuid4()),
        'TotalSize': file_stats.st_size,
    }

    url = f'http://{printer["ip"]}:3030/uploadFile/upload'
    num_parts = (int)(file_stats.st_size / CHUNK_SIZE)
    logger.info(f"Uploading file {filename} to printer {printer['name']} in {num_parts} parts")

    # Update progress
    update_upload_progress(task_id, 0, "uploading", f"Starting upload to {printer['name']}")

    # Upload parts
    try:
        # For Elegoo Saturn Ultra 16K - special handling
        if "saturnultra16k" in printer.get('model', '').lower() or "saturn" in printer.get('model', '').lower() and "16k" in printer.get('model', '').lower():
            logger.info(f"Using special upload handling for Saturn Ultra 16K")
            # Some Elegoo printers need specific headers
            extra_headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': '*/*'
            }
        else:
            extra_headers = {}

        with tqdm(total=num_parts, desc=f"Uploading {filename}") as pbar:
            for i in range(num_parts + 1):
                offset = i * CHUNK_SIZE
                progress = round(i / (num_parts + 1) * 100)

                # Update progress
                update_upload_progress(
                    task_id, progress, "uploading", f"Uploading part {i}/{num_parts}")

                with open(filepath, 'rb') as f:
                    f.seek(offset)
                    file_part = f.read(CHUNK_SIZE)

                    if not upload_file_part(url, post_data, filename, file_part, offset, extra_headers):
                        logger.error(f"Failed to upload part {i}/{num_parts} of file {filename}")
                        update_upload_progress(task_id, progress, "error", "Upload failed")
                        break

                pbar.update(1)

        # Cleanup
        os.remove(filepath)

        # Update progress
        update_upload_progress(task_id, 100, "complete", "Upload complete")

        # Refresh file list
        get_printer_files(pid, '/local')

        logger.info(f"File {filename} uploaded successfully to printer {printer['name']}")

    except Exception as e:
        logger.error(f"Error uploading file {filename} to printer {printer['name']}: {e}")
        update_upload_progress(task_id, 0, "error", str(e))

        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)


def upload_file_part(url: str, post_data: dict, file_name: str, file_part: bytes, offset: int, 
                   extra_headers: Optional[dict] = None) -> bool:
    """
    Upload a part of a file to the printer.
    
    Args:
        url (str): Upload URL
        post_data (dict): POST data
        file_name (str): File name
        file_part (bytes): File part data
        offset (int): File offset
        extra_headers (dict, optional): Additional headers
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Set offset
        post_data['Offset'] = offset

        # Create multipart form data
        post_files = {'File': (file_name, file_part)}

        # Set headers
        headers = {}
        if extra_headers:
            headers.update(extra_headers)

        # Send request with retry mechanism
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Send request
                response = requests.post(
                    url, data=post_data, files=post_files, headers=headers, timeout=10)
                response.raise_for_status()

                # Parse response
                try:
                    status = response.json()

                    if status.get('success'):
                        return True
                    else:
                        logger.error(f"Upload failed: {status}")
                        return False
                except ValueError:
                    # Some printers don't return JSON
                    if response.status_code == 200:
                        return True
                    else:
                        logger.error(
                            f"Upload failed: Non-JSON response with status {response.status_code}")
                        return False

            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"Upload attempt {retry_count} failed: {e}")
                if retry_count >= max_retries:
                    logger.error(f"Upload failed after {max_retries} attempts")
                    return False
                # Wait before retrying
                time.sleep(2)

    except Exception as e:
        logger.error(f"Error uploading file part: {e}")
        return False


def update_upload_progress(task_id: str, progress: int, status: str, message: str = ""):
    """
    Update upload progress.
    
    Args:
        task_id (str): Upload task ID
        progress (int): Progress percentage (0-100)
        status (str): Status string (starting, uploading, complete, error)
        message (str, optional): Progress message
    """
    if task_id not in upload_progress:
        logger.warning(f"Cannot update progress for unknown task {task_id}")
        return

    with printer_lock:
        upload_progress[task_id].update({
            'progress': progress,
            'status': status,
            'message': message,
            'updated_at': time.time()
        })

    # Emit progress to all clients
    from app import socketio
    socketio.emit('upload_progress', upload_progress[task_id])


def debug_printer_connection(ip: str) -> dict:
    """
    Debug printer connection issues.
    
    Args:
        ip (str): Printer IP address
        
    Returns:
        dict: Diagnostic results
    """
    try:
        logger.info(f"Testing connection to printer at {ip}")
        results = {
            "ping": {"status": "not_tested", "message": ""},
            "http": {"status": "not_tested", "message": ""},
            "websocket": {"status": "not_tested", "message": ""},
            "overall": {"status": "not_tested", "message": ""}
        }

        # Test ping
        try:
            logger.info(f"Pinging {ip}...")
            ping_result = subprocess.run(['ping', '-c', '2', '-W', '2', ip],
                                        capture_output=True, text=True)
            if ping_result.returncode == 0:
                results["ping"]["status"] = "success"
                results["ping"]["message"] = "Ping successful"
                logger.info(f"Ping successful")
            else:
                results["ping"]["status"] = "failed"
                results["ping"]["message"] = "Ping failed"
                logger.warning(f"Ping failed: {ping_result.stderr}")
        except Exception as ping_err:
            results["ping"]["status"] = "error"
            results["ping"]["message"] = f"Error: {str(ping_err)}"
            logger.error(f"Ping error: {ping_err}")

        # Test HTTP connection
        try:
            http_url = f"http://{ip}:3030/"
            logger.info(f"Testing HTTP connection to {http_url}")
            response = requests.get(http_url, timeout=5)
            results["http"]["status"] = "success" if response.status_code < 400 else "failed"
            results["http"]["message"] = f"HTTP status: {response.status_code}"
            logger.info(f"HTTP response: {response.status_code}")
        except Exception as http_err:
            results["http"]["status"] = "error"
            results["http"]["message"] = f"Error: {str(http_err)}"
            logger.error(f"HTTP connection failed: {http_err}")

        # Test WebSocket connection
        try:
            ws_url = f"ws://{ip}:3030/websocket"
            logger.info(f"Testing WebSocket connection to {ws_url}")
            websocket.setdefaulttimeout(10)
            ws = websocket.create_connection(ws_url)
            results["websocket"]["status"] = "success"
            results["websocket"]["message"] = "WebSocket connection successful"
            logger.info("WebSocket connection successful")
            ws.close()
        except Exception as ws_err:
            results["websocket"]["status"] = "error"
            results["websocket"]["message"] = f"Error: {str(ws_err)}"
            logger.error(f"WebSocket connection failed: {ws_err}")

        # Determine overall status
        if results["ping"]["status"] == "success" and (
           results["http"]["status"] == "success" or
           results["websocket"]["status"] == "success"):
            results["overall"]["status"] = "success"
            results["overall"]["message"] = "Printer is reachable"
        elif results["ping"]["status"] == "success":
            results["overall"]["status"] = "partial"
            results["overall"]["message"] = "Printer is reachable but SDCP services are not responding"
        else:
            results["overall"]["status"] = "failed"
            results["overall"]["message"] = "Printer is not reachable"

        return results

    except Exception as e:
        logger.error(f"Debug connection error: {e}")
        return {
            "ping": {"status": "error", "message": "Test failed"},
            "http": {"status": "error", "message": "Test failed"},
            "websocket": {"status": "error", "message": "Test failed"},
            "overall": {"status": "error", "message": f"Error during diagnostics: {str(e)}"}
        }
    

def connect_printers():
    """Connect to all printers in the registry."""
    connected = 0
    for printer_id in list(printers.keys()):
        if connect_printer(printer_id):
            connected += 1
    
    logger.info(f"Connected to {connected}/{len(printers)} printers")
    return connected

def remove_printer(printer_id: str) -> bool:
    """
    Remove a printer from the system.
    
    Args:
        printer_id (str): Printer ID to remove
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if printer exists
        if printer_id not in printers:
            logger.warning(f"Attempt to remove non-existent printer: {printer_id}")
            return False
            
        # Close any active WebSocket connection
        if printer_id in websockets:
            try:
                websockets[printer_id].close()
            except Exception as ws_err:
                logger.warning(f"Error closing WebSocket for printer {printer_id}: {ws_err}")
            del websockets[printer_id]
        
        # Remove from any job queues
        if printer_id in job_queues:
            del job_queues[printer_id]
        
        # Get printer info for logging
        printer_name = printers[printer_id].get('name', 'Unknown printer')
        
        # Remove printer from in-memory registry
        del printers[printer_id]
        
        logger.info(f"Printer {printer_name} (ID: {printer_id}) removed successfully")
        
        # Emit socket event
        from app import socketio
        socketio.emit('printer_removed', {'id': printer_id, 'name': printer_name})
        
        return True
    except Exception as e:
        logger.error(f"Error removing printer {printer_id}: {e}")
        return False
    
def get_interfaces() -> List[Dict[str,str]]:
    """
    Try netifaces for true broadcast addresses; 
    otherwise auto-derive from your host’s LAN IPs.
    """
    try:
        import netifaces
        interfaces = []
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for addr in addrs:
                if addr.get('broadcast'):
                    interfaces.append({
                        'name': iface,
                        'ip': addr['addr'],
                        'broadcast': addr['broadcast']
                    })
        if interfaces:
            return interfaces
    except Exception:
        pass

    # Fallback: probe any RFC1918 class-C you’re on
    host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
    subnets = {
        ip.rsplit('.',1)[0] + '.255'
        for ip in host_ips
        if ip.startswith(('10.', '192.168.', '172.'))
    }
    return [{'name': 'auto', 'ip': '0.0.0.0', 'broadcast': bc} for bc in subnets]


def scan_broadcast(iface: Dict[str,str], timeout: float, discovered: Dict[str,str], lock: threading.Lock):
    """
    Send UDP discovery on one broadcast address, collect JSON beacons,
    retrying once if nothing comes back.
    """
    for attempt in range(1, 3):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(timeout)
                sock.bind((iface['ip'], 0))
                sock.sendto(UDP_MSG, (iface['broadcast'], UDP_DISCOVERY_PORT))

                start = time.time()
                while time.time() - start < timeout:
                    try:
                        raw, addr = sock.recvfrom(8192)
                        payload = json.loads(raw.decode('utf-8'))
                        pid = (payload.get('Data', {}) .get('MainboardID')
                               or payload.get('Data', {}) .get('Attributes', {}) .get('MainboardID'))
                        if pid:
                            with lock:
                                if pid not in discovered:
                                    discovered[pid] = addr[0]
                    except socket.timeout:
                        break
                    except Exception:
                        continue

            # if we found at least one, no need to retry
            if discovered:
                return
        except Exception:
            continue