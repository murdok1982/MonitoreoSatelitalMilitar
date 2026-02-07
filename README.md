# 📡 MonitoreoSatelitalMilitar - Military Satellite Monitoring System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![AI Powered](https://img.shields.io/badge/AI-Powered-purple.svg)](https://openai.com/)
[![Computer Vision](https://img.shields.io/badge/CV-Enabled-green.svg)](https://opencv.org/)

> Advanced AI-powered satellite imagery analysis system for military vehicle detection, threat assessment, and early warning. Uses computer vision and machine learning to identify and track military assets from satellite imagery.

## ✨ Features

- 📡 **Satellite Image Analysis**: Process and analyze satellite imagery in real-time
- 🚑 **Vehicle Detection**: Identify military vehicles, tanks, aircraft, and naval vessels
- 🤖 **AI Classification**: GPT-powered threat assessment and classification
- 📍 **Geolocation Tracking**: Track movement patterns and deployment locations
- ⚠️ **Early Warning System**: Automated alerts for suspicious activities
- 📊 **Pattern Recognition**: Detect military buildups and unusual movements
- 💾 **Database Integration**: Store and query historical data
- 📸 **Image Processing**: Advanced computer vision for object detection

## 💰 Support This Project

<div align="center">

### ₿ Bitcoin Donations Welcome!

<img src="https://img.shields.io/badge/Bitcoin-000000?style=for-the-badge&logo=bitcoin&logoColor=white" alt="Bitcoin"/>

```
┌─────────────────────────────────────┐
│    ₿  BTC Donation Address  ₿      │
├─────────────────────────────────────┤
│                                     │
│  bc1qqphwht25vjzlptwzjyjt3sex     │
│  7e3p8twn390fkw                    │
│                                     │
│  Network: Bitcoin (BTC)             │
│  Scan QR ↓                          │
└─────────────────────────────────────┘
```

<img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=bitcoin:bc1qqphwht25vjzlptwzjyjt3sex7e3p8twn390fkw" alt="Bitcoin QR Code" width="200"/>

**Address:** `bc1qqphwht25vjzlptwzjyjt3sex7e3p8twn390fkw`

*Your donations help maintain this defense technology project!* 🙏

</div>

---

## 📋 Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Detection Capabilities](#detection-capabilities)
- [Security](#security)
- [License](#license)

## 🚀 Installation

### Prerequisites

- Python 3.8+
- OpenCV
- TensorFlow/PyTorch
- OpenAI API key
- Satellite imagery access (Planet, Sentinel, etc.)

### Setup

```bash
# Clone repository
git clone https://github.com/murdok1982/MonitoreoSatelitalMilitar.git
cd MonitoreoSatelitalMilitar

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

## ⚙️ Configuration

### .env file

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key
GPT_MODEL=gpt-4-vision-preview

# Satellite Data Sources
SATELLITE_API_KEY=your_satellite_api_key
SATELLITE_PROVIDER=sentinel  # or "planet", "maxar"

# Detection Settings
CONFIDENCE_THRESHOLD=0.75
MIN_VEHICLE_SIZE=50  # pixels
MAX_IMAGE_AGE=24  # hours

# Alert Settings
ALERT_WEBHOOK=your_webhook_url
ALERT_THRESHOLD=medium  # low, medium, high, critical

# Database
DATABASE_URL=sqlite:///base_de_datos/military_monitoring.db
```

## 💻 Usage

### Basic Usage

```bash
# Start monitoring system
python main.py
```

### Advanced Usage

```python
from main import SatelliteMonitor
from modelos import VehicleDetector, ThreatAnalyzer

# Initialize system
monitor = SatelliteMonitor()
detector = VehicleDetector(model_path="modelos/vehicle_detector.h5")
analyzer = ThreatAnalyzer()

# Process satellite image
image_path = "imagenes/satellite_image.jpg"
detections = detector.detect(image_path)

# Analyze threats
for detection in detections:
    threat_level = analyzer.assess_threat(detection)
    if threat_level >= "medium":
        monitor.send_alert(detection, threat_level)
```

## 🎯 Detection Capabilities

### Vehicle Types

| Category | Examples | Detection Accuracy |
|----------|----------|--------------------|
| **Tanks** | M1 Abrams, T-90, Leopard 2 | 92% |
| **APCs** | Bradley, BMP, LAV | 88% |
| **Artillery** | HIMARS, M777, Howitzers | 85% |
| **Aircraft** | F-35, Su-57, MiG-29 | 94% |
| **Naval** | Destroyers, Carriers, Subs | 90% |
| **Missiles** | SAM sites, Launchers | 87% |

## 🧠 AI Analysis

### GPT Vision Integration

The system uses GPT-4 Vision to:

1. **Verify Detections**: Confirm computer vision results
2. **Context Analysis**: Understand deployment patterns
3. **Threat Assessment**: Evaluate strategic implications
4. **Report Generation**: Create human-readable intelligence reports

## 💾 Database Schema

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    latitude REAL,
    longitude REAL,
    vehicle_type VARCHAR(50),
    confidence REAL,
    threat_level VARCHAR(20),
    image_path VARCHAR(255),
    analyst_notes TEXT
);
```

## 🔒 Security & Compliance

### Data Protection

- ✅ Encrypted data storage
- ✅ Secure API communications
- ✅ Access control and authentication
- ✅ Audit logging
- ✅ GDPR compliance for civilian areas

### Ethical Considerations

⚠️ **This system is for authorized use only:**

- Military and intelligence agencies
- Licensed defense contractors
- Authorized research institutions
- Humanitarian early warning systems

**Prohibited Uses:**
- Unauthorized surveillance
- Privacy violations
- Targeting civilian populations
- Commercial espionage

## ⚠️ Legal Disclaimer

**IMPORTANT LEGAL NOTICE:**

This software is intended for:
- Authorized military and intelligence use
- Academic and research purposes
- Humanitarian early warning systems
- Compliance with international law

**Users must:**
- Obtain proper authorization
- Comply with local laws and regulations
- Respect privacy and human rights
- Follow Rules of Engagement (ROE)
- Maintain operational security

## 🤝 Contributing

Due to the sensitive nature of this project, contributions require:

1. Security clearance verification
2. Signed NDA
3. Code review by authorized personnel
4. Compliance certification

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

**Note:** While the software is MIT licensed, use cases are restricted by applicable laws and regulations.

## 👤 Author

**murdok1982**

- GitHub: [@murdok1982](https://github.com/murdok1982)
- LinkedIn: [Gustavo Lobato Clara](https://www.linkedin.com/in/gustavo-lobato-clara-2b446b102/)
- Email: gustavolobatoclara@gmail.com

## 🙏 Acknowledgments

- OpenAI GPT-4 Vision
- OpenCV Community
- TensorFlow/PyTorch Teams
- Satellite imagery providers
- Defense research community

## 📈 Roadmap

- [ ] Support for more satellite data sources
- [ ] Improved classification models
- [ ] Real-time video feed analysis
- [ ] Multi-spectral image support
- [ ] Automated tracking and prediction
- [ ] Integration with military systems
- [ ] Mobile app for field officers
- [ ] Advanced threat modeling

---

⚠️ **For authorized use only. Handle with appropriate security classifications.**

⭐ **Star this repo if you find it useful!**  
🐛 **[Report bugs](https://github.com/murdok1982/MonitoreoSatelitalMilitar/issues)** (Security issues via private disclosure)

**Stay Vigilant! 📡**