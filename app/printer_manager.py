"""
Printer management module for ChitUI
"""
import socket
import json
import time
import os
import hashlib
import uuid
import websocket
import requests
from threading import Thread, Lock
from loguru import logger
from tqdm import tqdm
from app import printers, websockets, upload_progress
from app.constants import MACHINE_STATUS, PRINTER_ICONS, CAMERA_ENABLED_MODELS

import logging
logging.basicConfig(
    level=logging.DEBUG,  # Or logging.INFO for less verbose logging
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler('printer_debug.log'),
        logging.StreamHandler()
    ]
)


# Lock to prevent race conditions when accessing shared resources
printer_lock = Lock()


def discover_printers(timeout=1):
    """
    Discover 3D printers on the network using UDP broadcast.

    Args:
        timeout (int): Discovery timeout in seconds

    Returns:
        dict: Dictionary of discovered printers
    """
    logger.info("Starting printer discovery")

    msg = b'M99999'
    try:
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.bind(('', 54781))
        sock.sendto(msg, ("255.255.255.255", 3000))

        discovered = {}

        try:
            # Use tqdm for progress display during discovery
            with tqdm(desc="Discovering printers", unit="printer") as pbar:
                while True:
                    try:
                        data = sock.recv(8192)
                        printer = process_discovery_response(data)
                        if printer:
                            discovered[printer['id']] = printer
                            pbar.update(1)
                    except socket.timeout:
                        break
        finally:
            sock.close()

        logger.info(f"Discovery completed: {len(discovered)} printers found")
        return discovered

    except Exception as e:
        logger.error(f"Error during printer discovery: {e}")
        return {}


def process_discovery_response(data):
    """
    Process discovery response data and extract printer information.

    Args:
        data (bytes): Raw response data

    Returns:
        dict: Printer information dictionary or None on error
    """
    try:
        j = json.loads(data.decode('utf-8'))

        # Extract printer information
        printer = {
            'id': j['Data']['MainboardID'],
            'connection': j['Id'],
            'name': j['Data']['Name'],
            'model': j['Data']['MachineName'].lower(),
            'brand': j['Data']['BrandName'].lower(),
            'ip': j['Data']['MainboardIP'],
            'protocol': j['Data']['ProtocolVersion'],
            'firmware': j['Data']['FirmwareVersion'],
            'status': 'disconnected',
            'last_seen': time.time(),
            'machine_status': None,
            'print_status': None,
            'files': [],
            'print_progress': None,
            'current_file': None,
            'remain_time': None,
            'supports_camera': False,
        }

        # Set printer icon
        icon_key = f"{printer['brand']}_{printer['model']}".replace(" ", "")
        printer['icon'] = PRINTER_ICONS.get(icon_key, PRINTER_ICONS['default'])

        # Check if model supports camera
        for model in CAMERA_ENABLED_MODELS:
            if model in printer['model'].lower():
                printer['supports_camera'] = True
                printer['camera_config'] = CAMERA_ENABLED_MODELS[model]
                break

        logger.info(f"Discovered printer: {printer['name']} ({printer['ip']})")
        return printer

    except Exception as e:
        logger.error(f"Error processing discovery response: {e}")
        return None


