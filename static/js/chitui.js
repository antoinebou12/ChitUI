/**
 * ChitUI - Frontend JavaScript
 * Handles WebSocket communication with the server and UI interactions
 */

// Global state
let socket = null;
let currentPrinter = null;
let printers = {};
let uploadTasks = {};
let toastUpload = null;
let confirmModal = null;
let addPrinterModal = null;
let cameraInterval = null;
let cameraStreaming = false;

// DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  initSocketIO();
  setupEventListeners();

  // Initialize Bootstrap components
  toastUpload = new bootstrap.Toast(document.getElementById('toastUpload'));
  confirmModal = new bootstrap.Modal(document.getElementById('modalConfirm'));
  addPrinterModal = new bootstrap.Modal(document.getElementById('modalAddPrinter'));

  // Initialize tooltips
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
});

/**
 * Initialize Socket.IO connection
 */
function initSocketIO() {
  socket = io();

  // Connection events
  socket.on('connect', () => {
    console.log('Connected to server');
    setServerStatus(true);
  });

  socket.on('disconnect', () => {
    console.log('Disconnected from server');
    setServerStatus(false);
  });

  // Data events
  socket.on('printers', handlePrinters);
  socket.on('printer_status', handlePrinterStatus);
  socket.on('printer_attributes', handlePrinterAttributes);
  socket.on('printer_response', handlePrinterResponse);
  socket.on('printer_error', handlePrinterError);
  socket.on('printer_notice', handlePrinterNotice);
  socket.on('upload_progress', handleUploadProgress);
}

/**
 * Set up event listeners for UI elements
 */
function setupEventListeners() {
  // Discover button
  document.getElementById('btnScanLAN').addEventListener('click', discoverPrinters);

  // Upload button
  document.getElementById('btnUpload').addEventListener('click', handleUploadClick);

  // Confirm button (in modal)
  document.getElementById('btnConfirm').addEventListener('click', handleConfirmAction);

  // Add printer button
  document.getElementById('btnAddPrinter').addEventListener('click', () => {
    addPrinterModal.show();
  });

  // Add printer form
  document.getElementById('formAddPrinter').addEventListener('submit', handleAddPrinter);

  // Server status icon click (alternative for discover)
  document.querySelector('.serverStatus').addEventListener('click', () => {
    discoverPrinters();
  });

  // Server status icon hover
  document.querySelector('.serverStatus').addEventListener('mouseenter', (e) => {
    if (e.target.classList.contains('bi-cloud-check-fill')) {
      e.target.classList.remove('bi-cloud-check-fill');
      e.target.classList.add('bi-cloud-plus', 'text-primary');
    }
  });

  document.querySelector('.serverStatus').addEventListener('mouseleave', (e) => {
    if (e.target.classList.contains('bi-cloud-plus')) {
      e.target.classList.remove('bi-cloud-plus', 'text-primary');
      e.target.classList.add('bi-cloud-check-fill');
    }
  });
}

/**
 * Send discovery request to server
 */
function discoverPrinters() {
  socket.emit('printers');
  showToast('Discovering printers...', 'info');
}

/**
 * Handle printers data received from server
 */
function handlePrinters(data) {
  printers = data;
  updatePrintersList();

  // Update current printer details if one is selected
  if (currentPrinter && printers[currentPrinter]) {
    displayPrinterDetails(currentPrinter);
  }

  // Update upload count
  updateUploadCount();
}

/**
 * Update the printers list in the sidebar
 */
function updatePrintersList() {
  const printersList = document.getElementById('printersList');
  printersList.innerHTML = '';

  if (Object.keys(printers).length === 0) {
    printersList.innerHTML = '<div class="text-center p-3 text-muted">No printers found</div>';
    return;
  }

  const template = document.getElementById('tmplPrintersListItem');

  Object.entries(printers).forEach(([id, printer]) => {
    const item = template.content.cloneNode(true);

    // Set printer data
    const printerItem = item.querySelector('.printerListItem');
    printerItem.dataset.printerId = id;
    
    // Add event listener for selection
    printerItem.addEventListener('click', (e) => {
      // Prevent click from triggering on delete button
      if (e.target.closest('.btn-delete-printer')) {
        return;
      }
      e.preventDefault();
      selectPrinter(id);
    });

    // Set printer icon with fallback
    const iconImg = item.querySelector('.printerIcon');
    iconImg.src = printer.icon || '/static/img/default_printer.png';
    iconImg.onerror = function () {
      this.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI2NCIgZmlsbD0iI2RlZSIgdmlld0JveD0iMCAwIDE2IDE2Ij48cGF0aCBkPSJNMi41IDhBMi41IDIuNSAwIDEgMSA1IDUuNSAyLjUgMi41IDAgMCAxIDIuNSA4em0wIDBhMi41IDIuNSAwIDEgMSA1IDAgMi41IDIuNSAwIDAgMS01IDB6Ii8+PC9zdmc+';
    };
    iconImg.alt = printer.name;

    // Set printer information
    item.querySelector('.printerName').textContent = printer.name;
    item.querySelector('.printerType').textContent = `${printer.brand} ${printer.model}`;
    item.querySelector('.printerInfo').textContent = printer.ip || 'N/A';

    // Set printer status icon
    const statusIcon = item.querySelector('.printerStatus i');
    if (printer.status === 'connected') {
      statusIcon.className = 'bi bi-circle-fill text-success';
    } else {
      statusIcon.className = 'bi bi-circle-fill text-danger';
    }
    
    // Add delete button
    const headerDiv = item.querySelector('.d-flex.flex-row.align-items-center.justify-content-between');
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-sm btn-outline-danger ms-2 btn-delete-printer';
    deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
    deleteBtn.title = "Remove printer";
    deleteBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      confirmDeletePrinter(id, printer.name);
    });
    headerDiv.appendChild(deleteBtn);

    printersList.appendChild(item);
  });
}

// Add function to confirm printer deletion
function confirmDeletePrinter(printerId, printerName) {
  showConfirmModal('delete-printer', printerName);
  
  // Update the confirm button to handle printer deletion
  const confirmBtn = document.getElementById('btnConfirm');
  confirmBtn.dataset.printerId = printerId;
  
  // Override the existing handler temporarily
  const originalHandler = confirmBtn.onclick;
  confirmBtn.onclick = function() {
    if (confirmBtn.dataset.action === 'delete-printer') {
      deletePrinter(printerId);
    } else {
      // Call original handler for other actions
      if (originalHandler) originalHandler.call(this);
    }
  };
}

// Add function to delete a printer
function deletePrinter(printerId) {
  // Close the modal first
  if (confirmModal) confirmModal.hide();
  
  // Call API to delete printer
  fetch(`/api/printer/${printerId}/remove`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Remove from local cache
      delete printers[printerId];
      
      // Update UI
      updatePrintersList();
      
      // Reset current printer if it was the deleted one
      if (currentPrinter === printerId) {
        currentPrinter = null;
        document.getElementById('printerName').textContent = 'Select a printer';
        document.getElementById('printerType').textContent = '';
        document.getElementById('printerStatus').textContent = '';
        document.getElementById('navTabs').innerHTML = '';
        document.getElementById('navPanes').innerHTML = '';
      }
      
      // Show success message
      showToast(`Printer deleted successfully`, 'success');
    } else {
      showToast(data.error || 'Failed to delete printer', 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showToast('Error deleting printer', 'error');
  });
}

/**
 * Select a printer and display its details
 */
function selectPrinter(printerId) {
  // Highlight selected printer
  document.querySelectorAll('.printerListItem').forEach(item => {
    item.classList.remove('active');
  });
  document.querySelector(`.printerListItem[data-printer-id="${printerId}"]`)?.classList.add('active');

  currentPrinter = printerId;
  document.getElementById('uploadPrinter').value = printerId;

  // Stop camera streaming if we were viewing a different printer
  if (cameraStreaming) {
    stopCameraStream();
  }

  displayPrinterDetails(printerId);

  // Request updated information
  socket.emit('printer_info', { id: printerId });
  socket.emit('printer_files', { id: printerId, url: '/local' });
}


/**
 * Create tabs for printer details
 */
