"""Asyncio TCP 4321 XML-over-TCP client for HQPlayer Control API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
import logging
import xml.etree.ElementTree as ET

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

_STATE_MAP = {
    "0": "stopped",
    "1": "paused",
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
    input_bits: str | None = None
    output_format: str | None = None
    output_bits: str | None = None
    apod: int | None = None
    clips: int | None = None

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
        self._current_filter_1x_idx: str | None = None
        self._current_filter_nx_idx: str | None = None
        self._shaper_name_to_val: dict[str, str] = {}
        self._shaper_id_to_name: dict[str, str] = {}
        self._mode_name_to_val: dict[str, str] = {}
        self._mode_id_to_name: dict[str, str] = {}
        self._rate_name_to_val: dict[str, str] = {}
        self._rate_id_to_name: dict[str, str] = {}
        self._options_loaded = False

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
                resp = await asyncio.wait_for(
                    self._read_xml_element(self._reader),
                    timeout=self.timeout,
                )
                if resp.attrib.get("result") not in (None, "OK"):
                    _LOGGER.warning(
                        "HQPlayer command %s returned: %s",
                        xml_command,
                        ET.tostring(resp, encoding="unicode"),
                    )
                return resp
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
    def _parse_int(value: str | None) -> int | None:
        """Safely parse an int attribute."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except ValueError:
            return None

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
        names: list[str] = []
        n2k: dict[str, str] = {}
        k2n: dict[str, str] = {}
        for child in resp.findall(".//FiltersItem"):
            name = child.attrib.get("name")
            idx = child.attrib.get("index")
            if name and idx is not None:
                names.append(name)
                n2k[name] = idx
                k2n[idx] = name
        self._filter_name_to_val = n2k
        self._filter_id_to_name = k2n
        return names, list(names)

    async def get_shapers(self) -> list[str]:
        """Fetch available shapers / modulators (<ShapersItem>)."""
        resp = await self._send_command("<GetShapers/>")
        names: list[str] = []
        n2k: dict[str, str] = {}
        k2n: dict[str, str] = {}
        for child in resp.findall(".//ShapersItem"):
            name = child.attrib.get("name")
            idx = child.attrib.get("index")
            if name and idx is not None:
                names.append(name)
                n2k[name] = idx
                k2n[idx] = name
        self._shaper_name_to_val = n2k
        self._shaper_id_to_name = k2n
        return names

    async def get_output_modes(self) -> list[str]:
        """Fetch available output modes (<ModesItem>)."""
        resp = await self._send_command("<GetModes/>")
        names: list[str] = []
        n2k: dict[str, str] = {}
        k2n: dict[str, str] = {}
        for child in resp.findall(".//ModesItem"):
            name = child.attrib.get("name")
            idx = child.attrib.get("index")
            if name and idx is not None:
                names.append(name)
                n2k[name] = idx
                k2n[idx] = name
        self._mode_name_to_val = n2k
        self._mode_id_to_name = k2n
        return names

    async def get_sample_rates(self) -> list[str]:
        """Fetch available sample rates (<RatesItem>)."""
        resp = await self._send_command("<GetRates/>")
        names: list[str] = []
        n2k: dict[str, str] = {}
        k2n: dict[str, str] = {}
        for child in resp.findall(".//RatesItem"):
            name = child.attrib.get("name")
            val = child.attrib.get("value")
            if name and val is not None:
                names.append(name)
                n2k[name] = val
                k2n[val] = name
        self._rate_name_to_val = n2k
        self._rate_id_to_name = k2n
        return names

    async def get_matrix_profiles(self) -> list[str]:
        """Fetch available matrix profiles (<MatrixListProfiles/>) sorted A-Z."""
        resp = await self._send_command("<MatrixListProfiles/>")
        profiles = [
            child.attrib["name"]
            for child in resp.findall("MatrixProfile")
            if child.attrib.get("name")
        ]
        return sorted(profiles, key=str.casefold)

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

    def invalidate_options_cache(self) -> None:
        """Mark cached option lists as stale so the next poll refreshes them."""
        self._options_loaded = False

    def apply_status_element(
        self, status_el: ET.Element, current: HQPlayerState
    ) -> HQPlayerState:
        """Return an updated HQPlayerState from a pushed <Status> element."""
        s_attrs = status_el.attrib
        meta = status_el.find("metadata")
        meta_attrs = meta.attrib if meta is not None else {}

        raw_state = s_attrs.get("state")
        state_str = (
            _STATE_MAP.get(raw_state, raw_state)
            if raw_state is not None
            else current.state
        )
        vol = self._parse_float(s_attrs.get("volume"))
        input_sr = meta_attrs.get("samplerate") or current.input_sample_rate
        input_bits_raw = meta_attrs.get("bits")
        input_bits = f"{input_bits_raw}bit" if input_bits_raw else current.input_bits
        sdm = meta_attrs.get("sdm")
        input_fmt = (
            "DSD" if sdm == "1" else ("PCM" if sdm == "0" else current.input_format)
        )
        output_sr = s_attrs.get("active_rate") or current.output_sample_rate
        output_fmt = s_attrs.get("active_mode") or current.output_format
        active_bits = s_attrs.get("active_bits")
        output_bits = f"{active_bits}bit" if active_bits else current.output_bits
        apod = self._parse_int(s_attrs.get("apod"))
        clips = self._parse_int(s_attrs.get("clips"))
        output_mode = s_attrs.get("active_mode") or current.output_mode
        shaper = s_attrs.get("active_shaper") or current.shaper

        return replace(
            current,
            state=state_str,
            volume=vol if vol is not None else current.volume,
            output_mode=output_mode,
            shaper=shaper,
            input_sample_rate=input_sr,
            input_format=input_fmt,
            input_bits=input_bits,
            output_sample_rate=output_sr,
            output_format=output_fmt,
            output_bits=output_bits,
            apod=apod if apod is not None else current.apod,
            clips=clips if clips is not None else current.clips,
        )

    async def subscribe_status(
        self,
        on_status: Callable[[ET.Element], Awaitable[None]],
        stop_event: asyncio.Event,
    ) -> None:
        """Maintain a dedicated <Status subscribe="1"/> stream until stopped."""
        while not stop_event.is_set():
            writer: asyncio.StreamWriter | None = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    timeout=self.timeout,
                )
                writer.write(
                    b'<?xml version="1.0" encoding="UTF-8"?><Status subscribe="1"/>\n'
                )
                await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                while not stop_event.is_set():
                    elem = await self._read_xml_element(reader)
                    if elem.tag == "Status":
                        await on_status(elem)
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError, EOFError, ET.ParseError) as err:
                _LOGGER.debug("Status subscription disconnected: %s", err)
                self.invalidate_options_cache()
            finally:
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except OSError:
                        pass

            if not stop_event.is_set():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=5.0)
                except TimeoutError:
                    pass

    async def fetch_light_state(self, current: HQPlayerState | None) -> HQPlayerState:
        """Fetch only lightweight state (<Status/>, <State/>, Matrix, VolumeRange)."""
        if not self._options_loaded or current is None:
            return await self.fetch_full_state()

        status_el = await self.get_status()
        state_el = await self.get_state()
        matrix_current = await self.get_matrix_profile()
        vol_min, vol_max, vol_enabled = await self.get_volume_range()

        return self._build_state(
            status_el=status_el,
            state_el=state_el,
            filters_1x=current.filters_1x,
            filters_nx=current.filters_nx,
            shapers=current.shapers,
            output_modes=current.output_modes,
            sample_rates=current.sample_rates,
            matrix_profiles=current.matrix_profiles,
            matrix_current=matrix_current,
            vol_min=vol_min,
            vol_max=vol_max,
            vol_enabled=vol_enabled,
        )

    def _build_state(
        self,
        *,
        status_el: ET.Element,
        state_el: ET.Element,
        filters_1x: list[str],
        filters_nx: list[str],
        shapers: list[str],
        output_modes: list[str],
        sample_rates: list[str],
        matrix_profiles: list[str],
        matrix_current: str | None,
        vol_min: float | None,
        vol_max: float | None,
        vol_enabled: bool,
    ) -> HQPlayerState:
        """Assemble HQPlayerState from XML elements and option lists."""

        return self._build_state(
            status_el=status_el,
            state_el=state_el,
            filters_1x=current.filters_1x,
            filters_nx=current.filters_nx,
            shapers=current.shapers,
            output_modes=current.output_modes,
            sample_rates=current.sample_rates,
            matrix_profiles=current.matrix_profiles,
            matrix_current=matrix_current,
            vol_min=vol_min,
            vol_max=vol_max,
            vol_enabled=vol_enabled,
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
        self._options_loaded = True

        return self._build_state(
            status_el=status_el,
            state_el=state_el,
            filters_1x=filters_1x,
            filters_nx=filters_nx,
            shapers=shapers,
            output_modes=output_modes,
            sample_rates=sample_rates,
            matrix_profiles=matrix_profiles,
            matrix_current=matrix_current,
            vol_min=vol_min,
            vol_max=vol_max,
            vol_enabled=vol_enabled,
        )

    def _build_state(
        self,
        *,
        status_el: ET.Element,
        state_el: ET.Element,
        filters_1x: list[str],
        filters_nx: list[str],
        shapers: list[str],
        output_modes: list[str],
        sample_rates: list[str],
        matrix_profiles: list[str],
        matrix_current: str | None,
        vol_min: float | None,
        vol_max: float | None,
        vol_enabled: bool,
    ) -> HQPlayerState:
        """Assemble HQPlayerState from XML elements and option lists."""

        s_attrs = status_el.attrib
        st_attrs = state_el.attrib
        meta = status_el.find("metadata")
        meta_attrs = meta.attrib if meta is not None else {}

        raw_state = st_attrs.get("state") or s_attrs.get("state", "unknown")
        state_str = _STATE_MAP.get(raw_state, raw_state)

        filter_1x_val = st_attrs.get("filter1x") or st_attrs.get("filter")
        filter_nx_val = st_attrs.get("filterNx") or st_attrs.get("filter")
        self._current_filter_1x_idx = filter_1x_val
        self._current_filter_nx_idx = filter_nx_val
        shaper_val = st_attrs.get("shaper")
        mode_val = st_attrs.get("mode") or st_attrs.get("active_mode")
        rate_val = st_attrs.get("rate")

        input_sr = meta_attrs.get("samplerate")
        input_bits_raw = meta_attrs.get("bits")
        input_bits = f"{input_bits_raw}bit" if input_bits_raw else None
        sdm = meta_attrs.get("sdm")
        input_fmt = "DSD" if sdm == "1" else ("PCM" if sdm == "0" else None)
        output_sr = s_attrs.get("active_rate") or st_attrs.get("active_rate")
        output_fmt = s_attrs.get("active_mode")
        active_bits = s_attrs.get("active_bits")
        output_bits = f"{active_bits}bit" if active_bits else None

        return HQPlayerState(
            state=state_str,
            volume=self._parse_float(
                st_attrs.get("volume") or s_attrs.get("volume")
            ),
            volume_min=vol_min,
            volume_max=vol_max,
            volume_enabled=vol_enabled,
            filter_1x=(
                self._filter_id_to_name.get(filter_1x_val, filter_1x_val)
                if filter_1x_val is not None
                else s_attrs.get("active_filter")
            ),
            filter_nx=(
                self._filter_id_to_name.get(filter_nx_val, filter_nx_val)
                if filter_nx_val is not None
                else s_attrs.get("active_filter")
            ),
            shaper=(
                self._shaper_id_to_name.get(shaper_val, shaper_val)
                if shaper_val is not None
                else s_attrs.get("active_shaper")
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
            input_bits=input_bits,
            output_format=output_fmt,
            output_bits=output_bits,
            apod=self._parse_int(s_attrs.get("apod")),
            clips=self._parse_int(s_attrs.get("clips")),
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
        """Set 1x filter independently (<SetFilter value="{nx}" value1x="{1x}"/>)."""
        idx_1x = self._filter_name_to_val.get(name, name)
        idx_nx = self._current_filter_nx_idx or idx_1x
        self._current_filter_1x_idx = idx_1x
        await self._send_command(
            f'<SetFilter value="{idx_nx}" value1x="{idx_1x}"/>'
        )

    async def set_filter_nx(self, name: str) -> None:
        """Set Nx filter independently (<SetFilter value="{nx}" value1x="{1x}"/>)."""
        idx_nx = self._filter_name_to_val.get(name, name)
        idx_1x = self._current_filter_1x_idx or idx_nx
        self._current_filter_nx_idx = idx_nx
        await self._send_command(
            f'<SetFilter value="{idx_nx}" value1x="{idx_1x}"/>'
        )

    async def set_shaper(self, name: str) -> None:
        """Set shaper / modulator by name (<SetShaping value="{index}"/>)."""
        val = self._shaper_name_to_val.get(name, name)
        await self._send_command(f'<SetShaping value="{val}"/>')

    async def set_output_mode(self, name: str) -> None:
        """Set output mode by name (maps to HQPlayer index)."""
        val = self._mode_name_to_val.get(name, name)
        await self._send_command(f'<SetMode value="{val}"/>')
        self.invalidate_options_cache()

    async def set_sample_rate(self, name: str) -> None:
        """Set output sample rate by name (maps to HQPlayer value)."""
        val = self._rate_name_to_val.get(name, name)
        await self._send_command(f'<SetRate value="{val}"/>')

    async def set_matrix_profile(self, name: str) -> None:
        """Set matrix profile (<MatrixSetProfile value="..."/>)."""
        await self._send_command(f'<MatrixSetProfile value="{name}"/>')
