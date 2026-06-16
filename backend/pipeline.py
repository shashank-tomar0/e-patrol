import cv2
import numpy as np
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VideoPipeline")

# Try to import MediaPipe, fall back to mock mode if not installed/available
HAS_MEDIAPIPE = False
try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
    logger.info("MediaPipe successfully loaded.")
except ImportError:
    logger.warning("MediaPipe not found or failed to load. Running in Simulation/Fallback Mode.")

class VideoPipeline:
    def __init__(self, camera_id=0, source=0):
        self.camera_id = camera_id
        self.source = source
        self.cap = None
        self.running = False
        
        # Optical Flow parameters
        self.prev_gray = None
        self.flow_grid_size = 16  # Sample optical flow on a 16x16 grid for visualization
        
        # MediaPipe Pose setup
        self.pose = None
        if HAS_MEDIAPIPE:
            try:
                import mediapipe.python.solutions.pose as mp_pose
                self.mp_pose = mp_pose
                self.pose = self.mp_pose.Pose(
                    static_image_mode=False,
                    model_complexity=1,
                    smooth_landmarks=True,
                    enable_segmentation=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5
                )
            except Exception as e:
                logger.error(f"Error initializing MediaPipe Pose: {e}")
                self.pose = None
        
        # Telemetry State
        self.latest_skeletons = []
        self.latest_flow_vectors = []
        self.latest_crowd_density = 0.0
        self.latest_crowd_speed = 0.0
        self.frame_width = 640
        self.frame_height = 480
        
        # Simulated generator for mock mode
        self.simulated_state = "normal"  # normal, fight, fall, panic
        self.simulation_ticks = 0

    def start(self):
        """Starts the video capture stream if using a real video source."""
        if isinstance(self.source, str) and (self.source.startswith("http") or self.source.endswith(".mp4")):
            self.cap = cv2.VideoCapture(self.source)
        elif self.source == "mock":
            self.cap = None
            logger.info("Running pipeline with Mock Simulation Source")
        else:
            self.cap = cv2.VideoCapture(int(self.source) if str(self.source).isdigit() else self.source)
            
        if self.cap and self.cap.isOpened():
            self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"Video stream opened. Resolution: {self.frame_width}x{self.frame_height}")
        self.running = True

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        if self.pose:
            self.pose.close()

    def set_simulation_state(self, state):
        """Allows external controls (like the dashboard) to force an anomaly state for demo purposes."""
        if state in ["normal", "fight", "fall", "panic", "intrusion", "loitering"]:
            self.simulated_state = state
            logger.info(f"Camera {self.camera_id} simulation state set to: {state}")

    def process_frame_data(self, frame=None):
        """Processes a single frame: extracts pose skeletons and computes optical flow."""
        if frame is None:
            # If no frame is passed and cap exists, read from stream
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    # Loop video if it's a file
                    if isinstance(self.source, str) and self.source.endswith(".mp4"):
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self.cap.read()
                    if not ret:
                        return None
            else:
                # Mock generation of frame data
                return self._generate_simulated_telemetry()

        # Resize for faster processing
        resized_frame = cv2.resize(frame, (640, 480))
        h, w, _ = resized_frame.shape
        self.frame_width, self.frame_height = w, h

        # 1. Optical Flow Calculation
        gray = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2GRAY)
        crowd_density = 0.0
        crowd_speed = 0.0
        flow_vectors = []

        if self.prev_gray is not None:
            # Calculate dense optical flow (Farneback)
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None, 
                pyr_scale=0.5, levels=3, winsize=15, 
                iterations=3, poly_n=5, poly_sigma=1.2, flags=0
            )
            
            # Subsample flow grid for web visualization to prevent choking WebSockets
            step = self.flow_grid_size
            magnitudes = []
            for y in range(0, h, step):
                for x in range(0, w, step):
                    fx, fy = flow[y, x]
                    mag = float(np.sqrt(fx**2 + fy**2))
                    if mag > 1.5:  # filter background noise/camera shake
                        magnitudes.append(mag)
                        flow_vectors.append({
                            "x": int(x), "y": int(y),
                            "dx": float(fx), "dy": float(fy),
                            "mag": mag
                        })
            
            # Density estimate based on moving pixels
            moving_pixels = len(magnitudes)
            total_grid_points = (h // step) * (w // step)
            crowd_density = (moving_pixels / total_grid_points) * 100.0
            crowd_speed = float(np.mean(magnitudes)) if magnitudes else 0.0

        self.prev_gray = gray
        self.latest_flow_vectors = flow_vectors
        self.latest_crowd_density = crowd_density
        self.latest_crowd_speed = crowd_speed

        # 2. Skeleton Extraction
        skeletons = []
        if self.pose and HAS_MEDIAPIPE:
            # MediaPipe requires RGB
            rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(rgb_frame)
            
            if results.pose_landmarks:
                landmarks = []
                for idx, lm in enumerate(results.pose_landmarks.landmark):
                    # We normalize coordinates [0, 1] relative to w, h
                    landmarks.append({
                        "id": idx,
                        "x": float(lm.x),
                        "y": float(lm.y),
                        "z": float(lm.z),
                        "visibility": float(lm.visibility)
                    })
                skeletons.append({
                    "id": 1,  # Single pose tracker for standard MediaPipe
                    "landmarks": landmarks
                })
        else:
            # If MediaPipe is disabled/missing, generate simulated skeleton overlay
            skeletons = self._generate_fallback_skeletons()

        self.latest_skeletons = skeletons
        
        return {
            "camera_id": self.camera_id,
            "timestamp": time.time(),
            "skeletons": skeletons,
            "flow_vectors": flow_vectors[:150],  # cap at 150 vectors to minimize bandwidth
            "crowd_density": crowd_density,
            "crowd_speed": crowd_speed,
            "simulated": False
        }

    def _generate_fallback_skeletons(self):
        """Generates mock skeletons when MediaPipe is unavailable but OpenCV video is playing."""
        # Simple procedural skeleton that oscillates based on time to show active visual tracking
        t = time.time()
        base_x = 0.5 + 0.1 * np.sin(t)
        base_y = 0.5 + 0.05 * np.cos(t * 1.5)
        
        # Simple human-like landmark structure
        landmarks = []
        # Head (0)
        landmarks.append({"id": 0, "x": base_x, "y": base_y - 0.25, "z": 0.0, "visibility": 0.99})
        # Shoulders (11, 12)
        landmarks.append({"id": 11, "x": base_x - 0.08, "y": base_y - 0.18, "z": 0.0, "visibility": 0.99})
        landmarks.append({"id": 12, "x": base_x + 0.08, "y": base_y - 0.18, "z": 0.0, "visibility": 0.99})
        # Elbows (13, 14)
        landmarks.append({"id": 13, "x": base_x - 0.12, "y": base_y - 0.05 + 0.05*np.sin(t*3), "z": 0.0, "visibility": 0.95})
        landmarks.append({"id": 14, "x": base_x + 0.12, "y": base_y - 0.05 + 0.05*np.cos(t*3), "z": 0.0, "visibility": 0.95})
        # Wrists (15, 16)
        landmarks.append({"id": 15, "x": base_x - 0.14, "y": base_y + 0.05 + 0.08*np.sin(t*3), "z": 0.0, "visibility": 0.95})
        landmarks.append({"id": 16, "x": base_x + 0.14, "y": base_y + 0.05 + 0.08*np.cos(t*3), "z": 0.0, "visibility": 0.95})
        # Hips (23, 24)
        landmarks.append({"id": 23, "x": base_x - 0.06, "y": base_y + 0.1, "z": 0.0, "visibility": 0.99})
        landmarks.append({"id": 24, "x": base_x + 0.06, "y": base_y + 0.1, "z": 0.0, "visibility": 0.99})
        # Knees (25, 26)
        landmarks.append({"id": 25, "x": base_x - 0.07, "y": base_y + 0.25, "z": 0.0, "visibility": 0.9})
        landmarks.append({"id": 26, "x": base_x + 0.07, "y": base_y + 0.25, "z": 0.0, "visibility": 0.9})
        # Ankles (27, 28)
        landmarks.append({"id": 27, "x": base_x - 0.07, "y": base_y + 0.4, "z": 0.0, "visibility": 0.9})
        landmarks.append({"id": 28, "x": base_x + 0.07, "y": base_y + 0.4, "z": 0.0, "visibility": 0.9})
        
        return [{"id": 1, "landmarks": landmarks}]

    def _generate_simulated_telemetry(self):
        """Generates completely simulated crowd & skeleton telemetry for zero-video deployment."""
        self.simulation_ticks += 1
        t = time.time()
        
        # Base settings
        crowd_density = 12.0 + 4.0 * np.sin(t * 0.1)
        crowd_speed = 0.8 + 0.3 * np.cos(t * 0.2)
        skeletons = []
        flow_vectors = []

        # Create normal background flow grid (moving left-to-right)
        for y in range(40, 440, 40):
            for x in range(40, 600, 40):
                dx = 2.0 + 0.5 * np.sin(t + x)
                dy = 0.5 * np.cos(t + y)
                flow_vectors.append({
                    "x": x, "y": y,
                    "dx": dx, "dy": dy,
                    "mag": float(np.sqrt(dx**2 + dy**2))
                })

        if self.simulated_state == "normal":
            # Generate 2 normal walking skeletons moving past each other
            s1_x = (0.2 + (t * 0.05) % 0.6)
            s2_x = (0.8 - (t * 0.04) % 0.6)
            
            # Skeleton 1 (Normal Walker)
            skeletons.append(self._create_procedural_skeleton(id=1, cx=s1_x, cy=0.5, posture="walk", seed=1))
            # Skeleton 2 (Normal Walker)
            skeletons.append(self._create_procedural_skeleton(id=2, cx=s2_x, cy=0.55, posture="walk", seed=2))

        elif self.simulated_state == "fight":
            # Two skeletons close together, waving hands rapidly
            crowd_density = 25.0
            crowd_speed = 2.5
            
            # Alter flow vectors around the fight center (320, 240) to show local chaotic swirling
            flow_vectors = []
            for y in range(40, 440, 40):
                for x in range(40, 600, 40):
                    dist = np.sqrt((x - 320)**2 + (y - 240)**2)
                    if dist < 120:
                        dx = 15.0 * np.sin(t * 8 + y)
                        dy = 15.0 * np.cos(t * 8 + x)
                    else:
                        dx = 2.0 + 0.5 * np.sin(t + x)
                        dy = 0.5 * np.cos(t + y)
                    flow_vectors.append({
                        "x": x, "y": y,
                        "dx": dx, "dy": dy,
                        "mag": float(np.sqrt(dx**2 + dy**2))
                    })
            
            skeletons.append(self._create_procedural_skeleton(id=1, cx=0.46 + 0.02*np.sin(t*15), cy=0.5, posture="fight", seed=1))
            skeletons.append(self._create_procedural_skeleton(id=2, cx=0.54 + 0.02*np.cos(t*15), cy=0.5, posture="fight", seed=2))

        elif self.simulated_state == "fall":
            # One skeleton falls rapidly and stays horizontal
            elapsed = self.simulation_ticks % 100
            
            if elapsed < 15:
                # Falling transition
                cy = 0.5 + (elapsed / 15.0) * 0.25
                posture = "walk"
            else:
                # Lying down on ground
                cy = 0.78
                posture = "fallen"
                
            skeletons.append(self._create_procedural_skeleton(id=3, cx=0.5, cy=cy, posture=posture, seed=3))

        elif self.simulated_state == "panic":
            # Crowd optical flow shoots outwards rapidly, skeletons run to boundaries
            crowd_density = 40.0
            crowd_speed = 6.8
            flow_vectors = []
            
            # Radial explosion vectors pointing away from center (320, 240)
            for y in range(40, 440, 45):
                for x in range(40, 600, 45):
                    rx, ry = x - 320, y - 240
                    dist = np.sqrt(rx**2 + ry**2) + 0.01
                    dx = (rx / dist) * 12.0
                    dy = (ry / dist) * 12.0
                    flow_vectors.append({
                        "x": x, "y": y,
                        "dx": dx, "dy": dy,
                        "mag": float(np.sqrt(dx**2 + dy**2))
                    })
            
            # Running skeletons dispersing outward
            s1_x = 0.5 - 0.04 * (self.simulation_ticks % 20)
            s2_x = 0.5 + 0.04 * (self.simulation_ticks % 20)
            skeletons.append(self._create_procedural_skeleton(id=4, cx=s1_x, cy=0.55, posture="run", seed=4))
            skeletons.append(self._create_procedural_skeleton(id=5, cx=s2_x, cy=0.5, posture="run", seed=5))

        elif self.simulated_state == "intrusion":
            # Skeleton walking slowly towards the track line, crossing it
            elapsed = self.simulation_ticks % 100
            
            # Walks down from cy=0.36 to cy=0.52 (feet reach cy+0.3 = 0.82)
            cy = 0.36 + min(16, elapsed * 0.2) * 0.01
            posture = "walk" if elapsed < 80 else "stand"
            
            skeletons.append(self._create_procedural_skeleton(id=6, cx=0.5, cy=cy, posture=posture, seed=6))

        elif self.simulated_state == "loitering":
            # Walk left into the restricted corridor zone (x: 0.18, y: 0.55) and stand still
            elapsed = self.simulation_ticks % 120
            
            if elapsed < 30:
                cx = 0.5 - (elapsed / 30.0) * 0.32
                cy = 0.5 + (elapsed / 30.0) * 0.05
                posture = "walk"
            else:
                cx = 0.18
                cy = 0.55
                posture = "stand"
                
            skeletons.append(self._create_procedural_skeleton(id=7, cx=cx, cy=cy, posture=posture, seed=7))

        self.latest_skeletons = skeletons
        self.latest_flow_vectors = flow_vectors
        self.latest_crowd_density = crowd_density
        self.latest_crowd_speed = crowd_speed

        return {
            "camera_id": self.camera_id,
            "timestamp": time.time(),
            "skeletons": skeletons,
            "flow_vectors": flow_vectors,
            "crowd_density": crowd_density,
            "crowd_speed": crowd_speed,
            "simulated": True
        }

    def _create_procedural_skeleton(self, id, cx, cy, posture="walk", seed=0):
        """Generates joints coordinates depending on the posture style."""
        t = time.time() + seed * 10
        landmarks = []

        # Adjust posture settings
        head_y_offset = -0.25
        hip_y_offset = 0.1
        body_width = 0.07

        if posture == "fallen":
            # Completely horizontal skeleton lying on ground
            # Swap x and y offsets to rotate person 90 degrees
            landmarks.append({"id": 0, "x": cx - 0.25, "y": cy, "z": 0.0, "visibility": 0.99}) # Head
            landmarks.append({"id": 11, "x": cx - 0.18, "y": cy - 0.05, "z": 0.0, "visibility": 0.99}) # L shoulder
            landmarks.append({"id": 12, "x": cx - 0.18, "y": cy + 0.05, "z": 0.0, "visibility": 0.99}) # R shoulder
            landmarks.append({"id": 13, "x": cx - 0.1, "y": cy - 0.08, "z": 0.0, "visibility": 0.9}) # L elbow
            landmarks.append({"id": 14, "x": cx - 0.1, "y": cy + 0.08, "z": 0.0, "visibility": 0.9}) # R elbow
            landmarks.append({"id": 15, "x": cx - 0.05, "y": cy - 0.09, "z": 0.0, "visibility": 0.9}) # L wrist
            landmarks.append({"id": 16, "x": cx - 0.05, "y": cy + 0.09, "z": 0.0, "visibility": 0.9}) # R wrist
            landmarks.append({"id": 23, "x": cx + 0.05, "y": cy - 0.03, "z": 0.0, "visibility": 0.99}) # L hip
            landmarks.append({"id": 24, "x": cx + 0.05, "y": cy + 0.03, "z": 0.0, "visibility": 0.99}) # R hip
            landmarks.append({"id": 25, "x": cx + 0.18, "y": cy - 0.04, "z": 0.0, "visibility": 0.85}) # L knee
            landmarks.append({"id": 26, "x": cx + 0.18, "y": cy + 0.04, "z": 0.0, "visibility": 0.85}) # R knee
            landmarks.append({"id": 27, "x": cx + 0.3, "y": cy - 0.04, "z": 0.0, "visibility": 0.85}) # L ankle
            landmarks.append({"id": 28, "x": cx + 0.3, "y": cy + 0.04, "z": 0.0, "visibility": 0.85}) # R ankle
            return {"id": id, "landmarks": landmarks}

        # Dynamic limb animations
        l_arm_swing = r_arm_swing = l_leg_swing = r_leg_swing = 0.0
        l_shoulder_y = r_shoulder_y = cy - 0.18
        l_hip_y = r_hip_y = cy + 0.1

        if posture == "walk":
            l_arm_swing = 0.12 * np.sin(t * 4.0)
            r_arm_swing = -0.12 * np.sin(t * 4.0)
            l_leg_swing = 0.1 * np.cos(t * 4.0)
            r_leg_swing = -0.1 * np.cos(t * 4.0)
        elif posture == "run":
            l_arm_swing = 0.2 * np.sin(t * 8.0)
            r_arm_swing = -0.2 * np.sin(t * 8.0)
            l_leg_swing = 0.18 * np.cos(t * 8.0)
            r_leg_swing = -0.18 * np.cos(t * 8.0)
            head_y_offset += 0.02 * np.sin(t * 16.0) # Bobbing head
        elif posture == "fight":
            # Hands up, moving erratically and fast
            l_arm_swing = 0.15 * np.sin(t * 20.0) - 0.15
            r_arm_swing = 0.15 * np.cos(t * 18.0) - 0.15
            l_leg_swing = 0.03 * np.cos(t * 6.0)
            r_leg_swing = -0.03 * np.cos(t * 6.0)
            head_y_offset += 0.03 * np.sin(t * 12.0)

        # Head (0)
        landmarks.append({"id": 0, "x": cx, "y": cy + head_y_offset, "z": 0.0, "visibility": 0.99})
        # Shoulders (11, 12)
        landmarks.append({"id": 11, "x": cx - body_width, "y": l_shoulder_y, "z": -0.05, "visibility": 0.99})
        landmarks.append({"id": 12, "x": cx + body_width, "y": r_shoulder_y, "z": 0.05, "visibility": 0.99})
        
        # Elbows (13, 14)
        landmarks.append({"id": 13, "x": cx - body_width - 0.03, "y": l_shoulder_y + 0.1 + l_arm_swing*0.5, "z": -0.08, "visibility": 0.95})
        landmarks.append({"id": 14, "x": cx + body_width + 0.03, "y": r_shoulder_y + 0.1 + r_arm_swing*0.5, "z": 0.08, "visibility": 0.95})
        
        # Wrists (15, 16)
        if posture == "fight":
            # Wrists higher than shoulders
            landmarks.append({"id": 15, "x": cx - 0.04 + l_arm_swing, "y": cy - 0.22 + 0.05*np.sin(t*25), "z": -0.1, "visibility": 0.95})
            landmarks.append({"id": 16, "x": cx + 0.04 + r_arm_swing, "y": cy - 0.23 + 0.05*np.cos(t*25), "z": 0.1, "visibility": 0.95})
        else:
            landmarks.append({"id": 15, "x": cx - body_width - 0.04 + l_arm_swing, "y": l_shoulder_y + 0.22, "z": -0.1, "visibility": 0.95})
            landmarks.append({"id": 16, "x": cx + body_width + 0.04 + r_arm_swing, "y": r_shoulder_y + 0.22, "z": 0.1, "visibility": 0.95})

        # Hips (23, 24)
        landmarks.append({"id": 23, "x": cx - body_width*0.8, "y": l_hip_y, "z": -0.03, "visibility": 0.99})
        landmarks.append({"id": 24, "x": cx + body_width*0.8, "y": r_hip_y, "z": 0.03, "visibility": 0.99})
        
        # Knees (25, 26)
        landmarks.append({"id": 25, "x": cx - body_width*0.8 + l_leg_swing*0.5, "y": l_hip_y + 0.15, "z": -0.05, "visibility": 0.9})
        landmarks.append({"id": 26, "x": cx + body_width*0.8 + r_leg_swing*0.5, "y": r_hip_y + 0.15, "z": 0.05, "visibility": 0.9})
        
        # Ankles (27, 28)
        landmarks.append({"id": 27, "x": cx - body_width*0.8 + l_leg_swing, "y": l_hip_y + 0.3, "z": -0.08, "visibility": 0.9})
        landmarks.append({"id": 28, "x": cx + body_width*0.8 + r_leg_swing, "y": r_hip_y + 0.3, "z": 0.08, "visibility": 0.9})

        return {"id": id, "landmarks": landmarks}