def add_printer_manually(name, ip, model="unknown", brand="unknown"):
    """
    Add a printer manually by IP address.

    Args:
        name (str): Printer name
        ip (str): Printer IP address
        model (str): Printer model (optional)
        brand (str): Printer brand (optional)

    Returns:
        dict: Printer information or None on error
    """
    # Generate a unique ID for the printer
    printer_id = hashlib.md5(ip.encode('utf-8')).hexdigest()

    printer = {
        'id': printer_id,
        'connection': f"manual_{uuid.uuid4().hex[:8]}",
        'name': name,
        'model': model.lower(),
        'brand': brand.lower(),
        'ip': ip,
        'protocol': "unknown",
        'firmware': "unknown",
        'status': 'disconnected',
        'last_seen': time.time(),
        'machine_status': None,
        'print_status': None,
        'files': [],
        'print_progress': None,
        'current_file': None,
        'remain_time': None,
        'manually_added': True,
        'supports_camera': False,
    }

    # Set printer icon based on brand and model
    icon_key = f"{printer['brand']}_{printer['model']}".replace(" ", "")
    printer['icon'] = PRINTER_ICONS.get(icon_key, PRINTER_ICONS['default'])

    # Check if model supports camera
    for model_name in CAMERA_ENABLED_MODELS:
        if model_name in printer['model'].lower():
            printer['supports_camera'] = True
            printer['camera_config'] = CAMERA_ENABLED_MODELS[model_name]
            break

    # Try to connect to the printer to validate with more robust error handling
    connection_successful = False
    error_message = None

    # Try multiple connection methods
    try:
        # First try WebSocket connection
        logger.info(
            f"Attempting WebSocket connection to printer: {name} ({ip})")
        url = f"ws://{ip}:3030/websocket"
        websocket.setdefaulttimeout(10)

        try:
            ws = websocket.create_connection(url)
            ws.close()
            connection_successful = True
            logger.info(
                f"WebSocket connection successful to printer: {name} ({ip})")
        except Exception as ws_error:
            # WebSocket failed, try HTTP connection
            logger.warning(f"WebSocket connection failed: {ws_error}")
            logger.info(
                f"Attempting HTTP connection to printer: {name} ({ip})")

            try:
                http_url = f"http://{ip}:3030/"
                response = requests.get(http_url, timeout=5)
                if response.status_code < 400:
                    connection_successful = True
                    logger.info(
                        f"HTTP connection successful to printer: {name} ({ip})")
                else:
                    error_message = f"HTTP request failed with status {response.status_code}"
                    logger.error(error_message)
            except Exception as http_error:
                # HTTP failed, try a ping
                logger.warning(f"HTTP connection failed: {http_error}")
                logger.info(f"Attempting to ping printer: {name} ({ip})")

                try:
                    import subprocess
                    ping_result = subprocess.run(['ping', '-c', '1', '-W', '2', ip],
                                                 capture_output=True, text=True)
                    if ping_result.returncode == 0:
                        connection_successful = True
                        logger.info(
                            f"Ping successful to printer: {name} ({ip})")
                    else:
                        error_message = "Ping failed, printer not reachable"
                        logger.error(error_message)
                except Exception as ping_error:
                    error_message = f"All connection attempts failed: {ping_error}"
                    logger.error(error_message)

        if connection_successful:
            # Add printer to global list
            with printer_lock:
                printers[printer_id] = printer

            # Special handling for Saturn Ultra 16K
            if "saturn" in model.lower() and "16k" in model.lower():
                logger.info(f"Special handling for Saturn Ultra 16K model")
                printer['model'] = "saturnultra16k"
                printer['supports_camera'] = True
                printer['camera_config'] = CAMERA_ENABLED_MODELS.get(
                    "saturnultra16k", {})

            connect_printer(printer_id)
            return printer
        else:
            raise Exception(
                error_message or "Connection failed for unknown reason")

    except Exception as e:
        logger.error(
            f"Failed to connect to manually added printer {name} ({ip}): {e}")
        return None


def connect_printers():
    """
    Connect to all discovered printers.

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Connecting to printers...")

    for printer_id, printer in list(printers.items()):
        connect_printer(printer_id)

    return True


def connect_printer(printer_id):
    """
    Connect to a specific printer by ID.

    Args:
        printer_id (str): Printer ID

    Returns:
        bool: True if successful, False otherwise
    """
    if printer_id not in printers:
        logger.error(f"Printer {printer_id} not found")
        return False

    printer = printers[printer_id]
    url = f"ws://{printer['ip']}:3030/websocket"

    logger.info(f"Connecting to printer: {printer['name']} ({url})")

    try:
        websocket.setdefaulttimeout(10)
        ws = websocket.WebSocketApp(
            url,
            on_message=lambda ws, msg: ws_message_handler(ws, msg, printer_id),
            on_open=lambda ws: ws_open_handler(ws, printer_id),
            on_close=lambda ws, status, msg: ws_close_handler(
                ws, status, msg, printer_id),
            on_error=lambda ws, error: ws_error_handler(ws, error, printer_id)
        )

        # Store websocket
        websockets[printer_id] = ws

        # Start websocket in a separate thread
        Thread(target=lambda: ws.run_forever(reconnect=3), daemon=True).start()
        return True

    except Exception as e:
        logger.error(f"Error connecting to printer {printer['name']}: {e}")
        return False


def ws_open_handler(ws, printer_id):
    """
    WebSocket open event handler.

    Args:
        ws (WebSocketApp): WebSocket instance
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        logger.warning(
            f"WebSocket connected for unknown printer: {printer_id}")
        return

    printer = printers[printer_id]
    logger.info(f"Connected to printer: {printer['name']}")

    # Update printer status
    with printer_lock:
        printer['status'] = 'connected'
        printer['last_seen'] = time.time()

    # Request initial status and attributes
    get_printer_status(printer_id)
    get_printer_attributes(printer_id)
    get_printer_files(printer_id, '/local')