function createTabs(printer) {
  const navTabs = document.getElementById('navTabs');
  const navPanes = document.getElementById('navPanes');

  navTabs.innerHTML = '';
  navPanes.innerHTML = '';

  const tabTemplate = document.getElementById('tmplNavTab');
  const paneTemplate = document.getElementById('tmplNavPane');

  // 1. Status Tab
  const statusTab = tabTemplate.content.cloneNode(true);
  const statusTabBtn = statusTab.querySelector('button');
  statusTabBtn.id = 'status-tab';
  statusTabBtn.dataset.bsTarget = '#status-pane';
  statusTabBtn.classList.add('active');
  statusTabBtn.innerHTML = '<i class="bi bi-info-circle me-1"></i> Status';
  navTabs.appendChild(statusTab);

  const statusPane = paneTemplate.content.cloneNode(true);
  const statusPaneEl = statusPane.querySelector('.tab-pane');
  statusPaneEl.id = 'status-pane';
  statusPaneEl.classList.add('show', 'active');

  const statusTableBody = statusPane.querySelector('tbody');
  statusTableBody.id = 'status-table';
  navPanes.appendChild(statusPane);

  // 2. Files Tab
  const filesTab = tabTemplate.content.cloneNode(true);
  const filesTabBtn = filesTab.querySelector('button');
  filesTabBtn.id = 'files-tab';
  filesTabBtn.dataset.bsTarget = '#files-pane';
  filesTabBtn.innerHTML = '<i class="bi bi-file-earmark me-1"></i> Files';
  navTabs.appendChild(filesTab);

  const filesPane = paneTemplate.content.cloneNode(true);
  const filesPaneEl = filesPane.querySelector('.tab-pane');
  filesPaneEl.id = 'files-pane';
  filesPaneEl.innerHTML = `
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0">Files</h5>
      <div class="btn-group">
      </div>
    </div>
    <div id="files-list" class="list-group">
      <div class="text-center p-3">
        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
        <span class="ms-2">Loading files...</span>
      </div>
    </div>
  `;
  navPanes.appendChild(filesPane);

  // Add event listeners for file refresh buttons
  // filesPaneEl.querySelector('#btnRefreshLocalFiles').addEventListener('click', () => {
  //   socket.emit('printer_files', { id: printer.id, url: '/local' });
  //   filesPaneEl.querySelector('#files-list').innerHTML = `
  //     <div class="text-center p-3">
  //       <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
  //       <span class="ms-2">Loading files...</span>
  //     </div>
  //   `;
  // });

  // filesPaneEl.querySelector('#btnRefreshUsbFiles').addEventListener('click', () => {
  //   socket.emit('printer_files', { id: printer.id, url: '/usb' });
  //   filesPaneEl.querySelector('#files-list').innerHTML = `
  //     <div class="text-center p-3">
  //       <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
  //       <span class="ms-2">Loading USB files...</span>
  //     </div>
  //   `;
  // });

  // 3. Camera Tab (if supported)
  if (printer.supports_camera) {
    const cameraTab = tabTemplate.content.cloneNode(true);
    const cameraTabBtn = cameraTab.querySelector('button');
    cameraTabBtn.id = 'camera-tab';
    cameraTabBtn.dataset.bsTarget = '#camera-pane';
    cameraTabBtn.innerHTML = '<i class="bi bi-camera me-1"></i> Camera';
    navTabs.appendChild(cameraTab);

    const cameraPane = paneTemplate.content.cloneNode(true);
    const cameraPaneEl = cameraPane.querySelector('.tab-pane');
    cameraPaneEl.id = 'camera-pane';
    cameraPaneEl.innerHTML = `
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h5 class="mb-0">Camera Stream</h5>
        <div>
          <button class="btn btn-primary" id="btnStartStream">
            <i class="bi bi-play-fill me-1"></i> Start Stream
          </button>
          <button class="btn btn-secondary d-none" id="btnStopStream">
            <i class="bi bi-stop-fill me-1"></i> Stop Stream
          </button>
        </div>
      </div>
      <div class="camera-view">
        <div class="text-center py-5" id="cameraPlaceholder">
          <i class="bi bi-camera-video display-1 text-muted"></i>
          <p class="mt-2 text-muted">Click Start Stream to view camera feed</p>
        </div>
        <img src="" id="cameraStream" class="img-fluid d-none rounded" alt="Camera stream">
      </div>
    `;
    navPanes.appendChild(cameraPane);

    // Add event listeners for camera controls
    cameraPaneEl.querySelector('#btnStartStream').addEventListener('click', () => {
      startCameraStream(printer.id);
    });

    cameraPaneEl.querySelector('#btnStopStream').addEventListener('click', () => {
      stopCameraStream();
    });

    // When camera tab is clicked/shown, start the stream
    cameraTabBtn.addEventListener('shown.bs.tab', () => {
      if (!cameraStreaming) {
        startCameraStream(printer.id);
      }
    });

    // When another tab is clicked, stop the stream to save resources
    cameraTabBtn.addEventListener('hidden.bs.tab', () => {
      if (cameraStreaming) {
        stopCameraStream();
      }
    });
  }

  // 4. Info Tab
  const infoTab = tabTemplate.content.cloneNode(true);
  const infoTabBtn = infoTab.querySelector('button');
  infoTabBtn.id = 'info-tab';
  infoTabBtn.dataset.bsTarget = '#info-pane';
  infoTabBtn.innerHTML = '<i class="bi bi-gear me-1"></i> Information';
  navTabs.appendChild(infoTab);

  const infoPane = paneTemplate.content.cloneNode(true);
  const infoPaneEl = infoPane.querySelector('.tab-pane');
  infoPaneEl.id = 'info-pane';

  const infoTableBody = infoPane.querySelector('tbody');
  infoTableBody.id = 'info-table';
  navPanes.appendChild(infoPane);

  // Populate tabs with data
  populateStatusTab(printer);
  populateInfoTab(printer);
}

/**
 * Populate the status tab with printer information
 */
function populateStatusTab(printer) {
  const statusTable = document.getElementById('status-table');
  if (!statusTable) return;

  statusTable.innerHTML = '';

  const rows = [
    { key: 'Status', value: formatStatus(printer.machine_status || 'Unknown') },
    { key: 'Connection', value: formatConnectionStatus(printer.status) },
    { key: 'IP Address', value: printer.ip || 'N/A' },
    { key: 'Last Seen', value: printer.last_seen ? new Date(printer.last_seen * 1000).toLocaleString() : 'Never' }
  ];

  // Add print job information if printing
  if (printer.machine_status === 'PRINTING') {
    rows.push({ key: 'Print Status', value: formatPrintStatus(printer.print_status || 'Unknown') });

    if (printer.current_file) {
      rows.push({ key: 'Current File', value: printer.current_file });
    }

    if (printer.print_progress !== undefined) {
      rows.push({
        key: 'Progress',
        value: `
          <div class="progress" style="height: 20px;">
            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" 
                style="width: ${printer.print_progress}%">${printer.print_progress}%</div>
          </div>
        `
      });
    }

    if (printer.remain_time) {
      rows.push({ key: 'Remaining Time', value: formatTime(printer.remain_time) });
    }

    // Add print control buttons
    rows.push({
      key: 'Controls',
      value: `
        <div class="btn-group">
          <button class="btn btn-sm btn-warning" id="btnPausePrint">
            <i class="bi bi-pause-fill me-1"></i> Pause
          </button>
          <button class="btn btn-sm btn-danger" id="btnStopPrint">
            <i class="bi bi-stop-fill me-1"></i> Stop
          </button>
        </div>
      `
    });
  }

  // Add rows to table
  rows.forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td width="30%"><strong>${row.key}</strong></td>
      <td>${row.value}</td>
    `;
    statusTable.appendChild(tr);
  });

  // Add event listeners for print control buttons
  const pauseBtn = document.getElementById('btnPausePrint');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => {
      socket.emit('action_pause', { id: printer.id });
    });
  }

  const stopBtn = document.getElementById('btnStopPrint');
  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      showConfirmModal('stop', 'the current print job');
    });
  }
}

/**
 * Populate the info tab with printer details
 */
function populateInfoTab(printer) {
  const infoTable = document.getElementById('info-table');
  if (!infoTable) return;

  infoTable.innerHTML = '';

  const rows = [
    { key: 'Name', value: printer.name },
    { key: 'Model', value: printer.model },
    { key: 'Brand', value: printer.brand },
    { key: 'Firmware', value: printer.firmware || 'Unknown' },
    { key: 'Protocol', value: printer.protocol || 'Unknown' }
  ];

  // Add resolution if available
  if (printer.resolution) {
    const resolution = Array.isArray(printer.resolution)
      ? `${printer.resolution[0]} × ${printer.resolution[1]}`
      : printer.resolution;

    rows.push({ key: 'Resolution', value: resolution });
  }

  // Add build volume if available
  if (printer.build_volume) {
    const volume = Array.isArray(printer.build_volume)
      ? `${printer.build_volume[0]} × ${printer.build_volume[1]} × ${printer.build_volume[2]} mm`
      : printer.build_volume;

    rows.push({ key: 'Build Volume', value: volume });
  }

  // Add camera support info
  rows.push({
    key: 'Camera Support',
    value: printer.supports_camera
      ? '<span class="badge bg-success">Yes</span>'
      : '<span class="badge bg-secondary">No</span>'
  });

  // Add rows to table
  rows.forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td width="30%"><strong>${row.key}</strong></td>
      <td>${row.value}</td>
    `;
    infoTable.appendChild(tr);
  });

  // Add rename button
  const renameRow = document.createElement('tr');
  renameRow.innerHTML = `
    <td colspan="2" class="text-center pt-3">
      <button class="btn btn-outline-primary" id="btnRenamePrinter">
        <i class="bi bi-pencil me-1"></i> Rename Printer
      </button>
    </td>
  `;
  infoTable.appendChild(renameRow);

  // Add event listener for rename button
  document.getElementById('btnRenamePrinter').addEventListener('click', () => {
    const newName = prompt('Enter new name for printer:', printer.name);
    if (newName && newName !== printer.name) {
      socket.emit('action_rename', { id: printer.id, name: newName });
    }
  });
}

