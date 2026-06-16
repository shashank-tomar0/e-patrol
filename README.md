# E-Patrol // Real-Time Behavioral Anomaly Control Center

E-Patrol is an advanced, systems-level multi-modal behavioral reasoning engine designed for crowded public areas. It separates physical camera ingestion from semantic intent analytics, maintaining mathematical anonymity by discarding raw video streams and analyzing only human joint kinematics.

---

## 🌟 Key Features

1. **Privacy-Preserving Intent Recognition**: Runs **MediaPipe Pose** at the edge to extract human skeletons, allowing the system to run in "Anonymised Mode" (skeletons only) to completely protect passenger privacy.
2. **Spatio-Temporal Brain ([analytics.py](backend/analytics.py))**: Tracks joint coordinates across a rolling temporal window to identify Falls, Altercations, and Crowd Panic Stampedes.
3. **Geospatial Patrol Map**: Renders an interactive floor plan showing dynamic crowd density heatmaps and pulsing camera threat nodes.
4. **Voice Alert Dispatcher**: Broadcasts audio dispatches using the browser's native Web Speech API.
5. **Universal Ingestion**: Exposes a configuration input directly on the dashboard where users can connect a laptop webcam (`0`), RTSP CCTV feeds, or raw `.mp4` video files.
6. **Discord / Slack Dispatch Webhook**: Allows judges to paste their own Slack/Discord webhook URL to receive live, rich-embed mobile notifications when crimes trigger.
7. **Neural Search Index**: Utilizes a semantic keyword expansion search engine to query historical safety dossiers (e.g., `"people falling on escalator"`).

---

## 📁 Project Structure

```
├── backend/
│   ├── main.py               # FastAPI websocket and REST endpoints gateway
│   ├── pipeline.py           # Ingestion, optical flow, and MediaPipe pose tracking
│   ├── analytics.py          # Spatiotemporal kinematic heuristic engine
│   ├── agents.py             # Multi-agent verification and incident dossiers
│   ├── db.py                 # Historical DB and vector search keyword index
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── index.html            # Main HTML control center layout
│   ├── css/
│   │   └── style.css         # Glassmorphic cyberpunk styling sheet
│   └── js/
│   │   └── app.js            # WebSockets, Canvas rendering, and UI events
├── .gitignore                # Git ignore constraints (venv, caches, logs)
├── run.py                    # Root bootstrap startup script
└── README.md                 # Project documentation
```

---

## 🚀 Quick Start (Single Command)

E-Patrol includes a **root bootstrap script** that automatically detects the virtual environment, starts the backend server, and opens the dashboard in your default browser.

1. **Activate Environment & Install Requirements** (if not already done):
   ```powershell
   # Windows PowerShell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r backend/requirements.txt
   ```

2. **Run E-Patrol**:
   ```powershell
   python run.py
   ```
   *(Press `Ctrl+C` in the terminal to cleanly shut down all background server subprocesses).*

---

## 🎭 Demonstration Guide for Judges

During your presentation, show the judges these exact features in order:

1. **Nominal State**: Open the dashboard at `http://127.0.0.1:8000/dashboard/`. Show them the glowing green skeletons on the cyber grid. Explain how the system operates under total mathematical privacy.
2. **Interactive Simulation**:
   * Click **Fight** under Camera 01: Skeletons turn red and clash. The browser speaks the alert, and the geospatial map node flashes red.
   * Click **Fall** under Camera 02: A skeleton collapses down the escalator.
   * Click **Intrusion** under Camera 01: A skeleton crosses the yellow tripwire.
3. **Live Webcam test**: Type `0` in the input field of Camera 1 and click **CONNECT**. Toggle off **Anonymized** to **Admin View**. Show the judges themselves mapped as skeletons! Wave your arms rapidly to trigger a live fight warning.
4. **Geospatial Map & Mobile Alert**: Paste the judges' Discord Webhook URL into the header, click **CONNECT**, and trigger a simulated anomaly. Watch them receive the alert directly on their phones.
