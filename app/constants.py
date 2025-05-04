"""
Constants used throughout the ChitUI application.
"""

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {'ctb', 'goo', 'prz'}

# Machine statuses
MACHINE_STATUS = {
    0: {"name": "IDLE",             "description": "Idle"},
    1: {"name": "PRINTING",         "description": "Executing print task"},
    2: {"name": "PAUSED",           "description": "Suspended"},
    3: {"name": "STOPPED",          "description": "Stopped"},
    4: {"name": "HOMING",           "description": "Resetting"},
    5: {"name": "DROPPING",         "description": "Descending"},
    6: {"name": "LIFTING",          "description": "Lifting"},
    7: {"name": "EXPOSING",         "description": "Exposing"},
    8: {"name": "FILE_TRANSFER",    "description": "File transfer in progress"},
    9: {"name": "EXPOSURE_TEST",    "description": "Exposure test in progress"},
    10: {"name": "DEVICE_CHECK",    "description": "Device self‑check in progress"},
    11: {"name": "UNKNOWN",         "description": "Unknown / reserved"},
}

# Print statuses
PRINT_STATUS = {
    0: {"name": "IDLE",          "description": "Idle"},
    1: {"name": "HOMING",        "description": "Resetting"},
    2: {"name": "DROPPING",      "description": "Descending"},
    3: {"name": "EXPOSING",      "description": "Exposing"},
    4: {"name": "LIFTING",       "description": "Lifting"},
    5: {"name": "PAUSING",       "description": "Executing pause action"},
    6: {"name": "PAUSED",        "description": "Suspended"},
    7: {"name": "STOPPING",      "description": "Executing stop action"},
    8: {"name": "STOPPED",       "description": "Stopped"},
    9: {"name": "COMPLETE",      "description": "Print complete"},
    10: {"name": "FILE_CHECK",   "description": "File checking in progress"},
}

# Print errors
PRINT_ERROR = {
    0: {"name": "NONE", "description": "Normal"},
    1: {"name": "CHECK", "description": "File MD5 Check Failed"},
    2: {"name": "FILEIO", "description": "File Read Failed"},
    3: {"name": "INVLAID_RESOLUTION", "description": "Resolution Mismatch"},
    4: {"name": "UNKNOWN_FORMAT", "description": "Format Mismatch"},
    5: {"name": "UNKNOWN_MODEL", "description": "Machine Model Mismatch"}
}

# File transfer
FILE_TRANSFER = {
    0: {"name": "ACK_SUCCESS", "description": "Success"},
    1: {"name": "ACK_NOT_TRANSFER", "description": "The printer is not currently transferring files."},
    2: {"name": "ACK_CHECKING", "description": "The printer is already in the file verification phase."},
    3: {"name": "ACK_NOT_FOUND", "description": "File not found."}
}

# Print control
PRINT_CTRL = {
    0: {"name": "ACK_OK", "description": "OK"},
    1: {"name": "ACK_BUSY", "description": "Busy"},
    2: {"name": "ACK_NOT_FOUND", "description": "File Not Found"},
    3: {"name": "ACK_MD5_FAILED", "description": "MD5 Verification Failed"},
    4: {"name": "ACK_FILEIO_FAILED", "description": "File Read Failed"},
    5: {"name": "ACK_INVLAID_RESOLUTION", "description": "Resolution Mismatch"},
    6: {"name": "ACK_UNKNOW_FORMAT", "description": "Unrecognized File Format"},
    7: {"name": "ACK_UNKNOW_MODEL", "description": "Machine Model Mismatch"}
}

# Commands
CMD = {
    "STATUS": 0,
    "ATTRIBUTES": 1,
    "START_PRINT": 128,
    "PAUSE_PRINT": 129,
    "STOP_PRINT": 130,
    "RESUME_PRINT": 131,
    "STOP_FEEDING": 132,
    "SKIP_PREHEATING": 133,
    "CHANGE_PRINTER_NAME": 192,
    "TERMINATE_FILE_TRANSFER": 255,
    "FILE_LIST": 258,
    "BATCH_DELETE_FILES": 259,
    "TASK_HISTORY": 320,
    "TASK_DETAILS": 321,
    "VIDEO_STREAM": 386,
    "TIMELAPSE": 387,
}

# Printer models that support camera streaming
CAMERA_ENABLED_MODELS = {
    "saturnultra16k": {
        "snapshot": "http://{ip}:8899/snapshot",
        "mjpeg":     "http://{ip}:8899/stream",
        "resolution": "1280x720",
        "fps": 15,
    },
    # Elegoo Saturn Ultra 14 K – same camera API but different model string
    "saturnultra14k": {
        "snapshot": "http://{ip}:8899/snapshot",
        "mjpeg":     "http://{ip}:8899/stream",
        "resolution": "1280x720",
        "fps": 15,
    },
    "saturn4ultra": {
        "snapshot": "http://{ip}:8899/snapshot",
        "mjpeg":     "http://{ip}:8899/stream",
        "resolution": "1280x720",
        "fps": 15,
    },
    "saturn4": {
        "snapshot": "http://{ip}:8899/snapshot",
        "mjpeg":     "http://{ip}:8899/stream",
        "resolution": "1280x720",
        "fps": 15,
    },
    "saturn3ultra": {
        "snapshot": "http://{ip}:8899/snapshot",
        "mjpeg":     "http://{ip}:8899/stream",
        "resolution": "1280x720",
        "fps": 15,
    },
}

# Printer icons mapping
PRINTER_ICONS = {
    "elegoo_saturn4ultra":   "/static/img/elegoo_saturn4ultra.webp",
    "elegoo_saturn4":        "/static/img/elegoo_saturn4ultra.webp",
    "elegoo_saturn3ultra":   "/static/img/elegoo_saturn4ultra.webp",
    "elegoo_saturnultra16k": "/static/img/elegoo_saturn4ultra.webp",
    "elegoo_saturnultra14k": "/static/img/elegoo_saturn4ultra.webp",
    "default":               "/static/img/default_printer.png",
}