/**
 * Format status for display
 */
function formatStatus(status) {
  if (!status) return '<span class="badge bg-secondary">Unknown</span>';

  switch (status) {
    case 'IDLE':
      return '<span class="badge bg-success"><i class="bi bi-circle-fill me-1"></i> Idle</span>';
    case 'PRINTING':
      return '<span class="badge bg-primary"><i class="bi bi-printer-fill me-1"></i> Printing</span>';
    case 'FILE_TRANSFERRING':
      return '<span class="badge bg-warning"><i class="bi bi-arrow-repeat me-1"></i> Transferring File</span>';
    case 'EXPOSURE_TESTING':
      return '<span class="badge bg-info"><i class="bi bi-sun me-1"></i> Exposure Test</span>';
    case 'DEVICES_TESTING':
      return '<span class="badge bg-info"><i class="bi bi-tools me-1"></i> Device Test</span>';
    default:
      return `<span class="badge bg-secondary">${status}</span>`;
  }
}

/**
 * Format connection status for display
 */
function formatConnectionStatus(status) {
  if (status === 'connected') {
    return '<span class="badge bg-success"><i class="bi bi-plug-fill me-1"></i> Connected</span>';
  } else {
    return '<span class="badge bg-danger"><i class="bi bi-plug me-1"></i> Disconnected</span>';
  }
}

/**
 * Format print status for display
 */
function formatPrintStatus(status) {
  switch (status) {
    case 'IDLE':
      return '<span class="badge bg-secondary">Idle</span>';
    case 'HOMING':
      return '<span class="badge bg-info">Homing</span>';
    case 'DROPPING':
      return '<span class="badge bg-info">Dropping</span>';
    case 'EXPOSURING':
      return '<span class="badge bg-warning">Exposing</span>';
    case 'LIFTING':
      return '<span class="badge bg-info">Lifting</span>';
    case 'PAUSING':
      return '<span class="badge bg-warning">Pausing</span>';
    case 'PAUSED':
      return '<span class="badge bg-warning">Paused</span>';
    case 'STOPPING':
      return '<span class="badge bg-danger">Stopping</span>';
    case 'STOPED':
      return '<span class="badge bg-danger">Stopped</span>';
    case 'COMPLETE':
      return '<span class="badge bg-success">Complete</span>';
    case 'FILE_CHECKING':
      return '<span class="badge bg-info">Checking File</span>';
    default:
      return `<span class="badge bg-secondary">${status}</span>`;
  }
}

/**
 * Format time in seconds to human-readable format
 */
function formatTime(seconds) {
  if (!seconds) return 'Unknown';

  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  return `${hrs}h ${mins}m ${secs}s`;
}

/**
 * Format file size in bytes to human-readable format
 */
function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';

  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Handle printer status update
 */
function handlePrinterStatus(data) {
  if (!data || !data.id) return;
  
  const printerId = data.id;
  
  // Update printer in our local cache
  if (printers[printerId]) {
      printers[printerId].machine_status = data.machine_status;
      printers[printerId].print_status = data.print_status;
      printers[printerId].print_progress = data.print_progress;
      printers[printerId].current_file = data.current_file;
      printers[printerId].remain_time = data.remain_time;
      printers[printerId].status = 'connected';
      printers[printerId].last_seen = Date.now() / 1000;
      
      // Update UI if this is the current printer
      if (currentPrinter === printerId) {
          // Save current active tab before updating
          const activeTabId = document.querySelector('#navTabs .nav-link.active')?.id;
          
          // Update printer details
          displayPrinterDetails(printerId);
          
          // Restore active tab if one was selected
          if (activeTabId) {
              document.getElementById(activeTabId)?.click();
          }
      }
      
      // Update printer list item
      updatePrinterStatusInList(printerId);
  }
}

/**
 * Update printer status in the list
 */
function updatePrinterStatusInList(printerId) {
  const printer = printers[printerId];
  if (!printer) return;

  const printerItem = document.querySelector(`.printerListItem[data-printer-id="${printerId}"]`);
  if (!printerItem) return;

  // Update status icon
  const statusIcon = printerItem.querySelector('.printerStatus i');
  if (printer.status === 'connected') {
    statusIcon.className = 'bi bi-circle-fill text-success';
  } else {
    statusIcon.className = 'bi bi-circle-fill text-danger';
  }

  // Update info text
  const infoEl = printerItem.querySelector('.printerInfo');
  if (printer.machine_status === 'PRINTING' && printer.print_progress !== undefined) {
    infoEl.textContent = `Printing: ${printer.print_progress}%`;
  } else if (printer.machine_status) {
    infoEl.textContent = printer.machine_status;
  } else {
    infoEl.textContent = printer.ip;
  }
}

/**
 * Handle printer attributes update
 */
function handlePrinterAttributes(data) {
  if (!data || !data.id) return;

  const printerId = data.id;
  const attributes = data.attributes;

  // Update printer in our local cache
  if (printers[printerId] && attributes) {
    // Update attributes
    if (attributes.Resolution) {
      printers[printerId].resolution = attributes.Resolution;
    }

    if (attributes.XYZsize) {
      printers[printerId].build_volume = attributes.XYZsize;
    }

    if (attributes.CameraStatus !== undefined) {
      printers[printerId].camera_status = attributes.CameraStatus === 1;
    }

    // Update UI if this is the current printer
    if (currentPrinter === printerId) {
      populateInfoTab(printers[printerId]);
    }
  }
}

/**
 * Handle printer response
 */
function handlePrinterResponse(data) {
  if (!data || !data.id) return;

  const printerId = data.id;
  const cmd = data.cmd;
  const responseData = data.data;

  // Handle file list response
  if (cmd === 258 && responseData && responseData.FileList) {
    displayFileList(printerId, responseData.FileList, responseData.Url || '/local');
  }

  // Handle other responses
  switch (cmd) {
    case 259: // Delete file
      showToast('File deleted successfully', 'success');
      confirmModal.hide();
      break;
    case 128: // Start print
      showToast('Print started successfully', 'success');
      confirmModal.hide();
      break;
    case 129: // Pause print
      showToast('Print paused', 'success');
      break;
    case 130: // Stop print
      showToast('Print stopped', 'success');
      confirmModal.hide();
      break;
    case 131: // Resume print
      showToast('Print resumed', 'success');
      break;
    case 192: // Rename printer
      if (printers[printerId] && responseData && responseData.success) {
        showToast('Printer renamed successfully', 'success');
        // Update name in our local cache
        if (responseData.name) {
          printers[printerId].name = responseData.name;

          // Update UI
          if (currentPrinter === printerId) {
            document.getElementById('printerName').textContent = responseData.name;
          }

          // Update printer list item
          const printerItem = document.querySelector(`.printerListItem[data-printer-id="${printerId}"]`);
          if (printerItem) {
            printerItem.querySelector('.printerName').textContent = responseData.name;
          }
        }
      }
      break;
  }
}