def ws_close_handler(ws, status, message, printer_id):
    """
    WebSocket close event handler.

    Args:
        ws (WebSocketApp): WebSocket instance
        status (int): Close status code
        message (str): Close message
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    printer = printers[printer_id]
    logger.info(
        f"Disconnected from printer: {printer['name']}, status: {status}, message: {message}")

    # Update printer status
    with printer_lock:
        printer['status'] = 'disconnected'


def ws_error_handler(ws, error, printer_id):
    """
    WebSocket error event handler.

    Args:
        ws (WebSocketApp): WebSocket instance
        error (Exception): Error object
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    printer = printers[printer_id]
    logger.error(f"WebSocket error for printer {printer['name']}: {error}")


def ws_message_handler(ws, message, printer_id):
    """
    Robust WebSocket message handler with enhanced error logging

    Args:
        ws (WebSocketApp): WebSocket instance
        message (str): Received message
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        logger.warning(f"Received message for unknown printer: {printer_id}")
        return

    try:
        # Parse message with error handling
        try:
            data = json.loads(message)
        except json.JSONDecodeError as json_err:
            logger.error(
                f"Failed to parse JSON message for printer {printer_id}: {json_err}")
            logger.error(f"Problematic message: {message}")
            return

        # Log full message for debugging
        logger.debug(
            f"Received message from printer {printer_id}: {json.dumps(data, indent=2)}")

        # Validate message structure
        if not isinstance(data, dict):
            logger.warning(
                f"Unexpected message format for printer {printer_id}: {type(data)}")
            return

        # Process message topic
        topic = data.get('Topic', '')

        # Extensive error handling for each message type
        try:
            if topic.startswith('sdcp/status/'):
                process_status_message(data, printer_id)
            elif topic.startswith('sdcp/attributes/'):
                process_attributes_message(data, printer_id)
            elif topic.startswith('sdcp/response/'):
                process_response_message(data, printer_id)
            elif topic.startswith('sdcp/error/'):
                process_error_message(data, printer_id)
            elif topic.startswith('sdcp/notice/'):
                process_notice_message(data, printer_id)
            else:
                logger.warning(f"Received unknown message topic: {topic}")

        except Exception as process_err:
            logger.error(
                f"Error processing {topic} message for printer {printer_id}: {process_err}")
            logger.error(
                f"Problematic message data: {json.dumps(data, indent=2)}")

    except Exception as e:
        logger.error(
            f"Unexpected error in WebSocket message handler for printer {printer_id}: {e}")
        logger.error(f"Original message: {message}")


def process_status_message(data, printer_id):
    """
    Robust process_status_message with enhanced error handling

    Args:
        data (dict): Message data
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    # Safely extract status data
    try:
        status_data = data.get('Status', {})

        # Validate status data structure
        if not isinstance(status_data, dict):
            logger.warning(
                f"Invalid status data type for printer {printer_id}: {type(status_data)}")
            return

        # Safe extraction of current status with extensive type handling
        current_status = status_data.get('CurrentStatus')

        # Normalize current_status to a single integer
        machine_status_code = 0
        if current_status is not None:
            if isinstance(current_status, list):
                # If it's a list, try to get the first element
                try:
                    machine_status_code = int(
                        current_status[0]) if current_status else 0
                except (IndexError, ValueError, TypeError):
                    machine_status_code = 0
            elif isinstance(current_status, (int, str)):
                try:
                    machine_status_code = int(current_status)
                except (ValueError, TypeError):
                    machine_status_code = 0

        # Thread-safe update of printer status
        with printer_lock:
            # Get machine status name safely
            machine_status_name = MACHINE_STATUS.get(
                machine_status_code,
                {'name': 'UNKNOWN'}
            )['name']

            printers[printer_id]['machine_status'] = machine_status_name

            # Process print info
            print_info = status_data.get('PrintInfo', {})

            # Only process print info if printing
            if print_info and machine_status_code == 1:  # PRINTING
                # Safe extraction of print information
                printers[printer_id]['print_status'] = print_info.get(
                    'PrintStatus')
                printers[printer_id]['current_file'] = print_info.get(
                    'Filename')

                # Calculate progress safely
                try:
                    layer = int(print_info.get('Layer', 0))
                    total_layers = int(print_info.get('TotalLayer', 1))
                    progress = round((layer / total_layers) *
                                     100) if total_layers > 0 else 0
                    printers[printer_id]['print_progress'] = progress
                except (TypeError, ValueError):
                    printers[printer_id]['print_progress'] = None

                # Set remaining time
                try:
                    remain_time = int(print_info.get('RemainTime', 0))
                    printers[printer_id]['remain_time'] = remain_time
                except (TypeError, ValueError):
                    printers[printer_id]['remain_time'] = None

            # Reset print-related info if not printing
            elif machine_status_code == 0:  # IDLE
                printers[printer_id]['print_status'] = None
                printers[printer_id]['current_file'] = None
                printers[printer_id]['print_progress'] = None
                printers[printer_id]['remain_time'] = None

        # Emit status update to all clients
        from app import socketio
        socketio.emit('printer_status', {
            'id': printer_id,
            'status': printers[printer_id]['status'],
            'machine_status': printers[printer_id]['machine_status'],
            'print_status': printers[printer_id]['print_status'],
            'print_progress': printers[printer_id]['print_progress'],
            'current_file': printers[printer_id]['current_file'],
            'remain_time': printers[printer_id]['remain_time']
        })

    except Exception as e:
        logger.error(
            f"Unexpected error processing status message for printer {printer_id}: {e}")
        logger.error(f"Full status data: {json.dumps(status_data, indent=2)}")


