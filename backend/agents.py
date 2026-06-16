import os
import httpx
import logging
import json

logger = logging.getLogger("CognitiveAgents")

class SceneVerifierAgent:
    """Agent 1: Evaluates safety rules depending on location context."""
    def __init__(self):
        # Safety rules based on location contexts
        self.location_rules = {
            "subway_platform": {
                "fall": {"severity": "critical", "action": "Trigger Platform Emergency Stop & dispatcher alert"},
                "fight": {"severity": "critical", "action": "Dispatch station police & activate CCTV focus"},
                "panic": {"severity": "critical", "action": "Open emergency exit gates & initiate audio guidance"},
                "intrusion": {"severity": "critical", "action": "Trigger Track intrusion voice warning & warn dispatcher"},
                "loitering": {"severity": "low", "action": "Monitor skeleton coordinate bounds"}
            },
            "subway_tracks": {
                "fall": {"severity": "critical", "action": "IMMEDIATE POWER SHUTDOWN of rail lines & dispatcher override"},
                "fight": {"severity": "critical", "action": "IMMEDIATE POWER SHUTDOWN & Police Dispatch"},
                "panic": {"severity": "critical", "action": "Alert platform staff & track cameras"},
                "intrusion": {"severity": "critical", "action": "IMMEDIATE POWER SHUTDOWN of rail lines & dispatcher override"},
                "loitering": {"severity": "high", "action": "Sound trackside intrusion alarm & broadcast voice warning"}
            },
            "escalator": {
                "fall": {"severity": "high", "action": "Trigger Escalator Stop warning & alert concourse guard"},
                "fight": {"severity": "high", "action": "Alert concourse security staff"},
                "panic": {"severity": "critical", "action": "Stop escalator immediately to prevent pileup"},
                "loitering": {"severity": "low", "action": "Log baseline"}
            },
            "ticketing_hall": {
                "fall": {"severity": "medium", "action": "Inform customer assistance desk"},
                "fight": {"severity": "high", "action": "Alert terminal security officer"},
                "panic": {"severity": "high", "action": "Initiate evacuation protocols & alert supervisors"},
                "loitering": {"severity": "low", "action": "Log baseline"}
            }
        }

    def verify_event(self, event_type, location, confidence, telemetry=None):
        """Checks the detected anomaly against the scene guidelines."""
        # Normalize location key
        loc_key = location.lower().replace(" ", "_")
        
        # Default safety profile if location is not registered
        ruleset = self.location_rules.get(loc_key, self.location_rules["ticketing_hall"])
        rule = ruleset.get(event_type, {"severity": "medium", "action": "Monitor scene telemetry"})
        
        # Determine severity and construct evaluation
        reasoning = f"Evaluated incident [{event_type}] at [{location}]. "
        if rule["severity"] == "critical":
            reasoning += f"CRITICAL HAZARD: Action required: {rule['action']}."
        else:
            reasoning += f"Risk level assessed as {rule['severity'].upper()}. Standard response protocol: {rule['action']}."

        return {
            "verified": True,
            "severity": rule["severity"],
            "response_protocol": rule["action"],
            "reasoning_trail": reasoning
        }

