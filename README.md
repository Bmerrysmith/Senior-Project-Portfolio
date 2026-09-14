# FGCU Traffic Management System

**Cloud-Integrated Digital Twin Dashboard for Infrastructure Monitoring**

[![Deployed on Vercel](https://img.shields.io/badge/Deployed-Vercel-black)](https://cloud5.vercel.app)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## 🎯 Project Overview

An intelligent cloud-based system that monitors road infrastructure using:

- **Quantum Reinforcement Learning (QRL)** for risk classification
- **Computer Vision** for pavement condition analysis via Google Street View
- **Real-time Traffic Data** from Florida DOT 511 API
- **Interactive Web Dashboard** with split-screen map and Street View

**Live Demo:** [https://cloud5.vercel.app](https://cloud5.vercel.app)

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Running the Application](#-running-the-application)
- [Project Structure](#-project-structure)
- [API Documentation](#-api-documentation)
- [Technologies Used](#-technologies-used)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Screenshots](#-screenshots)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

### 🛣️ Pavement Condition Analysis

- **Real-time Image Analysis:** Fetches Google Street View imagery and analyzes pavement conditions
- **Computer Vision Pipeline:**
  - Edge detection (crack identification)
  - Texture analysis (surface smoothness)
  - Color uniformity assessment
  - Brightness gradient scoring
- **PCI Calculation:** Pavement Condition Index (0-100) with detailed breakdowns
- **Continuous Learning:** Model improves with each analysis (stores last 1000 scans)

### 🚦 Traffic Monitoring

- **Live Traffic Data:** Florida DOT 511 API integration
- **15-Mile Radius:** Filters incidents near FGCU campus
- **Real-time Overlay:** Google Maps traffic layer
- **Incident Types:** Accidents, construction, road closures

### ⚛️ Quantum Machine Learning

- **QRL Agent:** 2-qubit quantum circuit for risk classification
- **Risk Levels:**
  - 🟢 **NORMAL** - Excellent condition
  - 🟡 **WATCH** - Monitor closely
  - 🟠 **CONGESTED** - Action needed
  - 🔴 **CRITICAL** - Urgent repair
- **Confidence Scoring:** 85-97% accuracy range
- **Adaptive Learning:** Updates patterns every 10 analyses

### 🗺️ Interactive Dashboard

- **Split-Screen View:** Map (50%) + Street View (50%)
- **Click-to-Analyze:** Select any location for instant pavement scan
- **Drag Pegman:** Explore Street View panoramas
- **Traffic Toggle:** Show/hide real-time traffic conditions
- **Mobile Responsive:** Works on tablets and phones

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Vercel)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  │
│  │ index.html  │  │ pavement-   │  │ integrated-      │  │
│  │             │  │ viewer.html │  │ traffic-         │  │
│  │             │  │             │  │ viewer.html      │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘  │
│         │                 │                   │            │
│         └─────────────────┴───────────────────┘            │
│                           │                                │
└───────────────────────────┼────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend (Local/Azure)                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              FastAPI REST API                        │  │
│  │  ┌────────────────┐  ┌──────────────────────────┐   │  │
│  │  │ Pavement       │  │ Traffic Endpoints        │   │  │
│  │  │ Condition API  │  │ /api/real-traffic/fdot   │   │  │
│  │  │ /api/pavement  │  │ /api/real-traffic/status │   │  │
│  │  └────────┬───────┘  └────────┬─────────────────┘   │  │
│  │           │                    │                     │  │
│  │           ▼                    ▼                     │  │
│  │  ┌────────────────┐  ┌──────────────────────────┐   │  │
│  │  │ Computer       │  │ Florida DOT 511 Client   │   │  │
│  │  │ Vision Module  │  │                          │   │  │
│  │  │ (PIL, NumPy)   │  │                          │   │  │
│  │  └────────┬───────┘  └──────────────────────────┘   │  │
│  │           │                                          │  │
│  │           ▼                                          │  │
│  │  ┌────────────────────────────────────────────┐     │  │
│  │  │   Quantum Reinforcement Learning Agent     │     │  │
│  │  │   (2 qubits, 2 layers)                     │     │  │
│  │  │   Risk Classification: NORMAL/WATCH/       │     │  │
│  │  │   CONGESTED/CRITICAL                       │     │  │
│  │  └────────────────────────────────────────────┘     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  External Services                          │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────┐  │
│  │ Google Maps  │  │ Florida DOT   │  │ Azure Digital  │  │
│  │ API          │  │ 511 API       │  │ Twins          │  │
│  │ - Street View│  │ - Traffic     │  │ (Optional)     │  │
│  │ - Geocoding  │  │   Incidents   │  │                │  │
│  └──────────────┘  └───────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Prerequisites

### Required Software

- **Python:** 3.11 or higher
- **Node.js:** 16+ (for frontend development, optional)
- **Git:** Latest version

### API Keys

1. **Google Maps API Key**

   - Enable: Maps JavaScript API, Street View Static API, Geocoding API
   - Get one: [Google Cloud Console](https://console.cloud.google.com/)

2. **Florida DOT 511 API** (Optional)
   - Public access available at: https://fl511.com

### System Requirements

- **RAM:** 4GB minimum
- **Storage:** 10GB free space
- **Network:** Stable internet connection for API calls

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/nixguin/Cloud5.git
cd Cloud5
```

### 2. Set Up Python Virtual Environment

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Backend Dependencies

```bash
cd clean
pip install -r requirements-backend-only.txt
```

**Dependencies include:**

- FastAPI (0.104+)
- Uvicorn (ASGI server)
- Pillow (image processing)
- NumPy (numerical computing)
- Requests (HTTP client)
- Azure SDK (optional)

### 4. Configure API Keys

Create a `.env` file in the `clean/` directory:

```bash
# .env
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
FDOT_API_KEY=optional_fdot_key_here
AZURE_CLIENT_ID=optional_azure_id_here
```

**Or update directly in code:**

Edit `clean/api/pavement_condition.py`:

```python
STREET_VIEW_API_KEY = "YOUR_API_KEY_HERE"
```

Edit `clean/web/index.html` (and other HTML files):

```html
<script src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY_HERE&callback=initMap"></script>
```

---

## 🎮 Running the Application

### Option 1: Local Development (Recommended)

**Start Backend:**

```bash
cd clean
python -m uvicorn api.main:app --reload --port 8000
```

**Start Frontend:**
Open a new terminal:

```bash
cd clean/web
python -m http.server 8080
```

**Access Application:**

- Frontend: http://localhost:8080/index.html
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option 2: Production Deployment (Vercel)

The frontend is already deployed at: https://cloud5.vercel.app

**To deploy your own:**

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel --prod
```

**Note:** Backend runs in demo mode on Vercel. For full functionality, run backend locally.

---

## 📁 Project Structure

```
cloud-computing-project/
│
├── clean/                              # Main application directory
│   ├── web/                            # Frontend files
│   │   ├── index.html                  # Main viewer (recommended)
│   │   ├── pavement-viewer.html        # Dedicated pavement analysis
│   │   ├── integrated-traffic-viewer.html  # Traffic + pavement
│   │   ├── css/
│   │   │   ├── styles.css              # Main styles
│   │   │   ├── pavement-viewer.css     # Pavement viewer styles
│   │   │   └── integrated-traffic-viewer.css
│   │   ├── js/
│   │   │   ├── app.js                  # Main application logic
│   │   │   ├── pavement-viewer.js      # Pavement viewer logic
│   │   │   └── integrated-traffic-viewer.js
│   │   └── favicon.ico
│   │
│   ├── api/                            # Backend API
│   │   ├── main.py                     # FastAPI application entry
│   │   ├── pavement_condition.py       # Pavement analysis endpoints
│   │   ├── fdot_integration.py         # Florida DOT traffic client
│   │   ├── adt_client.py               # Azure Digital Twins (optional)
│   │   ├── cesium_integration.py       # 3D visualization (future)
│   │   └── backend_status.py           # Health check endpoint
│   │
│   ├── ai/                             # Machine Learning
│   │   ├── qrl_traffic_agent.py        # Quantum RL implementation
│   │   └── traffic_forecasting.py      # Traffic prediction models
│   │
│   ├── models/                         # Data models
│   │   ├── Road.json                   # Road infrastructure schema
│   │   ├── TrafficSensor.json          # Sensor data schema
│   │   └── PavementAsset.json          # Pavement asset schema
│   │
│   ├── requirements-backend-only.txt   # Backend Python dependencies
│   ├── requirements.txt                # Full dependencies
│   └── start.py                        # Quick start launcher
│
├── vercel.json                         # Vercel deployment config
├── README.md                           # This file
└── .gitignore                          # Git ignore rules
```

---

## 📚 API Documentation

### Base URL

- **Local:** `http://localhost:8000`
- **Production:** Backend runs locally

### Endpoints

#### 1. Pavement Condition Analysis

```http
POST /api/pavement-condition
Content-Type: application/json

{
  "latitude": 26.4625,
  "longitude": -81.7717,
  "heading": 0,
  "pitch": -10
}
```

**Response:**

```json
{
  "pci": 78.5,
  "condition": "Good",
  "confidence": 0.92,
  "timestamp": "2025-12-04T10:30:00",
  "learning_status": {
    "analysis_number": 42,
    "continuous_learning": true,
    "model_improving": true
  },
  "location": {
    "latitude": 26.4625,
    "longitude": -81.7717
  },
  "details": {
    "qrl_analysis": {
      "risk_label": "NORMAL",
      "quantum_confidence": 0.89,
      "risk_probabilities": {
        "NORMAL": 0.7,
        "WATCH": 0.2,
        "CONGESTED": 0.08,
        "CRITICAL": 0.02
      },
      "analysis_method": "Quantum Reinforcement Learning"
    },
    "street_view_analysis": {
      "pci_from_image": 78.5,
      "crack_score": 15.2,
      "smoothness_score": 82.3,
      "uniformity_score": 88.1,
      "condition_score": 76.8,
      "avg_brightness": 85.4,
      "detected_distress": ["Minor Cracking"]
    },
    "distress_types": ["Minor Cracking"],
    "severity": "Low",
    "recommended_action": "Continue monitoring - Road in good condition"
  }
}
```

#### 2. Florida DOT Traffic Data

```http
GET /api/real-traffic/fdot
```

**Response:**

```json
{
  "status": "success",
  "timestamp": "2025-12-04T10:30:00",
  "count": 5,
  "incidents": [
    {
      "id": "12345",
      "type": "accident",
      "description": "Multi-vehicle accident on I-75",
      "location": {
        "latitude": 26.4625,
        "longitude": -81.7717,
        "description": "I-75 Northbound near mile marker 141"
      },
      "severity": "major",
      "start_time": "2025-12-04T09:15:00",
      "lanes_affected": 2
    }
  ]
}
```

#### 3. Model Status

```http
GET /api/pavement-model-status
```

**Response:**

```json
{
  "model_loaded": true,
  "qrl_agent": "active",
  "status": "QRL-enhanced predictions with continuous learning",
  "timestamp": "2025-12-04T10:30:00Z",
  "learning_metrics": {
    "total_analyses": 156,
    "learning_history_size": 156,
    "continuous_learning": true,
    "update_frequency": "Every 10 analyses"
  },
  "capabilities": {
    "quantum_analysis": true,
    "risk_classification": true,
    "confidence_scoring": true,
    "distress_detection": true,
    "continuous_learning": true
  },
  "qrl_info": {
    "n_qubits": 2,
    "n_layers": 2,
    "risk_levels": ["NORMAL", "WATCH", "CONGESTED", "CRITICAL"]
  }
}
```

---

## 🛠️ Technologies Used

### Frontend

- **HTML5/CSS3:** Structure and styling
- **JavaScript (ES6+):** Application logic
- **Google Maps JavaScript API:** Interactive mapping
- **Google Street View API:** Panoramic imagery
- **Responsive Design:** Mobile-friendly interface

### Backend

- **Python 3.11:** Core language
- **FastAPI:** High-performance web framework
- **Uvicorn:** ASGI server
- **Pillow (PIL):** Image processing
- **NumPy:** Numerical computations
- **Requests:** HTTP client for external APIs

### Machine Learning

- **Quantum Reinforcement Learning:** Custom implementation
- **Computer Vision:** Edge detection, texture analysis
- **Continuous Learning:** Adaptive model improvement

### Cloud & DevOps

- **Vercel:** Serverless deployment, CDN
- **GitHub:** Version control, CI/CD
- **Azure Digital Twins (Optional):** Infrastructure modeling

### External APIs

- **Google Maps Platform:** Mapping, Street View, Geocoding
- **Florida DOT 511:** Real-time traffic data

---

## ⚙️ Configuration

### Frontend Configuration

**Update API Key in HTML files:**

```html
<!-- clean/web/index.html, pavement-viewer.html, integrated-traffic-viewer.html -->
<script src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY_HERE&callback=initMap&libraries=places&loading=async"></script>
```

**Configure Backend URL:**

```javascript
// clean/web/js/app.js (and other JS files)
const API_BASE =
  window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : window.location.origin;
```

### Backend Configuration

**Update Street View API Key:**

```python
# clean/api/pavement_condition.py
STREET_VIEW_API_KEY = "YOUR_API_KEY_HERE"
```

**Configure CORS (if needed):**

```python
# clean/api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🌐 Deployment

### Vercel Deployment (Frontend Only)

1. **Install Vercel CLI:**

```bash
npm install -g vercel
```

2. **Login:**

```bash
vercel login
```

3. **Deploy:**

```bash
vercel --prod
```

4. **Verify:** Check `vercel.json` configuration:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "clean/web/**",
      "use": "@vercel/static"
    }
  ],
  "routes": [
    {
      "src": "/",
      "dest": "/clean/web/index.html"
    },
    {
      "src": "/(.*)",
      "dest": "/clean/web/$1"
    }
  ]
}
```

### Azure Functions (Backend - Future)

```bash
# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4

# Initialize
func init --python

# Deploy
func azure functionapp publish <APP_NAME>
```

---

## 📸 Screenshots

### Main Dashboard (index.html)

![Main Dashboard](docs/screenshots/main-dashboard.png)

- Split-screen view with map and Street View
- Real-time pavement condition analysis
- Traffic layer toggle

### Pavement Viewer (pavement-viewer.html)

![Pavement Viewer](docs/screenshots/pavement-viewer.png)

- Dedicated QRL analysis interface
- Detailed risk classification
- Continuous learning metrics

### Integrated Traffic Viewer

![Integrated Viewer](docs/screenshots/integrated-viewer.png)

- Combined traffic and pavement monitoring
- Florida DOT incident overlay
- Comprehensive infrastructure insights

---

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. **Fork the repository**
2. **Create a feature branch:**

```bash
git checkout -b feature/amazing-feature
```

3. **Commit your changes:**

```bash
git commit -m "Add amazing feature"
```

4. **Push to branch:**

```bash
git push origin feature/amazing-feature
```

5. **Open a Pull Request**

### Code Style Guidelines

- **Python:** Follow PEP 8
- **JavaScript:** Use ES6+ syntax
- **Comments:** Document complex logic
- **Commits:** Use descriptive messages

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Team

- **[Member 1]** - Backend Development, QRL Implementation
- **[Member 2]** - Frontend Development, Google Maps Integration
- **[Member 3]** - Traffic Data Integration, Testing

---

## 🙏 Acknowledgments

- **Florida Gulf Coast University** - Project support
- **Google Maps Platform** - Mapping and Street View APIs
- **Florida DOT** - Real-time traffic data
- **Open Source Community** - Libraries and frameworks

---

## 📞 Support

For questions or issues:

- **GitHub Issues:** [Create an issue](https://github.com/nixguin/Cloud5/issues)
- **Email:** [your-email@fgcu.edu]
- **Documentation:** See [FINAL_REPORT.md](FINAL_REPORT.md)

---

## 🗺️ Roadmap

- [ ] Azure Functions backend deployment
- [ ] Mobile app development
- [ ] IoT sensor integration
- [ ] 3D visualization with Cesium.js
- [ ] Predictive maintenance algorithms
- [ ] Multi-city expansion

---

**Built by Cloud5**

_Last Updated: December 4, 2025_
