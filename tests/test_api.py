"""Unit tests for HQPlayerControl API asyncio TCP 4321 client."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
import xml.etree.ElementTree as ET

# Load api.py directly without requiring homeassistant package installed
ROOT = Path(__file__).resolve().parent.parent
PKG_PATH = ROOT / "custom_components" / "hqplayer"

pkg = types.ModuleType("hqplayer")
pkg.__path__ = [str(PKG_PATH)]
sys.modules["hqplayer"] = pkg

const_mod = types.ModuleType("hqplayer.const")
const_mod.DEFAULT_PORT = 4321
const_mod.DEFAULT_TIMEOUT = 2.0
sys.modules["hqplayer.const"] = const_mod

spec = importlib.util.spec_from_file_location("hqplayer.api", PKG_PATH / "api.py")
assert spec is not None and spec.loader is not None
api_mod = importlib.util.module_from_spec(spec)
sys.modules["hqplayer.api"] = api_mod
spec.loader.exec_module(api_mod)

HQPlayerClient = api_mod.HQPlayerClient
HQPlayerConnectionError = api_mod.HQPlayerConnectionError


class MockHQPlayerServer:
    """Minimal mock HQPlayer TCP 4321 XML server."""

    def __init__(self) -> None:
        self.mode = "PCM"
        self.volume = -12.0
        self.filter_1x = "poly-sinc-gauss-long"
        self.filter_nx = "poly-sinc-gauss-hires-lp"
        self.shaper = "LNS15"
        self.rate = "768000"
        self.matrix = "Default"
        self.server: asyncio.Server | None = None
        self.port: int = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        sock = self.server.sockets[0]
        self.port = sock.getsockname()[1]

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8").strip()
                if not text:
                    continue
                root = ET.fromstring(text)
                resp = self._dispatch(root)
                writer.write((resp + "\n").encode("utf-8"))
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    def _dispatch(self, root: ET.Element) -> str:
        tag = root.tag
        if tag == "Status":
            return (
                f'<Status state="playing" volume="{self.volume:.1f}" '
                f'filter1x="{self.filter_1x}" filternx="{self.filter_nx}" '
                f'shaper="{self.shaper}" mode="{self.mode}" rate="{self.rate}" '
                f'matrix="{self.matrix}" input_rate="44100" output_rate="{self.rate}" '
                f'input_format="PCM" output_format="{self.mode}"/>'
            )
        if tag == "GetFilters":
            return (
                "<GetFilters>"
                '<Filter1x name="poly-sinc-gauss-long"/>'
                '<Filter1x name="sinc-M"/>'
                '<FilterNx name="poly-sinc-gauss-hires-lp"/>'
                '<FilterNx name="sinc-L"/>'
                "</GetFilters>"
            )
        if tag == "GetShapers":
            if self.mode == "SDM":
                return '<GetShapers><Shaper name="ASDM7EC-super"/><Shaper name="ASDM5EC"/></GetShapers>'
            return '<GetShapers><Shaper name="LNS15"/><Shaper name="NS9"/></GetShapers>'
        if tag == "GetOutputModes":
            return '<GetOutputModes><OutputMode name="PCM"/><OutputMode name="SDM"/></GetOutputModes>'
        if tag == "GetRates":
            if self.mode == "SDM":
                return '<GetRates><Rate name="11289600"/><Rate name="22579200"/></GetRates>'
            return '<GetRates><Rate name="384000"/><Rate name="768000"/></GetRates>'
        if tag == "GetMatrixProfiles":
            return '<GetMatrixProfiles><Profile name="Default"/><Profile name="RoomEQ"/></GetMatrixProfiles>'
        if tag == "SetOutputMode":
            self.mode = root.attrib["name"]
            if self.mode == "SDM":
                self.shaper = "ASDM7EC-super"
                self.rate = "11289600"
            return "<SetOutputMode ok=\"1\"/>"
        if tag == "Volume":
            self.volume = float(root.attrib["value"])
            return "<Volume ok=\"1\"/>"
        if tag == "SetFilter1x":
            self.filter_1x = root.attrib["name"]
            return "<SetFilter1x ok=\"1\"/>"
        return f"<{tag} ok=\"1\"/>"


class TestHQPlayerClient(unittest.IsolatedAsyncioTestCase):
    """Tests for HQPlayerClient."""

    async def asyncSetUp(self) -> None:
        self.server = MockHQPlayerServer()
        await self.server.start()
        self.client = HQPlayerClient("127.0.0.1", self.server.port, timeout=2.0)

    async def asyncTearDown(self) -> None:
        await self.client.disconnect()
        await self.server.stop()

    async def test_fetch_full_state_and_dynamic_mode_switch(self) -> None:
        state = await self.client.fetch_full_state()
        self.assertEqual(state.state, "playing")
        self.assertEqual(state.volume, -12.0)
        self.assertEqual(state.output_mode, "PCM")
        self.assertEqual(state.shapers, ["LNS15", "NS9"])
        self.assertEqual(state.sample_rates, ["384000", "768000"])
        self.assertEqual(state.matrix_profiles, ["Default", "RoomEQ"])

        # Switch output mode to SDM and verify dynamic options update
        await self.client.set_output_mode("SDM")
        await self.client.set_volume(-6.5)
        state2 = await self.client.fetch_full_state()
        self.assertEqual(state2.output_mode, "SDM")
        self.assertEqual(state2.volume, -6.5)
        self.assertEqual(state2.shapers, ["ASDM7EC-super", "ASDM5EC"])
        self.assertEqual(state2.sample_rates, ["11289600", "22579200"])

    async def test_connection_error_on_unreachable_port(self) -> None:
        bad_client = HQPlayerClient("127.0.0.1", 1, timeout=0.5)
        with self.assertRaises(HQPlayerConnectionError):
            await bad_client.connect()


if __name__ == "__main__":
    unittest.main()
