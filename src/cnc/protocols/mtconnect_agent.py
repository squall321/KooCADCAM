"""MTConnect client for CNC machine monitoring.

MTConnect is an open, royalty-free standard for manufacturing
equipment data. Data is accessed via HTTP/XML REST API.

No special dependencies required (uses requests + xml.etree).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import requests


@dataclass
class MTConnectDataItem:
    """A single data item from MTConnect stream."""
    name: str
    category: str  # "SAMPLE", "EVENT", "CONDITION"
    value: Any = None
    timestamp: str = ""
    sequence: int = 0


@dataclass
class MTConnectDeviceStatus:
    """Parsed device status from MTConnect."""
    device_name: str = ""
    availability: str = "UNAVAILABLE"
    execution: str = "READY"  # ACTIVE, INTERRUPTED, STOPPED, READY
    mode: str = "AUTOMATIC"
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    feed_rate: float = 0.0
    spindle_speed: float = 0.0
    program: str = ""
    block: str = ""
    line: int = 0
    conditions: list[str] = field(default_factory=list)


class MTConnectClient:
    """HTTP client for MTConnect Agent.

    Connects to an MTConnect Agent running alongside the CNC machine.
    Standard port is 5000 or 7878.

    Usage:
        mt = MTConnectClient("http://192.168.1.100:5000")
        status = mt.get_current()
        print(status.position_x, status.spindle_speed)

        # Streaming
        for sample in mt.stream_samples(interval=1000):
            print(sample)
    """

    # MTConnect XML namespace
    NS = {"mt": "urn:mtconnect.org:MTConnectStreams:2.0"}

    def __init__(self, base_url: str, device: str | None = None) -> None:
        """
        Args:
            base_url: MTConnect Agent URL (e.g., "http://192.168.1.100:5000").
            device: Specific device name. None for first/default device.
        """
        self._base_url = base_url.rstrip("/")
        self._device = device
        self._session = requests.Session()
        self._last_sequence = 0

    def probe(self) -> dict[str, Any]:
        """Get device metadata (probe request)."""
        url = f"{self._base_url}/probe"
        if self._device:
            url = f"{self._base_url}/{self._device}/probe"
        resp = self._session.get(url, timeout=5)
        resp.raise_for_status()
        return {"raw_xml": resp.text, "status_code": resp.status_code}

    def get_current(self) -> MTConnectDeviceStatus:
        """Get current snapshot of all data items."""
        url = f"{self._base_url}/current"
        if self._device:
            url = f"{self._base_url}/{self._device}/current"
        resp = self._session.get(url, timeout=5)
        resp.raise_for_status()
        return self._parse_streams(resp.text)

    def get_sample(self, from_sequence: int = 0, count: int = 100) -> list[MTConnectDataItem]:
        """Get historical samples from a sequence number.

        Args:
            from_sequence: Starting sequence number (0 = latest).
            count: Number of samples to retrieve.
        """
        url = f"{self._base_url}/sample"
        params = {"count": count}
        if from_sequence > 0:
            params["from"] = from_sequence
        resp = self._session.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return self._parse_data_items(resp.text)

    def stream_samples(self, interval: int = 1000):
        """Generator that yields status snapshots at given interval.

        Args:
            interval: Polling interval in milliseconds.

        Yields:
            MTConnectDeviceStatus for each poll.
        """
        import time
        while True:
            try:
                status = self.get_current()
                yield status
            except Exception as e:
                yield MTConnectDeviceStatus(availability="UNAVAILABLE")
            time.sleep(interval / 1000.0)

    def _parse_streams(self, xml_text: str) -> MTConnectDeviceStatus:
        """Parse MTConnect Streams XML into structured status."""
        status = MTConnectDeviceStatus()

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return status

        # Auto-detect namespace
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        # Find all data items
        for elem in root.iter():
            tag = elem.tag.replace(ns, "") if ns else elem.tag
            text = (elem.text or "").strip()

            if tag == "Availability":
                status.availability = text
            elif tag == "Execution":
                status.execution = text
            elif tag == "ControllerMode":
                status.mode = text
            elif tag == "PathPosition" or tag == "Position":
                axis = elem.get("name", "")
                try:
                    val = float(text)
                except (ValueError, TypeError):
                    continue
                if "X" in axis:
                    status.position_x = val
                elif "Y" in axis:
                    status.position_y = val
                elif "Z" in axis:
                    status.position_z = val
            elif tag == "PathFeedrate":
                try:
                    status.feed_rate = float(text)
                except (ValueError, TypeError):
                    pass
            elif tag == "RotaryVelocity" or tag == "SpindleSpeed":
                try:
                    status.spindle_speed = float(text)
                except (ValueError, TypeError):
                    pass
            elif tag == "Program":
                status.program = text
            elif tag == "Block":
                status.block = text
            elif tag == "Line":
                try:
                    status.line = int(text)
                except (ValueError, TypeError):
                    pass

        return status

    def _parse_data_items(self, xml_text: str) -> list[MTConnectDataItem]:
        """Parse individual data items from sample response."""
        items = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return items

        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        for elem in root.iter():
            tag = elem.tag.replace(ns, "")
            if elem.get("dataItemId"):
                items.append(MTConnectDataItem(
                    name=elem.get("name", tag),
                    category=elem.get("category", ""),
                    value=elem.text,
                    timestamp=elem.get("timestamp", ""),
                    sequence=int(elem.get("sequence", 0)),
                ))

        return items