/**
 * Display file list
 */
function displayFileList(printerId, files, path) {
  const filesList = document.getElementById('files-list');
  if (!filesList) return;

  if (!files || files.length === 0) {
    filesList.innerHTML = `<div class="alert alert-info">No files found in ${path}</div>`;
    return;
  }

  filesList.innerHTML = '';

  // Sort files: directories first, then by name
  const sortedFiles = [...files].sort((a, b) => {
    if (a.type === 0 && b.type !== 0) return -1;
    if (a.type !== 0 && b.type === 0) return 1;
    return (a.name || a.FileName || '').localeCompare(b.name || b.FileName || '');
  });

  sortedFiles.forEach(file => {
    const isDirectory = file.type === 0;
    // Handle different file property naming conventions
    const fileName = file.name || file.FileName || 'Unknown';
    const fileSize = formatFileSize(file.FileSize || file.fileSize || 0);
    const fileDate = file.CreationTime
      ? new Date(file.CreationTime * 1000).toLocaleString()
      : 'Unknown date';

    const item = document.createElement('div');
    item.className = 'list-group-item';

    if (isDirectory) {
      // Directory item
      item.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <i class="bi bi-folder-fill text-warning me-2"></i>
            <strong>${fileName}</strong>
          </div>
          <button class="btn btn-sm btn-outline-primary browse-folder" data-path="${fileName}">
            <i class="bi bi-folder2-open me-1"></i> Browse
          </button>
        </div>
      `;

      // Add event listener for browsing folder
      item.querySelector('.browse-folder').addEventListener('click', () => {
        socket.emit('printer_files', { id: printerId, url: fileName });
        filesList.innerHTML = `
          <div class="text-center p-3">
            <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
            <span class="ms-2">Loading files...</span>
          </div>
        `;
      });
    } else {
      // File item
      item.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <i class="bi bi-file-earmark-fill text-primary me-2"></i>
            <strong>${fileName}</strong>
            <div class="text-muted small mt-1">
              ${fileDate} - ${fileSize}
            </div>
          </div>
          <div class="btn-group">
            <button class="btn btn-sm btn-primary btn-print-file">
              <i class="bi bi-printer me-1"></i> Print
            </button>
            <button class="btn btn-sm btn-danger btn-delete-file">
              <i class="bi bi-trash me-1"></i> Delete
            </button>
          </div>
        </div>
      `;

      // Add event listeners for file actions
      item.querySelector('.btn-print-file').addEventListener('click', () => {
        showConfirmModal('print', fileName);
      });

      item.querySelector('.btn-delete-file').addEventListener('click', () => {
        showConfirmModal('delete', fileName);
      });
    }

    filesList.appendChild(item);
  });
}

/**
 * Handle printer error
 */
function handlePrinterError(data) {
  if (!data) return;

  const errorCode = data.error_code;
  const errorMessage = data.error_message || `Error code: ${errorCode}`;

  showToast(`Printer error: ${errorMessage}`, 'error');
}

/**
 * Handle printer notice
 */
function handlePrinterNotice(data) {
  if (!data) return;

  const message = data.message || 'Notification from printer';

  showToast(message, 'info');
}

/**
 * Show confirmation modal
 */
function showConfirmModal(action, value) {
  const modalTitle = document.getElementById('modalConfirmTitle');
  const modalAction = document.getElementById('modalConfirmAction');
  const modalValue = document.getElementById('modalConfirmValue');
  const confirmBtn = document.getElementById('btnConfirm');
  
  // Check if elements exist
  if (!modalTitle || !modalAction || !modalValue || !confirmBtn) {
    console.error('Modal elements not found');
    return;
  }
  
  // Get modal element and initialize if not already done
  const modalEl = document.getElementById('modalConfirm');
  if (!modalEl) {
    console.error('Modal element not found');
    return;
  }
  
  // Initialize modal if not already initialized
  if (!confirmModal) {
    confirmModal = new bootstrap.Modal(modalEl);
  }

  // Set title based on action
  switch (action) {
    case 'print':
      modalTitle.textContent = 'Confirm Print';
      break;
    case 'delete':
      modalTitle.textContent = 'Confirm Delete';
      break;
    case 'stop':
      modalTitle.textContent = 'Confirm Stop Print';
      break;
    default:
      modalTitle.textContent = `Confirm ${action}`;
  }

  modalAction.textContent = action;
  modalValue.textContent = value;

  confirmBtn.dataset.action = action;
  confirmBtn.dataset.value = value;

  // Show the modal
  confirmModal.show();
}

/**
 * Handle confirm button click
 */
function handleConfirmAction() {
  const action = document.getElementById('btnConfirm').dataset.action;
  const value = document.getElementById('btnConfirm').dataset.value;
  const printerId = document.getElementById('btnConfirm').dataset.printerId;

  if (!action) return;

  // Handle printer deletion
  if (action === 'delete-printer' && printerId) {
    deletePrinter(printerId);
    return;
  }
  
  // Handle file actions
  if (!currentPrinter) {
    showToast('No printer selected', 'error');
    if (confirmModal) confirmModal.hide();
    return;
  }

  switch (action) {
    case 'print':
      socket.emit('action_print', { id: currentPrinter, data: value });
      break;
    case 'delete':
      socket.emit('action_delete', { id: currentPrinter, data: value });
      break;
    case 'stop':
      socket.emit('action_stop', { id: currentPrinter });
      break;
  }
}
/**
 * Handle upload button click
 */
function handleUploadClick() {
  if (!currentPrinter) {
    showToast('Please select a printer first', 'warning');
    return;
  }

  const fileInput = document.getElementById('uploadFile');
  const file = fileInput.files[0];

  if (!file) {
    showToast('Please select a file to upload', 'warning');
    return;
  }

  // Check file extension
  const fileExt = file.name.split('.').pop().toLowerCase();
  if (!['ctb', 'goo', 'prz'].includes(fileExt)) {
    showToast('Invalid file type. Only .ctb, .goo, and .prz files are supported.', 'error');
    return;
  }

  // Create FormData and submit
  const formData = new FormData();
  formData.append('file', file);
  formData.append('printer', currentPrinter);

  fetch('/upload', {
    method: 'POST',
    body: formData
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showToast('File upload started', 'success');
        fileInput.value = ''; // Clear file input

        // Reset progress bar
        const progressBar = document.getElementById('progressUpload');
        progressBar.style.width = '0%';
        progressBar.textContent = '0%';
      } else {
        showToast(data.error || 'Upload failed', 'error');
      }
    })
    .catch(error => {
      showToast('Error uploading file', 'error');
      console.error('Upload error:', error);
    });
}

/**
 * Handle upload progress update
 */
function handleUploadProgress(data) {
  if (!data || !data.id) return;

  // Store task in global state
  uploadTasks[data.id] = data;

  // Update UI if needed
  if (data.printer_id === currentPrinter) {
    // Update progress bar in upload form
    const progressBar = document.getElementById('progressUpload');
    if (progressBar) {
      progressBar.style.width = `${data.progress}%`;
      progressBar.textContent = `${data.progress}%`;

      if (data.status === 'complete') {
        progressBar.classList.add('bg-success');
        setTimeout(() => {
          progressBar.style.width = '0%';
          progressBar.textContent = '0%';
          progressBar.classList.remove('bg-success');
        }, 3000);

        // Refresh file list
        socket.emit('printer_files', { id: currentPrinter, url: '/local' });
      }
    }
  }

  // Update upload tasks display
  updateUploadTasksDisplay();
}

/**
 * Update upload tasks display
 */
