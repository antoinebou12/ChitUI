# ChitUI

A modern web UI for Chitubox SDCP 3.0 resin printers.

## Features

- 🖨️ **Printer Discovery**: Automatically find SDCP-compatible printers on your network
- 🔄 **Realtime Status**: Monitor printer status in real-time
- 📁 **File Management**: Upload and manage print files
- 📺 **Camera Support**: View livestream from printers with camera support (like Elegoo Saturn 4 Ultra)
- 🔒 **Authentication**: User login system with admin controls
- 🎛️ **Print Controls**: Start, pause, and stop prints remotely
- 💾 **Database Storage**: Store printer configurations, user accounts, and print history
- 🌓 **Dark/Light Mode**: Modern UI with theme support

## Installation

### Prerequisites

- Python 3.10 or newer
- Network access to your 3D printers

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/chitui.git
   cd chitui
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   ```

3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Linux/Mac: `source .venv/bin/activate`

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Initialize the database:
   ```bash
   python main.py init-db
   ```

6. (Optional) Edit the configuration file:
   ```bash
   cp config/config.yaml.example config/config.yaml
   # Edit config.yaml with your preferred settings
   ```

## Usage

### Starting the Server

```bash
python main.py
```

By default, ChitUI will be available at `http://localhost:54780` with the default login credentials (admin/admin).

### Command Line Options

```
ChitUI - Web UI for Chitubox SDCP 3.0 resin printers

Options:
  -c, --config PATH    Path to configuration file
  -h, --host TEXT      Host to bind the server to
  -p, --port INTEGER   Port to bind the server to
  -d, --debug          Enable debug mode
  -l, --log-level TEXT Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --db, --database TEXT Database URI (e.g., sqlite:///chitui.db)
  --help               Show this message and exit.

Commands:
  backup-db  Backup the database to a file
  init-db    Initialize or upgrade the database
  run        Run the ChitUI web server (default)
```

### Database Configuration

ChitUI supports multiple database backends:

1. **SQLite** (default):
   ```yaml
   database_uri: "sqlite:///chitui.db"
   ```

2. **MySQL**:
   ```yaml
   database_uri: "mysql+pymysql://username:password@localhost/chitui"
   ```

3. **PostgreSQL**:
   ```yaml
   database_uri: "postgresql+psycopg2://username:password@localhost/chitui"
   ```

### Backing Up the Database

```bash
python main.py backup-db
```

This will create a backup in the "backups" directory. You can specify a different backup location:

```bash
python main.py backup-db --backup-dir /path/to/backups
```

## Docker

ChitUI needs to broadcast UDP messages on your network segment to discover printers. Running ChitUI in Docker requires host networking to be enabled for the container:

```bash
docker build -t chitui:latest .
docker run --rm --name chitui --net=host chitui:latest
```

### Docker Compose

```yaml
version: '3.8'

services:
  chitui:
    build: .
    image: chitui:latest
    container_name: chitui
    network_mode: host
    volumes:
      - ./config:/app/config
      - ./uploads:/app/uploads
      - ./logs:/app/logs
      - ./backups:/app/backups
      - ./data:/app/data
    environment:
      - PORT=54780
      - HOST=0.0.0.0
      - DEBUG=false
      - LOG_LEVEL=INFO
      - ADMIN_USER=admin
      - ADMIN_PASSWORD=admin
    restart: unless-stopped
```

## Environment Variables

ChitUI can be configured using environment variables:

- `HOST`: Host address to bind to (default: "0.0.0.0")
- `PORT`: Port to listen on (default: 54780)
- `DEBUG`: Enable debug mode (default: false)
- `LOG_LEVEL`: Logging level (default: "INFO")
- `UPLOAD_FOLDER`: Directory for temporary file uploads (default: "uploads")
- `LOG_FOLDER`: Directory for log files (default: "logs")
- `ADMIN_USER`: Default admin username (default: "admin")
- `ADMIN_PASSWORD`: Default admin password (default: "admin")
- `DATABASE_URI`: Database connection URI (default: "sqlite:///chitui.db")

## Supported Printers

ChitUI works with Chitubox SDCP 3.0 protocol printers, including:

- Elegoo Saturn series (Saturn, Saturn 2, Saturn 3, Saturn 4, Saturn 4 Ultra)
- Elegoo Mars series (Mars 3, Mars 3 Ultra, Mars 4, Mars 4 Ultra)
- Other printers using the SDCP 3.0 protocol

Camera streaming is supported on models with built-in cameras, like the Elegoo Saturn 4 Ultra.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.