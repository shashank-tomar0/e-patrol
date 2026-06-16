import time
import uuid
import re
import numpy as np

# Simple keyword expansion mapping to make local search feel highly semantic
SEMANTIC_SYNONYMS = {
    "fight": ["altercation", "combat", "clash", "violence", "punch", "assault", "hit", "striking", "fighting"],
    "fall": ["collapse", "trip", "slip", "down", "lying", "unconscious", "medical", "faint", "fainted", "collapsed"],
    "panic": ["run", "running", "stampede", "dispersal", "fleeing", "scared", "evacuation", "rush", "crowd"],
    "subway": ["platform", "tracks", "train", "station", "rail"],
    "escalator": ["stairs", "steps", "elevator"],
    "lobby": ["hall", "ticketing", "concourse", "entrance"]
}

class EventDatabase:
    def __init__(self):
        # In-memory storage for events
        self.events = []
        
        # Populate with some high-fidelity mock historical data so the semantic search works immediately on launch!
        self._seed_database()

    def add_event(self, event_type, location, severity, dossier, telemetry_snapshot):
        """Saves a new anomaly event to the database."""
        event_record = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": time.time(),
            "type": event_type,
            "location": location,
            "severity": severity,
            "summary": dossier.get("summary", ""),
            "visual_analysis": dossier.get("visual_analysis", ""),
            "threat_level": dossier.get("threat_level", severity.upper()),
            # Store subset of coordinates to allow replay of skeletons
            "skeletons": telemetry_snapshot.get("skeletons", []),
            "density": telemetry_snapshot.get("crowd_density", 0.0),
            "speed": telemetry_snapshot.get("crowd_speed", 0.0),
        }
        self.events.insert(0, event_record) # Newest first
        return event_record

    def get_all_events(self):
        return self.events

    def search_events(self, query):
        """Performs a keyword-expanded search on summaries and locations, simulating vector search."""
        if not query:
            return self.events

        # Clean and tokenize the query
        query_words = re.findall(r'\w+', query.lower())
        
        # Expand query words using synonyms
        expanded_search_terms = set(query_words)
        for word in query_words:
            for key, syns in SEMANTIC_SYNONYMS.items():
                if word == key or word in syns:
                    expanded_search_terms.add(key)
                    expanded_search_terms.update(syns)

        ranked_results = []
        for event in self.events:
            score = 0.0
            
            # Text to search within
            event_text = f"{event['type']} {event['location']} {event['summary']} {event['visual_analysis']}".lower()
            
            # Scoring logic
            for term in expanded_search_terms:
                # Direct match in text
                occurrences = event_text.count(term)
                if occurrences > 0:
                    score += occurrences * 1.0
                    
                # Extra weight for exact matches in the event type or location
                if term == event["type"].lower():
                    score += 5.0
                if term in event["location"].lower():
                    score += 3.0
            
            if score > 0:
                ranked_results.append((event, score))

        # Sort by score descending
        ranked_results.sort(key=lambda x: x[1], reverse=True)
        
        # Return only the event objects with matching score metadata
        final_results = []
        for event, score in ranked_results:
            event_copy = event.copy()
            event_copy["similarity_score"] = float(min(1.0, score / 15.0)) # Normalize score
            final_results.append(event_copy)
            
        return final_results

    def _seed_database(self):
        """Pre-populates the database with realistic historic anomalies for demonstration."""
        now = time.time()
        
        mock_incidents = [
            {
                "type": "fight",
                "location": "Subway Platform 2",
                "severity": "critical",
                "summary": "High-velocity skeleton conflict. Two subjects in physical contact, throwing quick punches near safety yellow line.",
                "visual_analysis": "Close proximity skeleton collision detected. Wrists moving at 3.2m/s. Surrounding skeletons dispersing rapidly.",
                "threat_level": "CRITICAL",
                "density": 18.5,
                "speed": 2.8,
                "time_offset": -120  # 2 mins ago
            },
            {
                "type": "fall",
                "location": "North Entrance Escalator",
                "severity": "high",
                "summary": "Individual collapsed near escalator base. Skeleton height shrunk by 60% rapidly, remaining horizontal for over 30s.",
                "visual_analysis": "Hip landmark dropped from 0.52 to 0.79 coordinate space within 12 frames. Target static on ground.",
                "threat_level": "HIGH",
                "density": 8.0,
                "speed": 0.5,
                "time_offset": -600  # 10 mins ago
            },
            {
                "type": "panic",
                "location": "Main Ticketing Lobby",
                "severity": "high",
                "summary": "Sudden crowd surge and panic dispersal. Dense grid vectors show outward expansion away from ticketing booths.",
                "visual_analysis": "Average flow vector speed spiked to 5.4m/s. Multiple skeletons showing running gait patterns.",
                "threat_level": "HIGH",
                "density": 34.0,
                "speed": 5.8,
                "time_offset": -1800  # 30 mins ago
            },
            {
                "type": "loitering",
                "location": "Restricted Access Hallway",
                "severity": "medium",
                "summary": "Single skeleton observed remaining stationary inside restricted zone for 4.5 minutes.",
                "visual_analysis": "Target skeleton tracked in region coordinates [0.1, 0.4] to [0.2, 0.6] with near-zero displacement.",
                "threat_level": "MEDIUM",
                "density": 1.2,
                "speed": 0.1,
                "time_offset": -3600  # 1 hour ago
            }
        ]

        for inc in mock_incidents:
            # Generate a simple mock skeleton
            cx = 0.5
            cy = 0.5 if inc["type"] != "fall" else 0.78
            posture = "walk" if inc["type"] != "fall" else "fallen"
            if inc["type"] == "fight":
                posture = "fight"
            
            # Procedural mock landmarks
            landmarks = []
            for j in [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]:
                landmarks.append({"id": j, "x": cx, "y": cy, "z": 0.0, "visibility": 0.95})
            
            event = {
                "id": str(uuid.uuid4())[:8],
                "timestamp": now + inc["time_offset"],
                "type": inc["type"],
                "location": inc["location"],
                "severity": inc["severity"],
                "summary": inc["summary"],
                "visual_analysis": inc["visual_analysis"],
                "threat_level": inc["threat_level"],
                "skeletons": [{"id": 1, "landmarks": landmarks}],
                "density": inc["density"],
                "speed": inc["speed"]
            }
            self.events.append(event)