function updateUploadTasksDisplay() {
  const container = document.getElementById('uploadProgressContainer');
  if (!container) return;

  container.innerHTML = '';

  const activeTasks = Object.values(uploadTasks).filter(
    task => task.status !== 'complete' && task.status !== 'error'
  );

  const recentCompletedTasks = Object.values(uploadTasks)
    .filter(task => task.status === 'complete' || task.status === 'error')
    .sort((a, b) => b.updated_at - a.updated_at)
    .slice(0, 3);

  const allTasks = [...activeTasks, ...recentCompletedTasks];

  if (allTasks.length === 0) {
    container.innerHTML = '<div class="text-center py-3 text-muted">No active uploads</div>';
    return;
  }

  const template = document.getElementById('tmplUploadProgress');

  allTasks.forEach(task => {
    const item = template.content.cloneNode(true);

    item.querySelector('.upload-item').dataset.taskId = task.id;
    item.querySelector('.upload-filename').textContent = task.filename;
    item.querySelector('.upload-printer').textContent = `To: ${task.printer_name}`;

    const statusBadge = item.querySelector('.upload-status');
    const progressBar = item.querySelector('.upload-progress-bar');

    // Set status
    switch (task.status) {
      case 'starting':
        statusBadge.textContent = 'Starting';
        statusBadge.className = 'badge upload-status bg-secondary';
        break;
      case 'uploading':
        statusBadge.textContent = 'Uploading';
        statusBadge.className = 'badge upload-status bg-primary';
        progressBar.classList.add('progress-bar-striped', 'progress-bar-animated');
        break;
      case 'complete':
        statusBadge.textContent = 'Complete';
        statusBadge.className = 'badge upload-status bg-success';
        progressBar.classList.add('bg-success');
        break;
      case 'error':
        statusBadge.textContent = 'Error';
        statusBadge.className = 'badge upload-status bg-danger';
        progressBar.classList.add('bg-danger');
        break;
    }

    // Set progress
    progressBar.style.width = `${task.progress}%`;
    progressBar.setAttribute('aria-valuenow', task.progress);

    container.appendChild(item);
  });

  // Update count badge
  updateUploadCount();
}

/**
 * Update upload count badge
 */
function updateUploadCount() {
  const activeTasks = Object.values(uploadTasks).filter(
    task => task.status !== 'complete' && task.status !== 'error'
  );

  const countElement = document.getElementById('uploadCount');
  if (countElement) {
    countElement.textContent = `${activeTasks.length} active`;
  }
}

/**
 * Start camera stream
 */
function startCameraStream(printerId) {
  if (!printerId || !printers[printerId] || !printers[printerId].supports_camera) return;

  // Enable camera on printer
  socket.emit('action_camera', { id: printerId, enable: true });

  // Show loading indicator
  const placeholder = document.getElementById('cameraPlaceholder');
  placeholder.innerHTML = `
    <div class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
      <p class="mt-3 text-muted">Connecting to camera...</p>
    </div>
  `;

  // Get stream image
  const img = document.getElementById('cameraStream');

  // Show start/stop buttons
  document.getElementById('btnStartStream').classList.add('d-none');
  document.getElementById('btnStopStream').classList.remove('d-none');

  // Load first image
  const timestamp = new Date().getTime();
  img.src = `/camera/${printerId}/stream?t=${timestamp}`;

  // When image loads, hide placeholder and show image
  img.onload = () => {
    placeholder.classList.add('d-none');
    img.classList.remove('d-none');

    // Set streaming flag
    cameraStreaming = true;

    // Start refresh interval
    if (cameraInterval) {
      clearInterval(cameraInterval);
    }

    cameraInterval = setInterval(() => {
      const newTimestamp = new Date().getTime();
      img.src = `/camera/${printerId}/stream?t=${newTimestamp}`;
    }, 1000);
  };

  // Handle errors
  img.onerror = () => {
    placeholder.innerHTML = `
      <div class="text-center py-5">
        <i class="bi bi-camera-video-off text-danger display-4"></i>
        <p class="mt-3 text-danger">Failed to connect to camera</p>
        <button class="btn btn-outline-primary mt-2" id="btnRetryCamera">
          <i class="bi bi-arrow-clockwise me-1"></i> Retry
        </button>
      </div>
    `;

    img.classList.add('d-none');

    // Show start button, hide stop button
    document.getElementById('btnStartStream').classList.remove('d-none');
    document.getElementById('btnStopStream').classList.add('d-none');

    // Reset streaming state
    cameraStreaming = false;
    if (cameraInterval) {
      clearInterval(cameraInterval);
      cameraInterval = null;
    }

    // Add retry button handler
    document.getElementById('btnRetryCamera')?.addEventListener('click', () => {
      startCameraStream(printerId);
    });
  };
}

/**
 * Stop camera stream
 */
function stopCameraStream() {
  // Stop refresh interval
  if (cameraInterval) {
    clearInterval(cameraInterval);
    cameraInterval = null;
  }

  // Reset UI
  const placeholder = document.getElementById('cameraPlaceholder');
  const img = document.getElementById('cameraStream');

  placeholder.classList.remove('d-none');
  placeholder.innerHTML = `
    <div class="text-center py-5">
      <i class="bi bi-camera-video text-muted display-4"></i>
      <p class="mt-3 text-muted">Click Start Stream to view camera feed</p>
    </div>
  `;

  img.classList.add('d-none');

  // Show start button, hide stop button
  document.getElementById('btnStartStream').classList.remove('d-none');
  document.getElementById('btnStopStream').classList.add('d-none');

  // Set streaming flag
  cameraStreaming = false;

  // Disable camera on printer
  if (currentPrinter) {
    socket.emit('action_camera', { id: currentPrinter, enable: false });
  }
}

/**
 * Set server connection status
 */
function setServerStatus(online) {
  const serverStatus = document.querySelector('.serverStatus');
  if (online) {
    serverStatus.classList.remove('bi-cloud', 'text-danger');
    serverStatus.classList.add('bi-cloud-check-fill', 'text-success');
  } else {
    serverStatus.classList.remove('bi-cloud-check-fill', 'text-success');
    serverStatus.classList.add('bi-cloud', 'text-danger');
  }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
  const toastEl = document.getElementById('toastUpload');
  const toastBody = toastEl.querySelector('.toast-body');
  const toastHeader = toastEl.querySelector('.toast-header');
  const toastTime = document.getElementById('toastTime');

  // Set message
  toastBody.textContent = message;
  toastTime.textContent = 'just now';

  // Set icon and color based on type
  const iconEl = toastHeader.querySelector('i');

  switch (type) {
    case 'success':
      iconEl.className = 'bi bi-check-circle-fill text-success me-2';
      break;
    case 'error':
      iconEl.className = 'bi bi-exclamation-circle-fill text-danger me-2';
      break;
    case 'warning':
      iconEl.className = 'bi bi-exclamation-triangle-fill text-warning me-2';
      break;
    default:
      iconEl.className = 'bi bi-info-circle-fill text-primary me-2';
  }

  // Show toast
  const toast = bootstrap.Toast.getOrCreateInstance(toastEl);
  toast.show();
}

// Global variables (add these to your existing global variables)
let scanModal = null;
let scanInProgress = false;
let discoveredPrinters = 0;

document.addEventListener('DOMContentLoaded', () => {
  initDefaultImages();

  refreshStatus();
  setInterval(refreshStatus, 30_000);

  // Initialize scan modal
  scanModal = new bootstrap.Modal(document.getElementById('modalScanLAN'));

  // Add scan LAN button event listener
  document.getElementById('btnScanLAN').addEventListener('click', startLANScan);

  // Add socket event handlers for scan progress
  socket.on('scan_progress', handleScanProgress);
  socket.on('printer_discovered', handlePrinterDiscovered);
});

/**s
 * Start a LAN scan for printers
 */
