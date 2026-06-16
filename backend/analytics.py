import numpy as np
import time
import logging
from collections import deque

logger = logging.getLogger("AnalyticsEngine")

class AnalyticsEngine:
    def __init__(self, buffer_size=60):
        # We keep a rolling history of telemetry data (e.g., 2 seconds of video at 30 fps)
        self.buffer_size = buffer_size
        self.history = deque(maxlen=buffer_size)
        
        # Detection Thresholds
        self.FALL_VELOCITY_THRESHOLD = 0.8   # Normalized coordinate drop rate per second
        self.FIGHT_VELOCITY_THRESHOLD = 2.5   # Rapid joint movement threshold
        self.FIGHT_PROXIMITY_THRESHOLD = 0.25 # Normalized distance between skeletons
        self.PANIC_CROWD_SPEED_THRESHOLD = 4.0 # Flow speed for panic warning
        
        # Event Cooldowns (to prevent flooding alerts)
        self.cooldowns = {
            "fall": 0.0,
            "fight": 0.0,
            "panic": 0.0,
            "intrusion": 0.0
        }
        self.COOLDOWN_PERIOD = 5.0 # seconds
        self.INTRUSION_Y_THRESHOLD = 0.76 # Safety yellow line horizontal limit

    def update(self, telemetry):
        """Adds new telemetry frame to history and runs spatio-temporal anomaly detection."""
        self.history.append(telemetry)
        
        # Need at least 10 frames to start detecting temporal patterns
        if len(self.history) < 10:
            return []

        anomalies = []
        current_time = time.time()

        # Run detection subroutines
        fall_detected = self._detect_falls()
        fight_detected = self._detect_violence()
        panic_detected = self._detect_panic()

        # Check cooldowns and trigger alerts
        if fall_detected and (current_time - self.cooldowns["fall"] > self.COOLDOWN_PERIOD):
            self.cooldowns["fall"] = current_time
            anomalies.append({
                "type": "fall",
                "severity": "high",
                "message": "Immediate Fall Detected: Individual collapsed in public area",
                "timestamp": current_time,
                "confidence": 0.88
            })

        if fight_detected and (current_time - self.cooldowns["fight"] > self.COOLDOWN_PERIOD):
            self.cooldowns["fight"] = current_time
            anomalies.append({
                "type": "fight",
                "severity": "critical",
                "message": "Physical Altercation Detected: Highly erratic high-speed skeletal interaction",
                "timestamp": current_time,
                "confidence": 0.92
            })

        if panic_detected and (current_time - self.cooldowns["panic"] > self.COOLDOWN_PERIOD):
            self.cooldowns["panic"] = current_time
            anomalies.append({
                "type": "panic",
                "severity": "critical",
                "message": "Crowd Anomaly Detected: Rapid crowd dispersal or stampede velocity",
                "timestamp": current_time,
                "confidence": 0.85
            })

        # Check track trespassing / intrusion
        intrusion_detected = self._detect_intrusion()
        if intrusion_detected and (current_time - self.cooldowns["intrusion"] > self.COOLDOWN_PERIOD):
            self.cooldowns["intrusion"] = current_time
            anomalies.append({
                "type": "intrusion",
                "severity": "critical",
                "message": "Critical Intrusion: Individual crossed safety yellow line towards tracks",
                "timestamp": current_time,
                "confidence": 0.95
            })

        return anomalies

    def _detect_falls(self):
        """Detects sudden vertical collapse of a skeleton."""
        latest_frame = self.history[-1]
        skeletons = latest_frame.get("skeletons", [])
        
        for sk in skeletons:
            sk_id = sk["id"]
            landmarks = sk["landmarks"]
            
            # Extract head (0), hip center (average of 23, 24) or shoulders
            head = next((lm for lm in landmarks if lm["id"] == 0), None)
            l_hip = next((lm for lm in landmarks if lm["id"] == 23), None)
            r_hip = next((lm for lm in landmarks if lm["id"] == 24), None)
            
            if not head or not l_hip or not r_hip:
                continue

            hip_y = (l_hip["y"] + r_hip["y"]) / 2.0
            
            # Find matching skeleton in previous frames to compute velocity
            prev_hip_y = None
            prev_time = None
            
            # Look back 10-15 frames (approx 0.5s) to detect a sudden drop
            lookback_idx = max(0, len(self.history) - 15)
            lookback_frame = self.history[lookback_idx]
            
            for prev_sk in lookback_frame.get("skeletons", []):
                if prev_sk["id"] == sk_id:
                    prev_l_hip = next((lm for lm in prev_sk["landmarks"] if lm["id"] == 23), None)
                    prev_r_hip = next((lm for lm in prev_sk["landmarks"] if lm["id"] == 24), None)
                    if prev_l_hip and prev_r_hip:
                        prev_hip_y = (prev_l_hip["y"] + prev_r_hip["y"]) / 2.0
                        prev_time = lookback_frame["timestamp"]
                        break
            
            if prev_hip_y is not None and prev_time is not None:
                dt = latest_frame["timestamp"] - prev_time
                if dt > 0:
                    velocity_y = (hip_y - prev_hip_y) / dt  # Positive means moving down
                    
                    # 1. Sudden downward velocity check
                    # 2. Horizontal orientation: check height vs width of joints
                    min_y = min(lm["y"] for lm in landmarks)
                    max_y = max(lm["y"] for lm in landmarks)
                    min_x = min(lm["x"] for lm in landmarks)
                    max_x = max(lm["x"] for lm in landmarks)
                    
                    height = max_y - min_y
                    width = max_x - min_x
                    
                    # If velocity is high, and the posture becomes wider than it is tall (horizontal), or hip is low.
                    if velocity_y > self.FALL_VELOCITY_THRESHOLD and height < 0.35:
                        return True
                    
                    # Or if they are simply horizontal on the floor
                    if height < 0.22 and width > 0.35 and hip_y > 0.7:
                        return True

        return False

    def _detect_violence(self):
        """Detects rapid, erratic hand flailing and closeness between two people."""
        latest_frame = self.history[-1]
        skeletons = latest_frame.get("skeletons", [])
        
        if len(skeletons) < 2:
            return False

        # Calculate pairwise distance between skeletons (using hips or shoulders)
        for i in range(len(skeletons)):
            for j in range(i + 1, len(skeletons)):
                sk1, sk2 = skeletons[i], skeletons[j]
                
                # Extract hip coordinates
                sk1_l_hip = next((lm for lm in sk1["landmarks"] if lm["id"] == 23), None)
                sk1_r_hip = next((lm for lm in sk1["landmarks"] if lm["id"] == 24), None)
                sk2_l_hip = next((lm for lm in sk2["landmarks"] if lm["id"] == 23), None)
                sk2_r_hip = next((lm for lm in sk2["landmarks"] if lm["id"] == 24), None)
                
                if not sk1_l_hip or not sk2_l_hip:
                    continue
                
                sk1_cx = (sk1_l_hip["x"] + sk1_r_hip["x"]) / 2.0
                sk1_cy = (sk1_l_hip["y"] + sk1_r_hip["y"]) / 2.0
                sk2_cx = (sk2_l_hip["x"] + sk2_r_hip["x"]) / 2.0
                sk2_cy = (sk2_l_hip["y"] + sk2_r_hip["y"]) / 2.0
                
                distance = np.sqrt((sk1_cx - sk2_cx)**2 + (sk1_cy - sk2_cy)**2)
                
                # Check proximity
                if distance < self.FIGHT_PROXIMITY_THRESHOLD:
                    # Skeletons are close. Now check kinematic joint speeds over the last 10 frames
                    sk1_joint_speeds = self._calculate_joint_speeds(sk1["id"], lookback=10)
                    sk2_joint_speeds = self._calculate_joint_speeds(sk2["id"], lookback=10)
                    
                    # If both have high speeds or one has extreme speed, it's a conflict
                    mean_speed = (np.mean(sk1_joint_speeds) + np.mean(sk2_joint_speeds)) / 2.0 if sk1_joint_speeds and sk2_joint_speeds else 0.0
                    
                    if mean_speed > self.FIGHT_VELOCITY_THRESHOLD:
                        return True
        return False

    def _calculate_joint_speeds(self, sk_id, lookback=10):
        """Calculates mean speed of active joints (hands/elbows) over the last N frames."""
        speeds = []
        if len(self.history) < lookback:
            return []

        # Target active wrist/elbow joints (MediaPipe: 13, 14, 15, 16)
        target_joint_ids = [13, 14, 15, 16]
        
        # Traverse frames backwards
        for i in range(len(self.history) - lookback, len(self.history) - 1):
            f_curr = self.history[i + 1]
            f_prev = self.history[i]
            dt = f_curr["timestamp"] - f_prev["timestamp"]
            
            if dt <= 0:
                continue

            sk_curr = next((s for s in f_curr.get("skeletons", []) if s["id"] == sk_id), None)
            sk_prev = next((s for s in f_prev.get("skeletons", []) if s["id"] == sk_id), None)
            
            if sk_curr and sk_prev:
                for j_id in target_joint_ids:
                    curr_j = next((lm for lm in sk_curr["landmarks"] if lm["id"] == j_id), None)
                    prev_j = next((lm for lm in sk_prev["landmarks"] if lm["id"] == j_id), None)
                    
                    if curr_j and prev_j:
                        dx = curr_j["x"] - prev_j["x"]
                        dy = curr_j["y"] - prev_j["y"]
                        speed = np.sqrt(dx**2 + dy**2) / dt
                        speeds.append(speed)
        return speeds

    def _detect_panic(self):
        """Detects sudden, massive increase in optical flow speed (fleeing)."""
        latest_frame = self.history[-1]
        
        # Crowd velocity check
        crowd_speed = latest_frame.get("crowd_speed", 0.0)
        crowd_density = latest_frame.get("crowd_density", 0.0)
        
        # If crowd speed goes way up, and there's a significant portion of the grid moving
        if crowd_speed > self.PANIC_CROWD_SPEED_THRESHOLD and crowd_density > 15.0:
            # Check optical flow divergence to confirm they are running outwards (panic dispersal)
            flow_vectors = latest_frame.get("flow_vectors", [])
            if len(flow_vectors) > 20:
                # Calculate if vectors point in conflicting or outwards radial directions
                dxs = [v["dx"] for v in flow_vectors]
                dys = [v["dy"] for v in flow_vectors]
                
                # Check standard deviation of angles (chaotic movements)
                angles = [np.arctan2(dy, dx) for dx, dy in zip(dxs, dys)]
                angle_std = np.std(angles)
                
                # Highly scattered angles + high velocity indicates dispersal/panic
                if angle_std > 1.2:
                    return True
        return False

    def _detect_intrusion(self):
        """Detects if any skeleton crosses the safety boundary line on Platform 2 (Camera 1)."""
        latest_frame = self.history[-1]
        
        # Only check on Camera 1 (Subway Platform)
        if latest_frame.get("camera_id") != 1:
            return False
            
        skeletons = latest_frame.get("skeletons", [])
        for sk in skeletons:
            landmarks = sk["landmarks"]
            # Check ankles (MediaPipe joint IDs: 27, 28)
            ankle_l = next((lm for lm in landmarks if lm["id"] == 27), None)
            ankle_r = next((lm for lm in landmarks if lm["id"] == 28), None)
            
            # Anomaly triggered if feet coordinates cross below (greater than Y) the threshold
            if ankle_l and ankle_l["y"] > self.INTRUSION_Y_THRESHOLD:
                return True
            if ankle_r and ankle_r["y"] > self.INTRUSION_Y_THRESHOLD:
                return True
        return False
