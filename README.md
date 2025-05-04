# ChitUI

A modern web UI for managing Chitubox SDCP 3.0-compatible resin 3D printers.

## ✨ Features

- **🔍 Smart Discovery** - Automatically detect SDCP-compatible printers on your local network
- **📊 Real-time Monitoring** - Track print progress, status, and parameters with live updates
- **📁 File Management** - Upload, organize and manage print files directly from the web interface
- **📷 Camera Integration** - Live stream from printers with built-in cameras (like Elegoo Saturn 4 Ultra)
- **🖱️ Remote Control** - Start, pause, resume and stop prints from anywhere on your network
- **👥 Multi-user Support** - Role-based authentication with admin and user privileges
- **🌓 Dark/Light Themes** - Modern, responsive UI with automatic and manual theme switching
- **📱 Mobile Friendly** - Control your printers from any device with a web browser
- **📦 Docker Ready** - Easy deployment using Docker with host network support



## 🖼️ Screenshots
![Printer List](https://github.com/user-attachments/assets/9077c509-8605-45e3-84ce-fd214f875b49)
![File Management](https://github.com/user-attachments/assets/b7696317-efa1-403d-b411-40d320f0ad1e)
![Print Status](https://github.com/user-attachments/assets/df432a33-8e3c-43f1-a9ee-82a39febde0a)
![Info](https://github.com/user-attachments/assets/7a7aadc4-52c0-4999-9fcf-8d0e5031d221)
![Admin](https://github.com/user-attachments/assets/a89df49b-ad1e-40b9-9527-9e2d91e7985b)


## 🚀 Installation

### Prerequisites

- Python 3.10 or newer
- Network access to your SDCP-compatible 3D printers
- For camera functionality: working cameras on your printers

### Method 1: Standard Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/chitui.git
   cd chitui
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   
   # On Windows:
   .venv\Scripts\activate
   
   # On Linux/Mac:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the database**:
   ```bash
   python main.py init-db
   ```

5. **Configure settings** (optional):
   ```bash
   cp config/default.yaml config/config.yaml
   # Edit config.yaml with your preferred settings
   ```

6. **Launch the application**:
   ```bash
   python main.py
   ```

   By default, ChitUI will be available at `http://localhost:54780` with the default login credentials (admin/admin).

### Method 2: Docker Installation

#### Using Docker Run:

```bash
docker build -t chitui:latest .
docker run --rm --name chitui --net=host \
  -v ./config:/app/config \
  -v ./uploads:/app/uploads \
  -v ./logs:/app/logs \
  -v ./data:/app/data \
  -e ADMIN_PASSWORD=yourpassword \
  chitui:latest
```

#### Using Docker Compose:

1. **Create docker-compose.yml**:
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
         - ./data:/app/data
       environment:
         - PORT=54780
         - HOST=0.0.0.0
         - DEBUG=false
         - LOG_LEVEL=INFO
         - ADMIN_USER=admin
         - ADMIN_PASSWORD=yourpassword
       restart: unless-stopped
   ```

2. **Launch with docker-compose**:
   ```bash
   docker-compose up -d
   ```

> **⚠️ Important Note:** ChitUI requires host networking for printer discovery to work properly. This is because it needs to broadcast UDP packets on your local network to find printers.

## 📋 Usage

### Command Line Options

```
ChitUI - Web UI for Chitubox SDCP 3.0 resin printers

Options:
  -c, --config PATH      Path to configuration file
  -h, --host TEXT        Host to bind the server to
  -p, --port INTEGER     Port to bind the server to
  -d, --debug            Enable debug mode
  -l, --log-level TEXT   Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --db, --database TEXT  Database URI (e.g., sqlite:///chitui.db)
  --help                 Show this message and exit.

Commands:
  backup-db  Backup the database to a file
  init-db    Initialize or upgrade the database
  run        Run the ChitUI web server (default)
```

### Database Management

#### Database Configuration

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

#### Database Backup

Create a database backup:
```bash
python main.py backup-db
```

Specify a custom backup location:
```bash
python main.py backup-db --backup-dir /path/to/backups
```

## ⚙️ Configuration

### Configuration File

ChitUI can be configured using a YAML configuration file at `config/config.yaml`:

```yaml
# Network settings
host: "0.0.0.0"
port: 54780

# Application settings
debug: false
log_level: "INFO"
upload_folder: "uploads"
log_folder: "logs"

# Database settings
database_uri: "sqlite:///chitui.db"

# User settings
admin_user: "admin"
admin_password: "admin"
```

### Environment Variables

You can also configure ChitUI using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Host address to bind to | "0.0.0.0" |
| `PORT` | Port to listen on | 54780 |
| `DEBUG` | Enable debug mode | false |
| `LOG_LEVEL` | Logging level | "INFO" |
| `UPLOAD_FOLDER` | Directory for temporary file uploads | "uploads" |
| `LOG_FOLDER` | Directory for log files | "logs" |
| `ADMIN_USER` | Default admin username | "admin" |
| `ADMIN_PASSWORD` | Default admin password | "admin" |
| `DATABASE_URI` | Database connection URI | "sqlite:///chitui.db" |

## 🖨️ Supported Printers

ChitUI is compatible with printers that support the Chitubox SDCP 3.0 protocol, including:

### Elegoo Saturn Series
- Saturn Ultra 16K
- Saturn 4 Ultra
- Saturn 4
- Saturn 3 Ultra
- Saturn 3
- Saturn 2
- Saturn

### Elegoo Mars Series
- Mars 4 Ultra
- Mars 4
- Mars 3 Ultra
- Mars 3
- Mars 2

### Other Manufacturers
- Any printer that supports the SDCP 3.0 protocol

> **📷 Camera Support**: Live camera streaming is available on models with built-in cameras, such as the Saturn 4 Ultra, Saturn Ultra 16K, and others.

## 🔍 Troubleshooting

### Common Issues

1. **Cannot discover printers**:
   - Make sure your printers are on the same network as ChitUI
   - Check if UDP port 3000 is not blocked by your firewall
   - Try adding printers manually using their IP addresses

2. **Camera streaming not working**:
   - Verify that your printer model has a built-in camera
   - Ensure the printer firmware is up to date
   - Check if the camera is enabled in the printer settings

3. **File uploads failing**:
   - Check the ChitUI logs for detailed error information
   - Ensure the file type is supported (.ctb, .goo, .prz)
   - Verify that the uploads directory is writable

### Getting Help

- Check the logs in the `logs` directory for more detailed error information
- File an issue on the GitHub repository if you encounter a bug
- Join our Discord server for community support

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit your changes**: `git commit -m 'Add some amazing feature'`
4. **Push to the branch**: `git push origin feature/amazing-feature`
5. **Open a Pull Request**

### Development Setup

1. Clone the repository and set up a virtual environment as described in the installation section
2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
3. Run tests:
   ```bash
   pytest
   ```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact

- GitHub Issues: [https://github.com/antoinebou12/chitui/issues](https://github.com/yourusername/chitui/issues)
- Email: your.email@example.com
- Discord: [Join our server](https://discord.gg/yourlink)

---

<p align="center">
Made with ❤️ for the 3D printing community
</p>