function startLANScan() {
  if (scanInProgress) return;

  scanInProgress = true;
  discoveredPrinters = 0;

  // Reset UI elements
  document.getElementById('scanProgress').style.width = '0%';
  document.getElementById('scanStatus').textContent = 'Initializing scan...';
  document.getElementById('scanStatus').className = 'alert alert-info';
  document.getElementById('foundPrinters').classList.add('d-none');
  document.getElementById('printerScanList').innerHTML = '';
  
  // Add search status
  const scanDetails = document.createElement('div');
  scanDetails.className = 'scan-details small text-muted mt-2';
  scanDetails.innerHTML = `
    <div id="scanDetails">
      <div>Scanning network interfaces...</div>
    </div>
  `;
  document.getElementById('scanStatus').appendChild(scanDetails);

  // Show modal
  scanModal.show();

  // Start scan with 8 second timeout for more thorough scanning
  socket.emit('scan_lan', { timeout: 8 });

  // Set timeout to ensure scan doesn't hang
  setTimeout(() => {
    if (scanInProgress) {
      completeScan(discoveredPrinters > 0);
    }
  }, 30000);  // 30 second max timeout for thorough scan

  // Function to complete scan
  function completeScan(success) {
    scanInProgress = false;

    // Update UI
    document.getElementById('scanProgress').style.width = '100%';
    document.getElementById('scanProgress').classList.remove('progress-bar-animated');

    if (success) {
      document.getElementById('scanStatus').textContent = `Scan complete! Found ${discoveredPrinters} printer(s).`;
      document.getElementById('scanStatus').className = 'alert alert-success';
      document.getElementById('foundPrinters').classList.remove('d-none');
    } else {
      document.getElementById('scanStatus').textContent = 'No printers found on your network.';
      document.getElementById('scanStatus').className = 'alert alert-warning';
      
      // Add troubleshooting tips
      const tips = document.createElement('div');
      tips.className = 'mt-3 small';
      tips.innerHTML = `
        <p><strong>Troubleshooting tips:</strong></p>
        <ul>
          <li>Make sure your printer is powered on and connected to the network</li>
          <li>Ensure your computer and printer are on the same network</li>
          <li>Try adding your printer manually using its IP address</li>
          <li>Check if your firewall is blocking UDP port 3000</li>
          <li>Temporarily disable VPN software if you're using any</li>
        </ul>
      `;
      document.getElementById('scanStatus').appendChild(tips);
    }
  }
}

/**
 * Handle scan progress update from server with more detailed information
 */
function handleScanProgress(data) {
  if (!scanInProgress) return;

  // Update progress if provided
  if (data.progress) {
    document.getElementById('scanProgress').style.width = `${data.progress}%`;
  }

  // Update status text if provided
  if (data.status) {
    const mainStatus = document.getElementById('scanStatus');
    if (mainStatus.childNodes.length === 0 || mainStatus.childNodes[0].nodeType === Node.TEXT_NODE) {
      mainStatus.textContent = data.status;
    } else {
      mainStatus.childNodes[0].textContent = data.status;
    }
  }
  
  // Add scan details if available
  if (data.details) {
    const detailsEl = document.getElementById('scanDetails');
    if (detailsEl) {
      const detail = document.createElement('div');
      detail.textContent = data.details;
      detailsEl.appendChild(detail);
      
      // Scroll to bottom
      detailsEl.scrollTop = detailsEl.scrollHeight;
    }
  }

  // Complete scan if done
  if (data.complete) {
    scanInProgress = false;

    // Update UI
    document.getElementById('scanProgress').style.width = '100%';
    document.getElementById('scanProgress').classList.remove('progress-bar-animated');

    if (data.success) {
      document.getElementById('scanStatus').textContent = `Scan complete! Found ${discoveredPrinters} printer(s).`;
      document.getElementById('scanStatus').className = 'alert alert-success';
      document.getElementById('foundPrinters').classList.remove('d-none');
    } else {
      document.getElementById('scanStatus').textContent = 'No printers found on your network.';
      document.getElementById('scanStatus').className = 'alert alert-warning';
      
      // Add a button to manually add a printer
      const addManuallyBtn = document.createElement('button');
      addManuallyBtn.className = 'btn btn-primary mt-3';
      addManuallyBtn.innerHTML = '<i class="bi bi-plus-circle me-2"></i>Add Printer Manually';
      addManuallyBtn.addEventListener('click', () => {
        scanModal.hide();
        addPrinterModal.show();
      });
      document.getElementById('scanStatus').appendChild(addManuallyBtn);
    }
  }
}

/**
 * Handle newly discovered printer from server
 */
function handlePrinterDiscovered(printer) {
  if (!scanInProgress) return;

  discoveredPrinters++;

  // Add to found printers list
  const listItem = document.createElement('li');
  listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
  listItem.innerHTML = `
    <div>
      <strong>${printer.name}</strong>
      <div class="text-muted small">${printer.ip} - ${printer.model}</div>
    </div>
    <button class="btn btn-sm btn-primary add-discovered-printer" data-printer-ip="${printer.ip}" data-printer-name="${printer.name}" data-printer-model="${printer.model}" data-printer-brand="${printer.brand}">
      <i class="bi bi-plus-circle"></i> Add
    </button>
  `;

  // Add event listener for the add button
  listItem.querySelector('.add-discovered-printer').addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const printerData = {
      name: btn.dataset.printerName,
      ip: btn.dataset.printerIp,
      model: btn.dataset.printerModel,
      brand: btn.dataset.printerBrand
    };

    // Call addPrinterFromScan
    addPrinterFromScan(printerData);

    // Update button to show it's being added
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-check-circle"></i> Adding...';
  });

  document.getElementById('printerScanList').appendChild(listItem);
  document.getElementById('foundPrinters').classList.remove('d-none');
}

/**
 * Add a printer from scan results
 */
function addPrinterFromScan(printerData) {
  // Send request to add printer
  fetch('/api/printer/add', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(printerData)
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showToast(`Printer ${printerData.name} added successfully`, 'success');

        // Refresh printer list
        socket.emit('printers');

        // Select the new printer if available
        if (data.printer_id) {
          setTimeout(() => {
            selectPrinter(data.printer_id);
          }, 500);
        }
      } else {
        showToast(data.error || 'Failed to add printer', 'error');
      }
    })
    .catch(error => {
      showToast('Error adding printer', 'error');
      console.error('Error:', error);
    });
}

// Enhance the existing initSocketIO function to handle connection issues
function initSocketIO() {
  socket = io({
    reconnectionAttempts: 5,  // Try to reconnect 5 times
    reconnectionDelay: 1000,  // Start with a 1 second delay
    reconnectionDelayMax: 5000,  // Maximum delay of 5 seconds
    timeout: 20000  // Timeout after 20 seconds
  });

  // Connection events
  socket.on('connect', () => {
    console.log('Connected to server');
    setServerStatus(true);

    // If reconnected, refresh data
    socket.emit('printers');
  });

  socket.on('disconnect', () => {
    console.log('Disconnected from server');
    setServerStatus(false);
  });

  socket.on('connect_error', (error) => {
    console.error('Connection error:', error);
    setServerStatus(false);
    showToast('Connection to server failed. Retrying...', 'error');
  });

  socket.on('reconnect_failed', () => {
    console.error('Failed to reconnect to server');
    showToast('Could not connect to server. Please check if the server is running.', 'error');
  });

  // Data events
  socket.on('printers', handlePrinters);
  socket.on('printer_status', handlePrinterStatus);
  socket.on('printer_attributes', handlePrinterAttributes);
  socket.on('printer_response', handlePrinterResponse);
  socket.on('printer_error', handlePrinterError);
  socket.on('printer_notice', handlePrinterNotice);
  socket.on('upload_progress', handleUploadProgress);
}

function handleAddPrinter(e) {
  e.preventDefault();

  // Get form inputs
  const form = document.getElementById('formAddPrinter');
  const name = form.querySelector('[name="name"]').value.trim();
  const ip = form.querySelector('[name="ip"]').value.trim();
  const model = form.querySelector('[name="model"]').value;
  const brand = form.querySelector('[name="brand"]').value;

  // Enhanced validation
  const errors = [];
  if (!name) errors.push("Printer name is required");
  if (!ip) errors.push("IP address is required");

  // IP format validation
  const ipRegex = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/;
  if (ip && !ipRegex.test(ip)) {
    errors.push("Invalid IP address format (e.g., 192.168.1.100)");
  } else if (ip) {
    // Validate each octet is 0-255
    const octets = ip.split('.');
    for (const octet of octets) {
      const num = parseInt(octet, 10);
      if (num < 0 || num > 255) {
        errors.push("IP address octets must be between 0 and 255");
        break;
      }
    }
  }

  // Display validation errors
  if (errors.length > 0) {
    const errorMsg = errors.join(". ");
    showToast(errorMsg, 'error');
    return;
  }

  // Show loading state
  const submitBtn = form.querySelector('button[type="submit"]');
  const originalBtnText = submitBtn.innerHTML;
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Adding...';

  // First run a connectivity test
  fetch('/api/printer/diagnostics', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ ip })
  })
  .then(response => response.json())
  .then(diagnostic => {
    if (diagnostic.success && (diagnostic.results.overall.status === 'success' || diagnostic.results.ping.status === 'success')) {
      // IP is reachable, proceed with adding printer
      return fetch('/api/printer/add', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name, ip, model, brand })
      });
    } else {
      // IP is not reachable, but allow user to continue with warning
      const confirmContinue = confirm(`Warning: Printer at ${ip} seems unreachable. Add anyway?`);
      if (confirmContinue) {
        return fetch('/api/printer/add', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ name, ip, model, brand })
        });
      } else {
        throw new Error('Canceled by user');
      }
    }
  })
  .then(response => response.json())
  .then(data => {
    // Reset button state
    submitBtn.disabled = false;
    submitBtn.innerHTML = originalBtnText;

    if (data.success) {
      showToast(`Printer "${name}" added successfully`, 'success');
      addPrinterModal.hide();

      // Reset form
      form.reset();

      // Refresh printer list
      socket.emit('printers');

      // Select the new printer if available
      if (data.printer_id) {
        setTimeout(() => {
          selectPrinter(data.printer_id);
        }, 500);
      }
    } else {
      showToast(data.error || 'Failed to add printer', 'error');
    }
  })
  .catch(error => {
    // Reset button state
    submitBtn.disabled = false;
    submitBtn.innerHTML = originalBtnText;

    if (error.message === 'Canceled by user') {
      showToast('Printer addition canceled', 'info');
    } else {
      showToast('Error adding printer: Network error', 'error');
      console.error('Error:', error);
    }
  });
}

