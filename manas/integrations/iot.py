"""Edge / IoT / robotics adapters (MQTT). The Phase 14 acceptance criterion
is a hard invariant: PHYSICAL ACTUATION IS IMPOSSIBLE WITHOUT HUMAN APPROVAL.

Enforced in depth, not just by convention:
  1) actuate is APPROVAL at the ToolGate (as every write is), AND
  2) actuate carries always_gate=True: the ToolGate refuses to even consult
     an auto-approver policy for such tools — a human callable must answer,
     per invocation. No config flag can relax this.
  3) Like desktop control, dry_run previews the exact publish first.
Backend (paho-mqtt) optional + injectable; sensors are read-only and SAFE.
"""
from manas.kernel.config import settings
from manas.kernel.errors import ManasError
from manas.kernel.registry import tools


class MqttBackend:
    def __init__(self) -> None:
        try:
            import paho.mqtt.client as mqtt  # optional: pip install paho-mqtt
        except ImportError as e:
            raise ManasError("IoT needs: pip install paho-mqtt") from e
        self.c = mqtt.Client()
        if settings.mqtt_user:
            self.c.username_pw_set(settings.mqtt_user, settings.mqtt_pass)
        host, _, port = settings.mqtt_broker.partition(":")
        self.c.connect(host, int(port or 1883), keepalive=30)

    def publish(self, topic: str, payload: str, qos: int = 1) -> None:
        info = self.c.publish(topic, payload, qos=qos)
        info.wait_for_publish(timeout=10)

    def read(self, topic: str, timeout: float = 5.0) -> str | None:
        out: list[str] = []
        self.c.on_message = lambda c, u, m: out.append(m.payload.decode())
        self.c.subscribe(topic)
        self.c.loop_start()
        import time
        t0 = time.time()
        while not out and time.time() - t0 < timeout:
            time.sleep(0.05)
        self.c.loop_stop()
        return out[0] if out else None


@tools.register("sensor_read")
class SensorRead:
    """Read one message from a sensor topic. Read-only -> SAFE."""
    risk_level = "SAFE"

    def __init__(self, backend=None) -> None:
        self._backend = backend

    async def __call__(self, topic: str, timeout: float = 5.0) -> dict:
        b = self._backend or MqttBackend()
        value = b.read(topic, timeout)
        return {"topic": topic, "value": value, "timed_out": value is None}


@tools.register("actuate")
class Actuate:
    """Publish a command to an actuator topic. Moves physical things."""
    risk_level = "APPROVAL"
    always_gate = True                 # ToolGate: human callable required, always
    approval_reason = "commands a PHYSICAL actuator (motor/relay/robot)"

    def __init__(self, backend=None) -> None:
        self._backend = backend

    async def __call__(self, topic: str, payload: str,
                       dry_run: bool = True) -> dict:
        if not topic.strip() or "#" in topic or "+" in topic:
            raise ManasError("actuation topic must be explicit (no wildcards)")
        if dry_run:
            return {"dry_run": True,
                    "would_publish": {"topic": topic, "bytes": len(payload)}}
        b = self._backend or MqttBackend()
        b.publish(topic, payload)
        return {"dry_run": False, "published": topic}
