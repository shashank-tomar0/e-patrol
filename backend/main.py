import asyncio
import json
import logging
from typing import Dict, List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn

from pipeline import VideoPipeline
from analytics import AnalyticsEngine
from agents import SceneVerifierAgent, IncidentSummarizerAgent
from db import EventDatabase

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GatewayServer")

app = FastAPI(title="E-Patrol API Gateway")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core Instances
db = EventDatabase()
verifier_agent = SceneVerifierAgent()
summarizer_agent = IncidentSummarizerAgent()

# Cameras Setup
# We support multiple mock/simulated cameras by default
cameras: Dict[int, VideoPipeline] = {
    1: VideoPipeline(camera_id=1, source="mock"),
    2: VideoPipeline(camera_id=2, source="mock")
}
# Set camera descriptive locations
camera_locations = {
    1: "Subway Platform 2",
    2: "North Escalator"
}

analytics_engines: Dict[int, AnalyticsEngine] = {
    1: AnalyticsEngine(),
    2: AnalyticsEngine()
}

# Active WebSocket connections
active_connections: Dict[int, Set[WebSocket]] = {
    1: set(),
    2: set()
}

# Global Broadcast WebSocket (for alerts across all cameras)
alert_connections: Set[WebSocket] = set()

# Lock for background tasks
background_tasks = []

async def camera_processing_loop(camera_id: int):
    """Background loop that continually pulls frames, processes them, runs analytics, and broadcasts telemetry."""
    pipeline = cameras[camera_id]
    analytics = analytics_engines[camera_id]
    location = camera_locations[camera_id]
    
    pipeline.start()
    logger.info(f"Processing loop started for Camera {camera_id} ({location})")
    
    try:
        while pipeline.running:
            # Process frame / telemetry (runs optical flow + pose estimation)
            telemetry = pipeline.process_frame_data()
            if telemetry is None:
                await asyncio.sleep(0.05)
                continue
                
            # Run spatio-temporal brain analytics to detect anomalies
            anomalies = analytics.update(telemetry)
            
            # Handle detected anomalies
            for anomaly in anomalies:
                logger.info(f"Anomaly detected on Camera {camera_id}: {anomaly['type']}")
                
                # Agent 1: Verify rules against scene location
                verifier_data = verifier_agent.verify_event(
                    event_type=anomaly["type"],
                    location=location,
                    confidence=anomaly["confidence"],
                    telemetry=telemetry
                )
                
                # Agent 2: Summarize (Async task so we don't block the video stream!)
                asyncio.create_task(
                    generate_and_log_dossier(camera_id, anomaly["type"], location, verifier_data, telemetry)
                )

            # Package coordinates & flow metadata to stream to UI
            stream_payload = {
                "camera_id": camera_id,
                "location": location,
                "timestamp": telemetry["timestamp"],
                "skeletons": telemetry["skeletons"],
                "flow_vectors": telemetry["flow_vectors"],
                "density": telemetry["crowd_density"],
                "speed": telemetry["crowd_speed"],
                "active_anomalies": anomalies
            }
            
            # Broadcast to web socket connections subscribed to this camera
            sockets = active_connections[camera_id].copy()
            if sockets:
                message = json.dumps(stream_payload)
                for ws in sockets:
                    try:
                        await ws.send_text(message)
                    except Exception:
                        active_connections[camera_id].remove(ws)
            
            # Control processing rate (approx 15 FPS to ensure smooth web rendering and low CPU load)
            await asyncio.sleep(0.066)
            
    except Exception as e:
        logger.error(f"Error in Camera {camera_id} loop: {e}", exc_info=True)
    finally:
        pipeline.stop()
        logger.info(f"Processing loop stopped for Camera {camera_id}")

async def generate_and_log_dossier(camera_id, event_type, location, verifier_data, telemetry):
    """Runs summarizer agent asynchronously, logs to Vector DB, and alerts clients."""
    dossier = await summarizer_agent.generate_dossier(
        event_type=event_type,
        location=location,
        verifier_data=verifier_data,
        telemetry=telemetry
    )
    
    # Save the event record in our historical database
    event_record = db.add_event(
        event_type=event_type,
        location=location,
        severity=verifier_data["severity"],
        dossier=dossier,
        telemetry_snapshot=telemetry
    )
    
    # Broadcast alert instantly to all dashboard UI alerts listeners
    alert_payload = {
        "event": "CRITICAL_ALERT",
        "camera_id": camera_id,
        "location": location,
        "record": event_record
    }
    
    message = json.dumps(alert_payload)
    for ws in alert_connections.copy():
        try:
            await ws.send_text(message)
        except Exception:
            alert_connections.remove(ws)

