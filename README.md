# DNSTT Manager

DNSTT Manager is a centralized UI dashboard and API for managing `dnstt-client` and `slipstream-client` tunneling configurations. It simplifies running, monitoring, and load-balancing multiple DNS connections.

## Features
- **Centralized Dashboard**: Easily create, configure, start, and stop your `dnstt` and `slipstream` clients.
- **Advanced Load Balancing**: Intelligent TCP/UDP load-balancing across multiple tunneling endpoints, tracking pings, latencies, active connections, and historical throughput statistics.
- **Deep Monitoring**: Native UI graphs (via Chart.js) visualization of active upload/download bandwidth.
- **Process Management**: Robust process handling, live log viewing features with search and delete functions, and seamless health-checks that ensure you're always connected to the fastest and most reliable endpoints.
- **Responsive Design**: Modern and sleek mobile-first UI with collapsible sidebars and responsive card layouts.
- **RESTful API**: Manage and interact with your tunnels through a well-documented FastAPI backend.

## Requirements
- Python 3.10+
- `uv` (recommended) or `pip`
- `dnstt-client`
- `slipstream-client`

## Getting Started

1. Clone the repository and optionally set up a virtual environment.
2. Install the necessary Python packages: `uv pip install -r pyproject.toml` (or use `uv sync`).
3. Run the application:
   ```bash
   uv run python main.py --host 0.0.0.0 --port 8080
   ```
4. Access the dashboard via your browser at `http://localhost:8080`.
5. Enter the Settings panel to define the paths to your tunnel binaries if they differ from the defaults.

## Technologies
- **Backend**: FastAPI, SQLAlchemy, SQLite, Uvicorn
- **Frontend**: Vanilla JavaScript (ESM + differential DOM rendering), HTML5, custom CSS. No weighty JS frameworks.

## License
MIT License
