"""
WebSocket event handlers for ChitUI
"""
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from loguru import logger
from threading import Thread
import time
from app import printers, upload_progress
from app.printer_manager import (
    discover_printers, connect_printers, connect_printer, 
    get_printer_status, get_printer_attributes, get_printer_files,
    start_print, pause_print, resume_print, stop_print, delete_file,
    set_camera_status, rename_printer
)


def register_handlers(socketio):
    """Register all SocketIO event handlers."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection event."""
        if not current_user.is_authenticated:
            return False  # Reject connection
        
        logger.info(f"Client connected: {current_user.username}")
        emit('printers', printers)
        
        # Send active uploads
        for task_id, task in upload_progress.items():
            if task['status'] not in ['complete', 'error'] or task['progress'] < 100:
                emit('upload_progress', task)
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection event."""
        if current_user.is_authenticated:
            logger.info(f"Client disconnected: {current_user.username}")
    
    @socketio.on('printers')
    def handle_printers_request(data=None):
        """Handle printers list request."""
        logger.info(f"Client requested printer discovery: {current_user.username}")
        
        # Start discovery in a separate thread
        Thread(target=discovery_task, daemon=True).start()
    
    @socketio.on('scan_lan')
    def handle_scan_lan(data):
        """Handle LAN scan request."""
        timeout = data.get('timeout', 3)
        logger.info(f"Client requested LAN scan with timeout: {timeout}s")
        
        # Start scan in a separate thread
        Thread(target=lambda: lan_scan_task(timeout, socketio), daemon=True).start()
    
    @socketio.on('printer_info')
    def handle_printer_info(data):
        """Handle printer info request."""
        printer_id = data.get('id')
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested info for unknown printer: {printer_id}")
            return
        
        logger.debug(f"Client requested info for printer: {printer_id}")
        get_printer_status(printer_id)
        get_printer_attributes(printer_id)
    
    @socketio.on('printer_files')
    def handle_printer_files(data):
        """Handle printer files request."""
        printer_id = data.get('id')
        url = data.get('url', '/local')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested files for unknown printer: {printer_id}")
            return
        
        logger.debug(f"Client requested files for printer: {printer_id}, url: {url}")
        get_printer_files(printer_id, url)
    
    @socketio.on('action_print')
    def handle_action_print(data):
        """Handle print action request."""
        printer_id = data.get('id')
        filename = data.get('data')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested print action for unknown printer: {printer_id}")
            return
        
        if not filename:
            logger.warning(f"Client requested print action with no filename")
            return
        
        logger.info(f"Client requested print action: {printer_id}, file: {filename}")
        start_print(printer_id, filename)
    
    @socketio.on('action_pause')
    def handle_action_pause(data):
        """Handle pause action request."""
        printer_id = data.get('id')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested pause action for unknown printer: {printer_id}")
            return
        
        logger.info(f"Client requested pause action: {printer_id}")
        pause_print(printer_id)
    
    @socketio.on('action_resume')
    def handle_action_resume(data):
        """Handle resume action request."""
        printer_id = data.get('id')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested resume action for unknown printer: {printer_id}")
            return
        
        logger.info(f"Client requested resume action: {printer_id}")
        resume_print(printer_id)
    
    @socketio.on('action_stop')
    def handle_action_stop(data):
        """Handle stop action request."""
        printer_id = data.get('id')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested stop action for unknown printer: {printer_id}")
            return
        
        logger.info(f"Client requested stop action: {printer_id}")
        stop_print(printer_id)
    
    @socketio.on('action_delete')
    def handle_action_delete(data):
        """Handle delete action request."""
        printer_id = data.get('id')
        filename = data.get('data')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested delete action for unknown printer: {printer_id}")
            return
        
        if not filename:
            logger.warning(f"Client requested delete action with no filename")
            return
        
        logger.info(f"Client requested delete action: {printer_id}, file: {filename}")
        delete_file(printer_id, filename)
    
    @socketio.on('action_camera')
    def handle_action_camera(data):
        """Handle camera action request."""
        printer_id = data.get('id')
        enable = data.get('enable', True)
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested camera action for unknown printer: {printer_id}")
            return
        
        logger.info(f"Client requested camera action: {printer_id}, enable: {enable}")
        set_camera_status(printer_id, enable)
    
    @socketio.on('action_rename')
    def handle_action_rename(data):
        """Handle rename action request."""
        printer_id = data.get('id')
        name = data.get('name')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested rename action for unknown printer: {printer_id}")
            return
        
        if not name:
            logger.warning("Client requested rename action with no name")
            return
        
        logger.info(f"Client requested rename action: {printer_id}, new name: {name}")
        rename_printer(printer_id, name)

    @socketio.on('remove_printer')
    def handle_remove_printer(data):
        """Handle printer removal request."""
        printer_id = data.get('id')
        
        if not printer_id or printer_id not in printers:
            logger.warning(f"Client requested removal for unknown printer: {printer_id}")
            emit('printer_removal_result', {
                'success': False,
                'error': 'Printer not found'
            })
            return
        
        logger.info(f"Client requested printer removal: {printer_id}")
        from app.printer_manager import remove_printer
        result = remove_printer(printer_id)
        
        # Send confirmation of action
        if result:
            emit('printer_removal_result', {
                'success': True,
                'printer_id': printer_id
            })
        else:
            emit('printer_removal_result', {
                'success': False,
                'printer_id': printer_id,
                'error': 'Failed to remove printer'
            })


def discovery_task():
    """Run printer discovery in a separate thread."""
    # Discover printers
    discovered = discover_printers()
    
    # Update printers dict
    for printer_id, printer in discovered.items():
        if printer_id not in printers:
            # New printer
            printers[printer_id] = printer
            logger.info(f"New printer discovered: {printer['name']} ({printer['ip']})")
        else:
            # Update existing printer
            current = printers[printer_id]
            current.update({
                'name': printer['name'],
                'ip': printer['ip'],
                'last_seen': printer['last_seen']
            })
            logger.debug(f"Updated printer: {printer['name']} ({printer['ip']})")
    
    # Connect to printers
    connect_printers()
    
    # Emit updated printers list
    from app import socketio
    socketio.emit('printers', printers)


def lan_scan_task(timeout, socketio):
    """Run LAN scan in a separate thread with detailed progress updates."""
    # Emit initial progress
    socketio.emit('scan_progress', {
        'progress': 5,
        'status': 'Initializing network scan...',
        'complete': False
    })
    
    # Start discovery
    try:
        # Give UI time to show
        time.sleep(0.5)
        
        # Scan network interfaces
        socketio.emit('scan_progress', {
            'progress': 10,
            'status': 'Checking network interfaces...',
            'details': 'Finding available network interfaces',
            'complete': False
        })
        
        # Get network interfaces
        try:
            import netifaces
            interfaces = []
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        if 'addr' in addr and 'broadcast' in addr:
                            interfaces.append({
                                'name': iface,
                                'ip': addr['addr'],
                                'broadcast': addr['broadcast']
                            })
            
            # Update progress with interface info
            for i, iface in enumerate(interfaces):
                socketio.emit('scan_progress', {
                    'progress': 15 + i * 5,
                    'details': f"Found interface: {iface['name']} ({iface['ip']})",
                    'complete': False
                })
        except ImportError:
            socketio.emit('scan_progress', {
                'progress': 20,
                'details': 'Using default network configuration',
                'complete': False
            })
        
        # Update progress
        socketio.emit('scan_progress', {
            'progress': 30,
            'status': 'Broadcasting discovery packets...',
            'details': 'Sending UDP broadcast on all interfaces',
            'complete': False
        })
        
        # Run discovery with increased timeout for more thorough scanning
        discovered = discover_printers(timeout=timeout)
        
        # Update progress
        socketio.emit('scan_progress', {
            'progress': 70,
            'status': f'Processing {len(discovered)} found devices...',
            'details': f'Found {len(discovered)} printers on the network',
            'complete': False
        })
        
        # Emit each discovered printer
        for printer_id, printer in discovered.items():
            socketio.emit('printer_discovered', printer)
            time.sleep(0.1)  # Space out the emissions for UI
        
        # Update printers dict
        for printer_id, printer in discovered.items():
            if printer_id not in printers:
                # New printer
                printers[printer_id] = printer
                logger.info(f"New printer discovered: {printer['name']} ({printer['ip']})")
            else:
                # Update existing printer
                current = printers[printer_id]
                current.update({
                    'name': printer['name'],
                    'ip': printer['ip'],
                    'last_seen': printer['last_seen']
                })
                logger.debug(f"Updated printer: {printer['name']} ({printer['ip']})")
        
        # Connect to printers
        socketio.emit('scan_progress', {
            'progress': 85,
            'status': 'Connecting to discovered printers...',
            'details': 'Establishing connections to printers',
            'complete': False
        })
        
        connect_printers()
        
        # Emit final progress
        socketio.emit('scan_progress', {
            'progress': 100,
            'status': f'Scan complete! Found {len(discovered)} printer(s).',
            'details': 'Scan completed successfully',
            'complete': True,
            'success': len(discovered) > 0
        })
        
        # Emit updated printers list
        socketio.emit('printers', printers)
        
    except Exception as e:
        logger.error(f"Error during LAN scan: {e}")
        socketio.emit('scan_progress', {
            'progress': 100,
            'status': f'Error during scan: {str(e)}',
            'details': f'Exception: {str(e)}',
            'complete': True,
            'success': False
        })