def process_attributes_message(data, printer_id):
    """
    Process printer attributes message.

    Args:
        data (dict): Message data
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    attributes_data = data.get('Attributes', {})

    # Extract important attributes
    with printer_lock:
        # Resolution
        resolution = attributes_data.get('Resolution', [])
        if resolution and len(resolution) >= 2:
            printers[printer_id]['resolution'] = resolution

        # Build volume
        build_volume = attributes_data.get('XYZsize', [])
        if build_volume and len(build_volume) >= 3:
            printers[printer_id]['build_volume'] = build_volume

        # Camera status
        camera_status = attributes_data.get('CameraStatus', 0)
        printers[printer_id]['camera_status'] = camera_status == 1

    # Emit attributes update to all clients
    from app import socketio
    socketio.emit('printer_attributes', {
        'id': printer_id,
        'attributes': attributes_data
    })


def process_response_message(data, printer_id):
    """
    Process printer response message.

    Args:
        data (dict): Message data
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    cmd_data = data.get('Data', {})
    cmd = cmd_data.get('Cmd')
    response_data = cmd_data.get('Data', {})

    # Process file list response
    if cmd == 258:  # RETRIEVE_FILE_LIST
        file_list = response_data.get('FileList', [])
        url = response_data.get('Url', '')

        # Store file list
        if 'files' not in printers[printer_id]:
            printers[printer_id]['files'] = {}
        printers[printer_id]['files'][url] = file_list

    # Emit response to all clients
    from app import socketio
    socketio.emit('printer_response', {
        'id': printer_id,
        'cmd': cmd,
        'data': response_data
    })


def process_error_message(data, printer_id):
    """
    Process printer error message.

    Args:
        data (dict): Message data
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    error_data = data.get('Data', {}).get('Data', {})
    error_code = error_data.get('ErrorCode')
    error_str = error_data.get('ErrorStr', f"Error code: {error_code}")

    logger.error(f"Printer error ({printer_id}): {error_str}")

    # Emit error to all clients
    from app import socketio
    socketio.emit('printer_error', {
        'id': printer_id,
        'error_code': error_code,
        'error_message': error_str
    })


def process_notice_message(data, printer_id):
    """
    Process printer notice message.

    Args:
        data (dict): Message data
        printer_id (str): Printer ID
    """
    if printer_id not in printers:
        return

    notice_data = data.get('Data', {}).get('Data', {})
    message = notice_data.get('Message', 'Notification from printer')

    logger.info(f"Printer notice ({printer_id}): {message}")

    # Emit notice to all clients
    from app import socketio
    socketio.emit('printer_notice', {
        'id': printer_id,
        'message': message
    })


def get_printer_status(printer_id):
    """
    Request printer status.

    Args:
        printer_id (str): Printer ID

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 0)


def get_printer_attributes(printer_id):
    """
    Request printer attributes.

    Args:
        printer_id (str): Printer ID

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 1)


def get_printer_files(printer_id, url):
    """
    Request printer files.

    Args:
        printer_id (str): Printer ID
        url (str): Path URL ('/local' or '/usb')

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 258, {"Url": url})


def start_print(printer_id, filename):
    """
    Start a print job.

    Args:
        printer_id (str): Printer ID
        filename (str): File name to print

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 128, {"Filename": filename, "StartLayer": 0})


def pause_print(printer_id):
    """
    Pause a print job.

    Args:
        printer_id (str): Printer ID

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 129)


def resume_print(printer_id):
    """
    Resume a paused print job.

    Args:
        printer_id (str): Printer ID

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 131)


def stop_print(printer_id):
    """
    Stop a print job.

    Args:
        printer_id (str): Printer ID

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 130)


