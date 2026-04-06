"""OPC UA client for industrial CNC machine monitoring.

OPC UA is the standard for Industry 4.0 machine communication.
Provides real-time access to machine variables, alarms, and events.

Requires: pip install opcua (python-opcua) or asyncua
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class OpcUaVariable:
    """A monitored OPC UA variable."""
    node_id: str
    name: str
    value: Any = None
    timestamp: float = 0.0


class OpcUaClient:
    """OPC UA client for CNC machine state monitoring.

    Connects to an OPC UA server running on the CNC controller
    or a gateway (e.g., Kepware, Softing, open62541).

    Usage:
        client = OpcUaClient("opc.tcp://192.168.1.100:4840")
        client.connect()
        client.subscribe("ns=2;s=Channel1.Xact", on_value_change)
        client.start_monitoring()
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._client = None
        self._subscription = None
        self._monitored_items: dict[str, OpcUaVariable] = {}
        self._callbacks: list[Callable[[str, Any], None]] = []
        self._connected = False

    def connect(self, security_policy: str | None = None, username: str | None = None,
                password: str | None = None) -> bool:
        """Connect to OPC UA server.

        Args:
            security_policy: e.g., "Basic256Sha256"
            username, password: For authenticated connections.
        """
        try:
            from opcua import Client

            self._client = Client(self._endpoint)
            if username and password:
                self._client.set_user(username)
                self._client.set_password(password)
            if security_policy:
                self._client.set_security_string(
                    f"{security_policy},SignAndEncrypt,cert.pem,key.pem"
                )

            self._client.connect()
            self._connected = True
            return True
        except ImportError:
            raise RuntimeError("opcua package not installed. Run: pip install opcua")
        except Exception as e:
            raise RuntimeError(f"OPC UA connection failed: {e}")

    def disconnect(self) -> None:
        if self._client and self._connected:
            self._client.disconnect()
        self._connected = False

    def read_variable(self, node_id: str) -> Any:
        """Read a single variable value."""
        if not self._client:
            raise RuntimeError("Not connected")
        node = self._client.get_node(node_id)
        return node.get_value()

    def write_variable(self, node_id: str, value: Any) -> bool:
        """Write a value to a variable."""
        if not self._client:
            raise RuntimeError("Not connected")
        node = self._client.get_node(node_id)
        node.set_value(value)
        return True

    def subscribe(self, node_id: str, callback: Callable[[str, Any], None] | None = None,
                  interval: int = 500) -> None:
        """Subscribe to value changes on a node.

        Args:
            node_id: OPC UA node identifier (e.g., "ns=2;s=Channel1.Xact").
            callback: Called with (node_id, new_value) on change.
            interval: Monitoring interval in milliseconds.
        """
        self._monitored_items[node_id] = OpcUaVariable(node_id, node_id)
        if callback:
            self._callbacks.append(callback)

    def read_machine_status(self) -> dict[str, Any]:
        """Read common CNC machine variables (Siemens/FANUC typical OPC UA mapping).

        Returns dict with standard keys.
        """
        standard_nodes = {
            "position_x": "ns=2;s=Channel1.Xact",
            "position_y": "ns=2;s=Channel1.Yact",
            "position_z": "ns=2;s=Channel1.Zact",
            "feed_rate": "ns=2;s=Channel1.Fact",
            "spindle_rpm": "ns=2;s=Channel1.Sact",
            "program_name": "ns=2;s=Channel1.ProgramName",
            "program_line": "ns=2;s=Channel1.CurrentLine",
            "mode": "ns=2;s=Channel1.Mode",
        }
        result = {}
        for key, node_id in standard_nodes.items():
            try:
                result[key] = self.read_variable(node_id)
            except Exception:
                result[key] = None
        return result

    def browse(self, node_id: str = "i=85") -> list[dict[str, str]]:
        """Browse available nodes under a parent."""
        if not self._client:
            raise RuntimeError("Not connected")
        node = self._client.get_node(node_id)
        children = node.get_children()
        return [
            {"node_id": str(c.nodeid), "name": c.get_browse_name().Name}
            for c in children
        ]