function createCameraTab(printer) {
  // Only create camera tab if printer supports it
  if (!printer.supports_camera) return;
  
  const cameraPaneEl = document.getElementById('camera-pane');
  if (!cameraPaneEl) return;
  
  cameraPaneEl.innerHTML = `
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0">Camera Stream</h5>
      <div>
        <button class="btn btn-primary" id="btnStartStream">
          <i class="bi bi-play-fill me-1"></i> Start Stream
        </button>
        <button class="btn btn-secondary d-none" id="btnStopStream">
          <i class="bi bi-stop-fill me-1"></i> Stop Stream
        </button>
        <button class="btn btn-info ms-2" id="btnCameraSettings">
          <i class="bi bi-gear-fill me-1"></i> Settings
        </button>
      </div>
    </div>
    <div class="camera-view">
      <div class="text-center py-5" id="cameraPlaceholder">
        <i class="bi bi-camera-video display-1 text-muted"></i>
        <p class="mt-2 text-muted">Click Start Stream to view camera feed</p>
      </div>
      <img src="" id="cameraStream" class="img-fluid d-none rounded" alt="Camera stream">
    </div>
    <div class="camera-controls mt-3 d-none">
      <div class="card">
        <div class="card-header">Camera Controls</div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-6">
              <div class="mb-3">
                <label class="form-label">Refresh Rate</label>
                <select class="form-select" id="cameraRefreshRate">
                  <option value="500">Very Fast (0.5s)</option>
                  <option value="1000" selected>Fast (1s)</option>
                  <option value="2000">Normal (2s)</option>
                  <option value="5000">Slow (5s)</option>
                </select>
              </div>
            </div>
            <div class="col-md-6">
              <div class="mb-3">
                <label class="form-label">Camera Status</label>
                <div class="d-flex align-items-center">
                  <span id="cameraStatus" class="badge bg-secondary me-2">Unknown</span>
                  <button class="btn btn-sm btn-outline-primary" id="btnRefreshCameraStatus">
                    <i class="bi bi-arrow-clockwise"></i>
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div class="row mt-2">
            <div class="col-12">
              <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" id="cameraEnabledSwitch">
                <label class="form-check-label" for="cameraEnabledSwitch">
                  Enable Camera on Printer
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
  
  // Add event listeners for camera controls
  document.getElementById('btnStartStream').addEventListener('click', () => {
    startCameraStream(printer.id);
  });
  
  document.getElementById('btnStopStream').addEventListener('click', () => {
    stopCameraStream();
  });
  
  document.getElementById('btnCameraSettings').addEventListener('click', () => {
    toggleCameraControls();
  });
  
  document.getElementById('cameraRefreshRate').addEventListener('change', (e) => {
    updateCameraRefreshRate(parseInt(e.target.value, 10));
  });
  
  document.getElementById('cameraEnabledSwitch').addEventListener('change', (e) => {
    setCameraEnabled(printer.id, e.target.checked);
  });
  
  document.getElementById('btnRefreshCameraStatus').addEventListener('click', () => {
    checkCameraStatus(printer.id);
  });
  
  // Initialize camera status
  checkCameraStatus(printer.id);
}

// Toggle camera controls visibility
function toggleCameraControls() {
  const controls = document.querySelector('.camera-controls');
  if (controls) {
    controls.classList.toggle('d-none');
  }
}

// Update camera refresh rate
function updateCameraRefreshRate(rate) {
  if (cameraInterval) {
    clearInterval(cameraInterval);
    cameraInterval = null;
  }
  
  if (cameraStreaming) {
    // Restart stream with new refresh rate
    cameraInterval = setInterval(() => {
      const img = document.getElementById('cameraStream');
      if (img) {
        const newTimestamp = new Date().getTime();
        img.src = `/camera/${currentPrinter}/stream?t=${newTimestamp}`;
      }
    }, rate);
  }
}

// Check camera status via API
function checkCameraStatus(printerId) {
  if (!printerId) return;
  
  const statusEl = document.getElementById('cameraStatus');
  const switchEl = document.getElementById('cameraEnabledSwitch');
  
  if (!statusEl || !switchEl) return;
  
  // Set loading state
  statusEl.className = 'badge bg-info me-2';
  statusEl.textContent = 'Checking...';
  
  // Request camera status via API
  fetch(`/api/printer/${printerId}/camera/status`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Update UI
        const enabled = data.enabled;
        statusEl.className = enabled ? 'badge bg-success me-2' : 'badge bg-danger me-2';
        statusEl.textContent = enabled ? 'Enabled' : 'Disabled';
        switchEl.checked = enabled;
      } else {
        // Show error
        statusEl.className = 'badge bg-warning me-2';
        statusEl.textContent = 'Error';
      }
    })
    .catch(error => {
      console.error('Error checking camera status:', error);
      statusEl.className = 'badge bg-danger me-2';
      statusEl.textContent = 'Error';
    });
}

// Enable/disable camera on printer
function setCameraEnabled(printerId, enabled) {
  if (!printerId) return;
  
  // Send request to API endpoint
  fetch(`/api/printer/${printerId}/camera`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      enable: enabled
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Show success message
        showToast(
          `Camera ${enabled ? 'enabled' : 'disabled'} successfully`,
          'success'
        );
        
        // Update UI
        checkCameraStatus(printerId);
      } else {
        // Show error
        showToast(
          `Failed to ${enabled ? 'enable' : 'disable'} camera: ${data.error || 'Unknown error'}`,
          'error'
        );
      }
    })
    .catch(error => {
      console.error('Error setting camera status:', error);
      showToast(
        `Error setting camera status: ${error.message || 'Network error'}`,
        'error'
      );
    });
}
function startCameraStream(printerId) {
  if (!printerId || !printers[printerId] || !printers[printerId].supports_camera) return;

  // Show loading indicator
  const placeholder = document.getElementById('cameraPlaceholder');
  placeholder.innerHTML = `
    <div class="text-center py-5">
      <div class="spinner-border text-primary" role="status"></div>
      <p class="mt-3 text-muted">Connecting to camera...</p>
    </div>
  `;

  // Get stream image element
  const img = document.getElementById('cameraStream');

  // Show start/stop buttons
  document.getElementById('btnStartStream').classList.add('d-none');
  document.getElementById('btnStopStream').classList.remove('d-none');

  // Enable camera on printer via API
  fetch(`/api/printer/${printerId}/camera`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      enable: true
    })
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Load first image
        const timestamp = new Date().getTime();
        img.src = `/camera/${printerId}/stream?t=${timestamp}`;
        
        // When image loads, hide placeholder and show image
        img.onload = () => {
          placeholder.classList.add('d-none');
          img.classList.remove('d-none');
          
          // Set streaming flag
          cameraStreaming = true;
          
          // Get refresh rate from select
          const refreshRate = parseInt(document.getElementById('cameraRefreshRate').value, 10) || 1000;
          
          // Start refresh interval
          if (cameraInterval) {
            clearInterval(cameraInterval);
          }
          
          cameraInterval = setInterval(() => {
            const newTimestamp = new Date().getTime();
            img.src = `/camera/${printerId}/stream?t=${newTimestamp}`;
          }, refreshRate);
          
          // Show camera controls
          document.querySelector('.camera-controls')?.classList.remove('d-none');
          
          // Update status
          checkCameraStatus(printerId);
        };
        
        // Handle errors
        img.onerror = () => {
          handleCameraError(placeholder);
        };
      } else {
        // Show error
        handleCameraError(placeholder, data.error || 'Failed to enable camera');
      }
    })
    .catch(error => {
      console.error('Error enabling camera:', error);
      handleCameraError(placeholder, error.message || 'Network error');
    });
}

function handleCameraError(placeholder, errorMsg = null) {
  placeholder.innerHTML = `
    <div class="text-center py-5">
      <i class="bi bi-camera-video-off text-danger display-4"></i>
      <p class="mt-3 text-danger">Failed to connect to camera</p>
      ${errorMsg ? `<p class="small text-muted">${errorMsg}</p>` : ''}
      <button class="btn btn-outline-primary mt-2" id="btnRetryCamera">
        <i class="bi bi-arrow-clockwise me-1"></i> Retry
      </button>
    </div>
  `;

  document.getElementById('cameraStream').classList.add('d-none');

  // Show start button, hide stop button
  document.getElementById('btnStartStream').classList.remove('d-none');
  document.getElementById('btnStopStream').classList.add('d-none');

  // Reset streaming state
  cameraStreaming = false;
  if (cameraInterval) {
    clearInterval(cameraInterval);
    cameraInterval = null;
  }

  // Add retry button handler
  document.getElementById('btnRetryCamera')?.addEventListener('click', () => {
    startCameraStream(currentPrinter);
  });
}

function stopCameraStream() {
  // Stop refresh interval
  if (cameraInterval) {
    clearInterval(cameraInterval);
    cameraInterval = null;
  }

  // Reset UI
  const placeholder = document.getElementById('cameraPlaceholder');
  const img = document.getElementById('cameraStream');

  placeholder.classList.remove('d-none');
  placeholder.innerHTML = `
    <div class="text-center py-5">
      <i class="bi bi-camera-video text-muted display-4"></i>
      <p class="mt-3 text-muted">Click Start Stream to view camera feed</p>
    </div>
  `;

  img.classList.add('d-none');

  // Show start button, hide stop button
  document.getElementById('btnStartStream').classList.remove('d-none');
  document.getElementById('btnStopStream').classList.add('d-none');

  // Set streaming flag
  cameraStreaming = false;

  // Disable camera on printer
  if (currentPrinter) {
    fetch(`/api/printer/${currentPrinter}/camera`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        enable: false
      })
    })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          // Update status
          checkCameraStatus(currentPrinter);
        }
      })
      .catch(error => {
        console.error('Error disabling camera:', error);
      });
  }
}

function handleCameraError(placeholder, errorMsg = null) {
  placeholder.innerHTML = `
      <div class="text-center py-5">
          <i class="bi bi-camera-video-off text-danger display-4"></i>
          <p class="mt-3 text-danger">Failed to connect to camera</p>
          ${errorMsg ? `<p class="small text-muted">${errorMsg}</p>` : ''}
          <button class="btn btn-outline-primary mt-2" id="btnRetryCamera">
              <i class="bi bi-arrow-clockwise me-1"></i> Retry
          </button>
      </div>
  `;

  document.getElementById('cameraStream').classList.add('d-none');

  // Show start button, hide stop button
  document.getElementById('btnStartStream').classList.remove('d-none');
  document.getElementById('btnStopStream').classList.add('d-none');

  // Reset streaming state
  cameraStreaming = false;
  if (cameraInterval) {
      clearInterval(cameraInterval);
      cameraInterval = null;
  }

  // Add retry button handler
  document.getElementById('btnRetryCamera')?.addEventListener('click', () => {
      startCameraStream(currentPrinter);
  });
}

function stopCameraStream() {
  // Stop refresh interval
  if (cameraInterval) {
      clearInterval(cameraInterval);
      cameraInterval = null;
  }

  // Reset UI
  const placeholder = document.getElementById('cameraPlaceholder');
  const img = document.getElementById('cameraStream');

  placeholder.classList.remove('d-none');
  placeholder.innerHTML = `
      <div class="text-center py-5">
          <i class="bi bi-camera-video text-muted display-4"></i>
          <p class="mt-3 text-muted">Click Start Stream to view camera feed</p>
      </div>
  `;

  img.classList.add('d-none');

  // Show start button, hide stop button
  document.getElementById('btnStartStream').classList.remove('d-none');
  document.getElementById('btnStopStream').classList.add('d-none');

  // Set streaming flag
  cameraStreaming = false;

  // Disable camera on printer
  if (currentPrinter) {
      fetch(`/api/printer/${currentPrinter}/camera`, {
          method: 'POST',
          headers: {
              'Content-Type': 'application/json'
          },
          body: JSON.stringify({
              enable: false
          })
      })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  // Update status
                  checkCameraStatus(currentPrinter);
              }
          })
          .catch(error => {
              console.error('Error disabling camera:', error);
          });
  }
}

// Add this to the initialization code in chitui.js
function initDefaultImages() {
  // Create a default SVG printer icon as base64
  window.DEFAULT_PRINTER_ICON = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMDAiIGhlaWdodD0iMTAwIiB2aWV3Qm94PSIwIDAgMTAwIDEwMCI+PHJlY3Qgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxMDAiIGZpbGw9IiMzMzMiIHJ4PSIxMCIvPjxwYXRoIGQ9Ik0zMCA3MGg0MHYxNUgzMHoiIGZpbGw9IiM2NjYiLz48cGF0aCBkPSJNMjUgMzBoNTB2MzBIMjV6IiBmaWxsPSIjNjY2Ii8+PHBhdGggZD0iTTM1IDIwaDMwdjEwSDM1eiIgZmlsbD0iIzY2NiIvPjxjaXJjbGUgY3g9IjY1IiBjeT0iNDUiIHI9IjUiIGZpbGw9IiM5OTkiLz48L3N2Zz4=';
  
  // Add global error handler for images
  document.addEventListener('error', function(e) {
    if (e.target.tagName === 'IMG') {
      // For printer icons
      if (e.target.classList.contains('printerIcon')) {
        e.target.src = window.DEFAULT_PRINTER_ICON;
      }
      // For the main printer image
      else if (e.target.id === 'printerIcon') {
        e.target.src = window.DEFAULT_PRINTER_ICON;
      }
    }
  }, true);
}

function displayPrinterDetails(printerId) {
  const printer = printers[printerId];
  if (!printer) return;

  // Set printer header info
  document.getElementById('printerName').textContent = printer.name;
  document.getElementById('printerType').textContent = `${printer.brand} ${printer.model}`;
  document.getElementById('printerIcon').src = printer.icon || window.DEFAULT_PRINTER_ICON;

  // Set printer status
  const statusEl = document.getElementById('printerStatus');
  if (printer.status === 'connected') {
    statusEl.innerHTML = '<i class="bi bi-circle-fill text-success me-1"></i> Connected';

    if (printer.machine_status) {
      statusEl.innerHTML += ` - ${printer.machine_status}`;
    }
  } else {
    statusEl.innerHTML = '<i class="bi bi-circle-fill text-danger me-1"></i> Disconnected';
  }

  // Create tabs
  createTabs(printer);
  
  // Initialize camera tab if printer supports camera
  if (printer.supports_camera) {
    createCameraTab(printer);
  }
}

function logDebug(...args) {
  if (DEBUG) {
    console.log('[ChitUI Debug]', ...args);
  }
}

function logError(...args) {
  console.error('[ChitUI Error]', ...args);
}

// static/js/admin.js
const uptimeEl = document.getElementById("uptime");
const printersEl = document.getElementById("connectedPrinters");

async function refreshStatus() {
  let [health, printers] = await Promise.all([
    fetch("/api/health").then(r => r.json()),
    fetch("/api/printer/list").then(r => r.json())
  ]);
  // health.uptime is in seconds
  let secs = health.uptime;
  let d = Math.floor(secs/86400), h = Math.floor((secs%86400)/3600), m = Math.floor((secs%3600)/60);
  uptimeEl.textContent = `${d}d ${h}h ${m}m`;
  printersEl.textContent = Object.keys(printers).length;
}

// kick off, then every 30s
refreshStatus();
setInterval(refreshStatus, 30_000);
