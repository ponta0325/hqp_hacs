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
    """Mock HQPlayer TCP 4321 XML server matching hqplayer_tcp_4321_protocol_spec.md."""

    def __init__(self) -> None:
        self.mode = "0"  # 0=PCM, 1=SDM (DSD)
        self.volume = -12.0
        self.filter = "48"
        self.shaper = "20"
        self.rate = "768000"
        self.matrix = "LANDER"
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
        active_mode_str = "SDM (DSD)" if self.mode == "1" else "PCM"
        if tag == "Status":
            return (
                f'<Status active_mode="{active_mode_str}" active_rate="{self.rate}" '
                f'active_filter="poly-sinc-gauss-long" active_shaper="LNS15" '
                f'state="2" volume="{self.volume:.1f}">'
                '<metadata samplerate="44100" bits="16" channels="2"/>'
                "</Status>"
            )
        if tag == "State":
            return (
                f'<State active_mode="{self.mode}" active_rate="{self.rate}" '
                f'filter="{self.filter}" filter1x="{self.filter}" filterNx="{self.filter}" '
                f'matrix_profile="{self.matrix}" mode="{self.mode}" rate="{self.rate}" '
                f'shaper="{self.shaper}" state="2" volume="{self.volume:.1f}"/>'
            )
        if tag == "GetFilters":
            return (
                "<GetFilters>"
                '<FiltersItem index="0" name="IIR" value="64"/>'
                '<FiltersItem index="1" name="poly-sinc-gauss-long" value="48"/>'
                "</GetFilters>"
            )
        if tag == "GetShapers":
            if self.mode == "1":
                return (
                    "<GetShapers>"
                    '<ShapersItem index="25" name="ASDM7EC-super" value="20"/>'
                    '<ShapersItem index="24" name="ASDM5EC" value="19"/>'
                    "</GetShapers>"
                )
            return (
                "<GetShapers>"
                '<ShapersItem index="10" name="LNS15" value="20"/>'
                '<ShapersItem index="11" name="NS9" value="21"/>'
                "</GetShapers>"
            )
        if tag == "GetModes":
            return (
                "<GetModes>"
                '<ModesItem index="0" name="[source]" value="-1"/>'
                '<ModesItem index="1" name="PCM" value="0"/>'
                '<ModesItem index="2" name="SDM (DSD)" value="1"/>'
                "</GetModes>"
            )
        if tag == "GetRates":
            if self.mode == "1":
                return (
                    "<GetRates>"
                    '<RatesItem name="Auto" value="0"/>'
                    '<RatesItem name="11289600" value="11289600"/>'
                    '<RatesItem name="22579200" value="22579200"/>'
                    "</GetRates>"
                )
            return (
                "<GetRates>"
                '<RatesItem name="Auto" value="0"/>'
                '<RatesItem name="384000" value="384000"/>'
                '<RatesItem name="768000" value="768000"/>'
                "</GetRates>"
            )
        if tag == "MatrixListProfiles":
            return (
                "<MatrixListProfiles>"
                '<MatrixProfile name="DX1"/>'
                '<MatrixProfile name="LANDER"/>'
                "</MatrixListProfiles>"
            )
        if tag == "MatrixGetProfile":
            return f'<MatrixGetProfile result="OK" value="{self.matrix}"/>'
        if tag == "VolumeRange":
            return '<VolumeRange adaptive="0" enabled="1" max="0.0" min="-60.0"/>'
        if tag == "SetMode":
            self.mode = root.attrib["value"]
            if self.mode == "1":
                self.shaper = "20"
                self.rate = "11289600"
            return '<SetMode result="OK"/>'
        if tag == "Volume":
            self.volume = float(root.attrib["value"])
            return '<Volume result="OK"/>'
        if tag == "MatrixSetProfile":
            self.matrix = root.attrib["value"]
            return '<MatrixSetProfile result="OK"/>'
        return f'<{tag} result="OK"/>'


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
        self.assertEqual(state.filter_1x, "poly-sinc-gauss-long")
        self.assertEqual(state.shapers, ["LNS15", "NS9"])
        self.assertEqual(state.sample_rates, ["Auto", "384000", "768000"])
        self.assertEqual(state.matrix_profiles, ["DX1", "LANDER"])
        self.assertEqual(state.matrix_profile, "LANDER")

        # Switch output mode to SDM (DSD), change matrix profile and volume
        await self.client.set_output_mode("SDM (DSD)")
        await self.client.set_matrix_profile("DX1")
        await self.client.set_volume(-6.5)

        state2 = await self.client.fetch_full_state()
        self.assertEqual(state2.output_mode, "SDM (DSD)")
        self.assertEqual(state2.matrix_profile, "DX1")
        self.assertEqual(state2.volume, -6.5)
        self.assertEqual(state2.shapers, ["ASDM7EC-super", "ASDM5EC"])
        self.assertEqual(state2.sample_rates, ["Auto", "11289600", "22579200"])

    async def test_connection_error_on_unreachable_port(self) -> None:
        bad_client = HQPlayerClient("127.0.0.1", 1, timeout=0.5)
        with self.assertRaises(HQPlayerConnectionError):
            await bad_client.connect()


if __name__ == "__main__":
    unittest.main()
