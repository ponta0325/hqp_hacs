"""Asyncio TCP 4321 XML-over-TCP client for HQPlayer Control API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import xml.etree.ElementTree as ET

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class HQPlayerError(Exception):
    """Base exception for HQPlayer API errors."""


class HQPlayerConnectionError(HQPlayerError):
    """Raised when connection to HQPlayer fails or drops."""


@dataclass
class HQPlayerState:
    """Snapshot of HQPlayer engine state and available options."""

    state: str = "unknown"
    volume: float | None = None
    filter_1x: str | None = None
    filter_nx: str | None = None
    shaper: str | None = None
    output_mode: str | None = None
    sample_rate: str | None = None
    matrix_profile: str | None = None
    input_sample_rate: str | None = None
    output_sample_rate: str | None = None
    input_format: str | None = None
    output_format: str | None = None

    filters_1x: list[str] = field(default_factory=list)
    filters_nx: list[str] = field(default_factory=list)
    shapers: list[str] = field(default_factory=list)
    output_modes: list[str] = field(default_factory=list)
    sample_rates: list[str] = field(default_factory=list)
    matrix_profiles: list[str] = field(default_factory=list)


class HQPlayerClient:
    """Asyncio client for HQPlayer Control API (TCP 4321 / XML-over-TCP)."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Return True if socket is currently open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open TCP connection to HQPlayer."""
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (OSError, TimeoutError) as err:
            self._reader = None
            self._writer = None
            raise HQPlayerConnectionError(
                f"Failed to connect to {self.host}:{self.port}: {err}"
            ) from err

    async def disconnect(self) -> None:
        """Close TCP connection."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._reader = None
                self._writer = None

    async def _send_command(self, xml_command: str) -> ET.Element:
        """Send an XML command and read a single complete XML response element."""
        async with self._lock:
            if not self.connected:
                await self.connect()

            assert self._reader is not None
            assert self._writer is not None

            payload = f'<?xml version="1.0" encoding="UTF-8"?>{xml_command}\n'.encode(
                "utf-8"
            )
            try:
                self._writer.write(payload)
                await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
                return await asyncio.wait_for(
                    self._read_xml_element(self._reader),
                    timeout=self.timeout,
                )
            except (OSError, TimeoutError, EOFError, ET.ParseError) as err:
                await self.disconnect()
                raise HQPlayerConnectionError(
                    f"Communication error with {self.host}:{self.port}: {err}"
                ) from err

    @staticmethod
    async def _read_xml_element(reader: asyncio.StreamReader) -> ET.Element:
        """Read from stream until a complete root XML element is parsed."""
        parser = ET.XMLPullParser(events=("start", "end"))
        depth = 0
        root: ET.Element | None = None

        while True:
            chunk = await reader.read(4096)
            if not chunk:
                raise EOFError("Connection closed by HQPlayer")
            parser.feed(chunk)
            for event, elem in parser.read_events():
                if event == "start":
                    if depth == 0:
                        root = elem
                    depth += 1
                elif event == "end":
                    depth -= 1
                    if depth == 0 and root is not None:
                        return root

    @staticmethod
    def _parse_list(
        element: ET.Element, item_tag: str, attr: str = "name"
    ) -> list[str]:
        """Extract ordered option names from child XML elements."""
        items: list[str] = []
        for child in element.findall(item_tag):
            val = child.attrib.get(attr) or (child.text or "").strip()
            if val:
                items.append(val)
        return items

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        """Safely parse a float attribute."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except ValueError:
            return None

    async def get_status(self) -> ET.Element:
        """Fetch raw Status XML element."""
        return await self._send_command("<Status/>")

    async def get_filters(self) -> tuple[list[str], list[str]]:
        """Fetch available 1x and Nx filters."""
        resp = await self._send_command("<GetFilters/>")
        filters_1x = self._parse_list(resp, "Filter1x") or self._parse_list(
            resp, "Filter"
        )
        filters_nx = self._parse_list(resp, "FilterNx") or list(filters_1x)
        return filters_1x, filters_nx

    async def get_shapers(self) -> list[str]:
        """Fetch available shapers / modulators."""
        resp = await self._send_command("<GetShapers/>")
        return self._parse_list(resp, "Shaper")

    async def get_output_modes(self) -> list[str]:
        """Fetch available output modes (e.g. PCM, SDM)."""
        resp = await self._send_command("<GetOutputModes/>")
        return self._parse_list(resp, "OutputMode")

    async def get_sample_rates(self) -> list[str]:
        """Fetch available sample rates for the current output mode."""
        resp = await self._send_command("<GetRates/>")
        return self._parse_list(resp, "Rate")

    async def get_matrix_profiles(self) -> list[str]:
        """Fetch available matrix profiles."""
        resp = await self._send_command("<GetMatrixProfiles/>")
        return self._parse_list(resp, "Profile")

    async def fetch_full_state(self) -> HQPlayerState:
        """Fetch current status and all dynamic option lists."""
        status_el = await self.get_status()
        filters_1x, filters_nx = await self.get_filters()
        shapers = await self.get_shapers()
        output_modes = await self.get_output_modes()
        sample_rates = await self.get_sample_rates()
        matrix_profiles = await self.get_matrix_profiles()

        attrs = status_el.attrib
        return HQPlayerState(
            state=attrs.get("state", "unknown"),
            volume=self._parse_float(attrs.get("volume")),
            filter_1x=attrs.get("filter1x") or attrs.get("filter"),
            filter_nx=attrs.get("filternx") or attrs.get("filter"),
            shaper=attrs.get("shaper"),
            output_mode=attrs.get("mode") or attrs.get("output_mode"),
            sample_rate=attrs.get("rate") or attrs.get("sample_rate"),
            matrix_profile=attrs.get("matrix") or attrs.get("matrix_profile"),
            input_sample_rate=attrs.get("input_rate"),
            output_sample_rate=attrs.get("output_rate"),
            input_format=attrs.get("input_format"),
            output_format=attrs.get("output_format"),
            filters_1x=filters_1x,
            filters_nx=filters_nx,
            shapers=shapers,
            output_modes=output_modes,
            sample_rates=sample_rates,
            matrix_profiles=matrix_profiles,
        )

    async def set_volume(self, volume_db: float) -> None:
        """Set volume in dB."""
        await self._send_command(f'<Volume value="{volume_db:.1f}"/>')

    async def set_filter_1x(self, name: str) -> None:
        """Set 1x filter by name."""
        await self._send_command(f'<SetFilter1x name="{name}"/>')

    async def set_filter_nx(self, name: str) -> None:
        """Set Nx filter by name."""
        await self._send_command(f'<SetFilterNx name="{name}"/>')

    async def set_shaper(self, name: str) -> None:
        """Set shaper / modulator by name."""
        await self._send_command(f'<SetShaper name="{name}"/>')

    async def set_output_mode(self, name: str) -> None:
        """Set output mode (e.g. PCM, SDM) by name."""
        await self._send_command(f'<SetOutputMode name="{name}"/>')

    async def set_sample_rate(self, rate: str) -> None:
        """Set output sample rate."""
        await self._send_command(f'<SetRate name="{rate}"/>')

    async def set_matrix_profile(self, name: str) -> None:
        """Set matrix profile by name."""
        await self._send_command(f'<SetMatrixProfile name="{name}"/>')