def delete_file(printer_id, filename):
    """
    Delete a file from the printer.

    Args:
        printer_id (str): Printer ID
        filename (str): File name to delete

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 259, {"FileList": [filename]})


def set_camera_status(printer_id, enable=True):
    """
    Enable or disable the camera.

    Args:
        printer_id (str): Printer ID
        enable (bool): Whether to enable the camera

    Returns:
        bool: True if successful, False otherwise
    """
    return send_printer_command(printer_id, 386, {"Enable": 1 if enable else 0})


def rename_printer(printer_id, new_name):
    """
    Rename a printer.

    Args:
        printer_id (str): Printer ID
        new_name (str): New printer name

    Returns:
        bool: True if successful, False otherwise
    """
    result = send_printer_command(printer_id, 192, {"Name": new_name})

    if result and printer_id in printers:
        printers[printer_id]['name'] = new_name

    return result


def send_printer_command(printer_id, cmd, data=None):
    """
    Send a command to the printer.

    Args:
        printer_id (str): Printer ID
        cmd (int): Command code
        data (dict, optional): Additional command data

    Returns:
        bool: True if successful, False otherwise
    """
    if printer_id not in printers or printer_id not in websockets:
        logger.error(
            f"Cannot send command to printer {printer_id}: not connected")
        return False

    printer = printers[printer_id]
    ws = websockets[printer_id]

    if not data:
        data = {}

    # Create command payload
    payload = {
        "Id": printer['connection'],
        "Data": {
            "Cmd": cmd,
            "Data": data,
            "RequestID": os.urandom(8).hex(),
            "MainboardID": printer_id,
            "TimeStamp": int(time.time()),
            "From": 0
        },
        "Topic": "sdcp/request/" + printer_id
    }

    try:
        # Send command
        ws.send(json.dumps(payload))
        logger.debug(f"Sent command {cmd} to printer {printer_id}")
        return True
    except Exception as e:
        logger.error(f"Error sending command to printer {printer_id}: {e}")
        return False


def upload_file_to_printer(task_id, printer_id, filepath):
    """
    Upload a file to the printer.

    Args:
        task_id (str): Upload task ID
        printer_id (str): Printer ID
        filepath (str): Path to file
    """
    if printer_id not in printers:
        logger.error(f"Cannot upload file to printer {printer_id}: not found")
        update_upload_progress(task_id, 0, "error",
                               f"Printer {printer_id} not found")
        return

    printer = printers[printer_id]

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
        update_upload_progress(task_id, 0, "error",
                               f"File read error: {str(e)}")
        return

    file_stats = os.stat(filepath)
    filename = os.path.basename(filepath)

    # Upload parameters
    part_size = 1048576  # 1MB chunks
    post_data = {
        'S-File-MD5': md5_hash.hexdigest(),
        'Check': 1,
        'Offset': 0,
        'Uuid': str(uuid.uuid4()),
        'TotalSize': file_stats.st_size,
    }

    url = f'http://{printer["ip"]}:3030/uploadFile/upload'
    num_parts = (int)(file_stats.st_size / part_size)
    logger.info(
        f"Uploading file {filename} to printer {printer['name']} in {num_parts} parts")

    # Update progress
    update_upload_progress(task_id, 0, "uploading",
                           f"Starting upload to {printer['name']}")

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
                offset = i * part_size
                progress = round(i / (num_parts + 1) * 100)

                # Update progress
                update_upload_progress(
                    task_id, progress, "uploading", f"Uploading part {i}/{num_parts}")

                with open(filepath, 'rb') as f:
                    f.seek(offset)
                    file_part = f.read(part_size)

                    if not upload_file_part(url, post_data, filename, file_part, offset, extra_headers):
                        logger.error(
                            f"Failed to upload part {i}/{num_parts} of file {filename}")
                        update_upload_progress(
                            task_id, progress, "error", "Upload failed")
                        break

                pbar.update(1)

        # Cleanup
        os.remove(filepath)

        # Update progress
        update_upload_progress(task_id, 100, "complete", "Upload complete")

        # Refresh file list
        get_printer_files(printer_id, '/local')

        logger.info(
            f"File {filename} uploaded successfully to printer {printer['name']}")

    except Exception as e:
        logger.error(
            f"Error uploading file {filename} to printer {printer['name']}: {e}")
        update_upload_progress(task_id, 0, "error", str(e))

        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)


def upload_file_part(url, post_data, file_name, file_part, offset, extra_headers=None):
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


def update_upload_progress(task_id, progress, status, message=""):
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


def debug_printer_connection(ip):
    """Debug printer connection issues."""
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
            import subprocess
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