class IncidentSummarizerAgent:
    """Agent 2: Generates natural language incident dossiers."""
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            logger.info("Gemini API key detected. Summarizer will use AI-Cloud mode.")
        else:
            logger.warning("No Gemini API key found. Summarizer will use Local Mode.")

    async def generate_dossier(self, event_type, location, verifier_data, telemetry):
        """Asynchronously creates a detailed dossier. Uses Gemini API if key is present, else rule-based local generator."""
        timestamp = verifier_data.get("timestamp", time.time())
        crowd_density = telemetry.get("crowd_density", 0.0)
        crowd_speed = telemetry.get("crowd_speed", 0.0)
        skeleton_count = len(telemetry.get("skeletons", []))
        
        prompt = (
            f"You are a cognitive multi-agent security analyst. Generate an Incident Dossier.\n"
            f"Incident: {event_type.upper()}\n"
            f"Location: {location}\n"
            f"Skeletons Present: {skeleton_count}\n"
            f"Crowd Density: {crowd_density:.1f}%\n"
            f"Crowd Speed: {crowd_speed:.2f} m/s\n"
            f"Response Action: {verifier_data['response_protocol']}\n"
            f"Verifier Reasoning: {verifier_data['reasoning_trail']}\n"
            f"Generate a professional, concise security incident report in JSON format with fields: "
            f"'summary', 'visual_evidence_analysis', 'threat_level'."
        )

        if self.api_key:
            try:
                # Call Gemini API via httpx
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                    if response.status_code == 200:
                        data = response.json()
                        text_response = data['candidates'][0]['content']['parts'][0]['text']
                        result = json.loads(text_response)
                        return {
                            "summary": result.get("summary", "Incident summary unavailable."),
                            "visual_analysis": result.get("visual_evidence_analysis", "No detailed visual analysis available."),
                            "threat_level": result.get("threat_level", verifier_data["severity"].upper()),
                            "llm_generated": True
                        }
            except Exception as e:
                logger.error(f"Error calling Gemini API: {e}. Falling back to Local Mode.")

        # Local Mode: Fallback templates
        return self._generate_local_dossier(event_type, location, verifier_data, telemetry)

    def _generate_local_dossier(self, event_type, location, verifier_data, telemetry):
        """Generates realistic structured summary reports without calling external APIs."""
        crowd_density = telemetry.get("crowd_density", 0.0)
        crowd_speed = telemetry.get("crowd_speed", 0.0)
        skeleton_count = len(telemetry.get("skeletons", []))
        
        summary = ""
        visual_analysis = ""
        
        if event_type == "fall":
            summary = (
                f"A fall/collapse incident was verified at {location}. A tracked skeleton "
                f"showed rapid vertical descent, terminating in a horizontal posture. "
                f"Crowd speed is at {crowd_speed:.2f} m/s, indicating no immediate crowd panic."
            )
            visual_analysis = (
                f"Skeletal analysis shows a single target coordinate system flattening at base height. "
                f"No close-proximity skeletons are colliding, suggesting a medical event or trip-and-fall."
            )
        elif event_type == "fight":
            summary = (
                f"A physical altercation was verified at {location} involving {skeleton_count} active skeletons. "
                f"Kinematics show high-speed erratic flailing of upper limbs (wrists, elbows). "
                f"Crowd density is elevated at {crowd_density:.1f}%."
            )
            visual_analysis = (
                f"Spatiotemporal tracking shows two skeletons colliding within the proximity envelope (<0.25m). "
                f"Active joint velocities exceeded the flailing threshold. Surrounding crowd shows signs of evasion."
            )
        elif event_type == "panic":
            summary = (
                f"Crowd panic / dispersal registered at {location}. Average optical flow velocity "
                f"spiked to {crowd_speed:.2f} m/s, which is {crowd_speed/1.2:.1f}x the baseline crowd speed."
            )
            visual_analysis = (
                f"Optical flow dense vector fields show a radial dispersal pattern outward from the scene center. "
                f"Skeletons exhibit locomotion kinematics corresponding to running (large stride animations)."
            )
        elif event_type == "intrusion":
            summary = (
                f"Safety line intrusion verified at {location}. A tracked skeleton "
                f"crossed the yellow platform safety threshold, entering the trackside zone."
            )
            visual_analysis = (
                f"Skeletal tracking shows ankle coordinates extending past y-coordinate 0.76. "
                f"Immediate power shutdown override issued to hold incoming trains."
            )
        else:
            summary = f"Routine alert: anomaly detected at {location}."
            visual_analysis = "Standard camera telemetry logged."

        return {
            "summary": summary,
            "visual_analysis": visual_analysis,
            "threat_level": verifier_data["severity"].upper(),
            "llm_generated": False
        }
import time

class AlertDispatcher:
    """Dispatches real-time webhooks (Discord / Slack) for mobile patrol notifications."""
    def __init__(self, default_webhook_url=None):
        self.default_webhook_url = default_webhook_url or os.getenv("DISPATCH_WEBHOOK_URL")

    async def dispatch_alert(self, event_record, webhook_url=None):
        target_url = webhook_url or self.default_webhook_url
        if not target_url:
            logger.info(f"Console Patrol Log: [{event_record['type'].upper()}] - {event_record['summary']}")
            return False

        payload = {}
        # Discord Embed
        if "discord.com" in target_url:
            payload = {
                "username": "E-Patrol Dispatch Bot",
                "avatar_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=100",
                "embeds": [{
                    "title": f"🚨 EMERGENCY PATROL DISPATCH: {event_record['type'].upper()}",
                    "description": event_record['summary'],
                    "color": 16724582 if event_record['severity'] == 'critical' else 16751155,
                    "fields": [
                        {"name": "📍 Location Beat", "value": event_record['location'], "inline": True},
                        {"name": "⚠️ Threat Severity", "value": event_record['threat_level'], "inline": True},
                        {"name": "🔍 Evidentiary Analysis", "value": event_record.get('visual_analysis', 'Standard protocols apply.'), "inline": False}
                    ],
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(event_record['timestamp']))
                }]
            }
        else:
            # Slack Format
            payload = {
                "text": f"🚨 *E-PATROL ALERT: {event_record['type'].upper()}* \n*Location*: {event_record['location']} \n*Severity*: {event_record['threat_level']} \n*AI Summary*: {event_record['summary']}"
            }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(target_url, json=payload, timeout=5.0)
                if response.status_code in [200, 204]:
                    logger.info("Alert webhook successfully dispatched to external endpoint.")
                    return True
                else:
                    logger.error(f"Alert webhook failed with status {response.status_code}")
        except Exception as e:
            logger.error(f"Error executing webhook request: {e}")
        return False