@app.on_event("startup")
async def startup_event():
    # Start background processing tasks for both cameras
    for cid in cameras:
        task = asyncio.create_task(camera_processing_loop(cid))
        background_tasks.append(task)
    logger.info("Startup complete: Background camera tasks initialized.")

@app.on_event("shutdown")
async def shutdown_event():
    # Stop all cameras
    for cid, pipe in cameras.items():
        pipe.stop()
    for task in background_tasks:
        task.cancel()
    logger.info("Shutdown complete: Camera pipelines stopped.")

# WebSockets
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await websocket.accept()
    alert_connections.add(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep connection alive
    except WebSocketDisconnect:
        alert_connections.remove(websocket)

@app.websocket("/ws/stream/{camera_id}")
async def websocket_stream(websocket: WebSocket, camera_id: int):
    if camera_id not in active_connections:
        await websocket.close(code=4000, reason="Invalid Camera ID")
        return
        
    await websocket.accept()
    active_connections[camera_id].add(websocket)
    try:
        while True:
            # Sockets can receive state controls from UI
            data = await websocket.receive_text()
            payload = json.loads(data)
            if "simulate_state" in payload:
                cameras[camera_id].set_simulation_state(payload["simulate_state"])
    except WebSocketDisconnect:
        active_connections[camera_id].remove(websocket)
    except Exception as e:
        logger.error(f"Error in WS stream {camera_id}: {e}")
        if websocket in active_connections[camera_id]:
            active_connections[camera_id].remove(websocket)

@app.post("/api/camera/configure/{camera_id}")
async def configure_camera(camera_id: int, payload: dict):
    """Dynamically restarts a camera stream with a new source (e.g. RTSP link, webcam index '0', or MP4 file)."""
    if camera_id not in cameras:
        return {"error": "Camera not found"}, 404
        
    source = payload.get("source", "mock")
    location = payload.get("location", camera_locations[camera_id])
    
    logger.info(f"Reconfiguring Camera {camera_id} with source: {source}, location: {location}")
    
    # Stop existing loop
    cameras[camera_id].stop()
    await asyncio.sleep(0.2) # Allow loop to break
    
    # Reinitialize pipeline
    # Check if source is numeric (webcam index)
    if source.isdigit():
        source = int(source)
        
    cameras[camera_id] = VideoPipeline(camera_id=camera_id, source=source)
    camera_locations[camera_id] = location
    
    # Restart the loop task
    cameras[camera_id].start()
    task = asyncio.create_task(camera_processing_loop(camera_id))
    background_tasks.append(task)
    
    return {
        "status": "success",
        "camera_id": camera_id,
        "location": location,
        "source": str(source)
    }

# REST Endpoints
@app.get("/api/events")
def get_events():
    """Returns list of all logged safety incident records."""
    return db.get_all_events()

@app.get("/api/search")
def search_events(q: str = ""):
    """Performs semantic video indexing search across logged dossier text."""
    return db.search_events(q)

@app.post("/api/simulate/{camera_id}/{state}")
def simulate_camera_anomaly(camera_id: int, state: str):
    """REST trigger to set camera simulation state (normal, fight, fall, panic)."""
    if camera_id not in cameras:
        return {"error": "Camera not found"}, 404
    cameras[camera_id].set_simulation_state(state)
    return {"status": "success", "camera_id": camera_id, "state": state}

# Serve Frontend
@app.get("/")
def redirect_to_dashboard():
    return RedirectResponse(url="/dashboard/")

# Mount the static files folder (holds frontend index.html, index.css, app.js)
try:
    app.mount("/dashboard", StaticFiles(directory="../frontend", html=True), name="frontend")
except Exception as e:
    logger.error(f"Could not mount static frontend folder: {e}")
