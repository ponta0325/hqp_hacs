"""Asyncio TCP 4321 XML-over-TCP client for HQPlayer Control API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import xml.etree.ElementTree as ET

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_STATE_MAP = {
    "1": "stopped",
    "2": "playing",
}


class HQPlayerError(Exception):
    """Base exception for HQPlayer API errors."""


class HQPlayerConnectionError(HQPlayerError):
    """Raised when connection to HQPlayer fails or drops."""


@dataclass
class HQPlayerState:
    """Snapshot of HQPlayer engine state and available options."""

    state: str = "unknown"
    volume: float | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_enabled: bool = True
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

        # Name <-> value / index mappings populated from Get* commands
        self._filter_name_to_val: dict[str, str] = {}
        self._filter_id_to_name: dict[str, str] = {}
        self._shaper_name_to_val: dict[str, str] = {}
        self._shaper_id_to_name: dict[str, str] = {}
        self._mode_name_to_val: dict[str, str] = {}
        self._mode_id_to_name: dict[str, str] = {}
        self._rate_name_to_val: dict[str, str] = {}
        self._rate_id_to_name: dict[str, str] = {}

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
    def _parse_item_map(
        element: ET.Element, *item_tags: str
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        """Extract ordered names, name->value, and (value|index)->name mappings."""
        names: list[str] = []
        name_to_val: dict[str, str] = {}
        id_to_name: dict[str, str] = {}
        for tag in item_tags:
            for child in element.findall(f".//{tag}"):
                name = child.attrib.get("name")
                val = child.attrib.get("value")
                idx = child.attrib.get("index")
                target_val = val if val is not None else (idx or name)
                if name and target_val is not None:
                    names.append(name)
                    name_to_val[name] = target_val
                    if val is not None:
                        id_to_name[val] = name
                    if idx is not None and idx not in id_to_name:
                        id_to_name[idx] = name
            if names:
                break
        return names, name_to_val, id_to_name

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

    async def get_state(self) -> ET.Element:
        """Fetch raw State XML element."""
        return await self._send_command("<State/>")

    async def get_filters(self) -> tuple[list[str], list[str]]:
        """Fetch available filters (<FiltersItem>)."""
        resp = await self._send_command("<GetFilters/>")
        names, n2v, v2n = self._parse_item_map(
            resp, "FiltersItem", "FilterItem", "Filter", "Filter1x"
        )
        if not names:
            _LOGGER.debug(
                "GetFilters returned no items: %s",
                ET.tostring(resp, encoding="unicode"),
            )
        self._filter_name_to_val = n2v
        self._filter_id_to_name = v2n
        return names, list(names)

    async def get_shapers(self) -> list[str]:
        """Fetch available shapers / modulators (<ShapersItem>)."""
        resp = await self._send_command("<GetShapers/>")
        names, n2v, v2n = self._parse_item_map(resp, "ShapersItem")
        self._shaper_name_to_val = n2v
        self._shaper_id_to_name = v2n
        return names

    async def get_output_modes(self) -> list[str]:
        """Fetch available output modes (<ModesItem>)."""
        resp = await self._send_command("<GetModes/>")
        names, n2v, v2n = self._parse_item_map(resp, "ModesItem")
        self._mode_name_to_val = n2v
        self._mode_id_to_name = v2n
        return names

    async def get_sample_rates(self) -> list[str]:
        """Fetch available sample rates (<RatesItem>)."""
        resp = await self._send_command("<GetRates/>")
        names, n2v, v2n = self._parse_item_map(resp, "RatesItem")
        self._rate_name_to_val = n2v
        self._rate_id_to_name = v2n
        return names

    async def get_matrix_profiles(self) -> list[str]:
        """Fetch available matrix profiles (<MatrixListProfiles/>)."""
        resp = await self._send_command("<MatrixListProfiles/>")
        return [
            child.attrib["name"]
            for child in resp.findall("MatrixProfile")
            if child.attrib.get("name")
        ]

    async def get_matrix_profile(self) -> str | None:
        """Fetch currently active matrix profile (<MatrixGetProfile/>)."""
        resp = await self._send_command("<MatrixGetProfile/>")
        return resp.attrib.get("value")

    async def get_volume_range(self) -> tuple[float | None, float | None, bool]:
        """Fetch volume range and enabled flag (<VolumeRange/>)."""
        resp = await self._send_command("<VolumeRange/>")
        return (
            self._parse_float(resp.attrib.get("min")),
            self._parse_float(resp.attrib.get("max")),
            resp.attrib.get("enabled", "1") == "1",
        )

    async def fetch_full_state(self) -> HQPlayerState:
        """Fetch current status, engine state, and all dynamic option lists."""
        status_el = await self.get_status()
        state_el = await self.get_state()
        filters_1x, filters_nx = await self.get_filters()
        shapers = await self.get_shapers()
        output_modes = await self.get_output_modes()
        sample_rates = await self.get_sample_rates()
        matrix_profiles = await self.get_matrix_profiles()
        matrix_current = await self.get_matrix_profile()
        vol_min, vol_max, vol_enabled = await self.get_volume_range()

        s_attrs = status_el.attrib
        st_attrs = state_el.attrib
        meta = status_el.find("metadata")
        meta_attrs = meta.attrib if meta is not None else {}

        raw_state = st_attrs.get("state") or s_attrs.get("state", "unknown")
        state_str = _STATE_MAP.get(raw_state, raw_state)

        filter_1x_val = st_attrs.get("filter1x") or st_attrs.get("filter")
        filter_nx_val = st_attrs.get("filterNx") or st_attrs.get("filter")
        shaper_val = st_attrs.get("shaper")
        mode_val = st_attrs.get("mode") or st_attrs.get("active_mode")
        rate_val = st_attrs.get("rate")

        input_sr = meta_attrs.get("samplerate")
        input_bits = meta_attrs.get("bits")
        input_fmt = f"{input_bits}bit" if input_bits else None
        output_sr = s_attrs.get("active_rate") or st_attrs.get("active_rate")
        output_fmt = s_attrs.get("active_mode")

        return HQPlayerState(
            state=state_str,
            volume=self._parse_float(
                st_attrs.get("volume") or s_attrs.get("volume")
            ),
            volume_min=vol_min,
            volume_max=vol_max,
            volume_enabled=vol_enabled,
            filter_1x=(
                s_attrs.get("active_filter")
                or (
                    self._filter_id_to_name.get(filter_1x_val, filter_1x_val)
                    if filter_1x_val is not None
                    else None
                )
            ),
            filter_nx=(
                s_attrs.get("active_filter")
                or (
                    self._filter_id_to_name.get(filter_nx_val, filter_nx_val)
                    if filter_nx_val is not None
                    else None
                )
            ),
            shaper=(
                s_attrs.get("active_shaper")
                or (
                    self._shaper_id_to_name.get(shaper_val, shaper_val)
                    if shaper_val is not None
                    else None
                )
            ),
            output_mode=(
                s_attrs.get("active_mode")
                or (
                    self._mode_id_to_name.get(mode_val, mode_val)
                    if mode_val is not None
                    else None
                )
            ),
            sample_rate=(
                self._rate_id_to_name.get(rate_val, rate_val)
                if rate_val is not None
                else output_sr
            ),
            matrix_profile=matrix_current or st_attrs.get("matrix_profile"),
            input_sample_rate=input_sr,
            output_sample_rate=output_sr,
            input_format=input_fmt,
            output_format=output_fmt,
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
        """Set filter by name (maps to HQPlayer value)."""
        val = self._filter_name_to_val.get(name, name)
        await self._send_command(f'<SetFilter value="{val}"/>')

    async def set_filter_nx(self, name: str) -> None:
        """Set Nx filter by name (maps to HQPlayer value)."""
        val = self._filter_name_to_val.get(name, name)
        await self._send_command(f'<SetFilter value="{val}"/>')

    async def set_shaper(self, name: str) -> None:
        """Set shaper / modulator by name (maps to HQPlayer value)."""
        val = self._shaper_name_to_val.get(name, name)
        await self._send_command(f'<SetShaper value="{val}"/>')

    async def set_output_mode(self, name: str) -> None:
        """Set output mode by name (maps to HQPlayer value)."""
        val = self._mode_name_to_val.get(name, name)
        await self._send_command(f'<SetMode value="{val}"/>')

    async def set_sample_rate(self, name: str) -> None:
        """Set output sample rate by name (maps to HQPlayer value)."""
        val = self._rate_name_to_val.get(name, name)
        await self._send_command(f'<SetRate value="{val}"/>')

    async def set_matrix_profile(self, name: str) -> None:
        """Set matrix profile (<MatrixSetProfile value="..."/>)."""
        await self._send_command(f'<MatrixSetProfile value="{name}"/>')
