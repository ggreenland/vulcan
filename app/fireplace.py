"""
Async TCP client for Alflex B6R-HATV4P WiFi module.
Protocol reverse-engineered from the official app.
"""

import asyncio
from typing import Optional
from dataclasses import dataclass

from app.config import config

STX = b'\x02'
ETX = b'\x03'


@dataclass
class FireplaceStatus:
    power: bool
    flame_level: int  # 0-100
    burner2: bool
    pilot: bool
    raw_response: str


def decode_response(frame: bytes) -> Optional[bytes]:
    """Decode response frame: STX + ASCII hex + ETX -> raw bytes."""
    if len(frame) < 3:
        return None
    if frame[0:1] != STX or frame[-1:] != ETX:
        return None

    hex_str = frame[1:-1].decode("ascii")
    try:
        return bytes.fromhex(hex_str)
    except ValueError:
        return None


def percentage_to_hex(percentage: int) -> int:
    """Convert 0-100% to flame hex value (0x80-0xFF)."""
    if percentage <= 0:
        return 0x80
    hex_value = int(128 + (percentage / 100.0 * 127))
    return max(0x80, min(0xFF, hex_value))


def hex_to_percentage(hex_value: int) -> int:
    """Convert flame hex value (0x80-0xFF) to 0-100%."""
    if hex_value <= 0x80:
        return 0
    return int((hex_value - 0x80) / 127.0 * 100)


class FireplaceClient:
    """Async TCP client for Alflex B6R-HATV4P WiFi module."""

    # Command payloads (ASCII hex format)
    CMD_STATUS = b'303030308003'
    CMD_OFF = b'303030308010'
    CMD_ON_SEQ = [
        b'3030303080FE00',  # Step 1: Initialize
        b'303030308001',    # Step 2: Firmware query
        b'30303030801A',    # Step 3: Ignite trigger
    ]
    CMD_BURNER2_ON = b'30303030802001'
    CMD_BURNER2_OFF = b'30303030802000'
    # Flame: 303030308016XX where XX is hex value

    def __init__(
        self, host: str = config.FIREPLACE_IP, port: int = config.FIREPLACE_PORT
    ):
        self.host = host
        self.port = port
        self._lock = asyncio.Lock()

    async def _send_raw(
        self, payload: bytes, timeout: float = 5.0
    ) -> Optional[bytes]:
        """Send a command and wait for response. Returns decoded bytes."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except (asyncio.TimeoutError, OSError) as e:
            raise ConnectionError(f"Failed to connect to fireplace: {e}")

        try:
            frame = STX + payload + ETX
            writer.write(frame)
            await writer.drain()

            try:
                response = await asyncio.wait_for(reader.read(1024), timeout=timeout)
                return decode_response(response)
            except asyncio.TimeoutError:
                return None
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_command(
        self, payload: bytes, timeout: float = 5.0
    ) -> Optional[bytes]:
        """Send command with lock to prevent concurrent access."""
        async with self._lock:
            return await self._send_raw(payload, timeout)

    async def get_status(self) -> FireplaceStatus:
        """Query fireplace status."""
        response = await self._send_command(self.CMD_STATUS, timeout=5.0)

        if not response or len(response) < 18:
            raise ValueError(f"Invalid status response: {response}")

        # Parse device info response (53 bytes)
        # Byte[7]: Flame level (0x00 = OFF, 0x80-0xFF = ON with level)
        # Byte[9]: Status bits (bit 7 = pilot, bit 3 = burner2)
        flame_byte = response[7]
        status_byte = response[9]

        power = flame_byte >= 0x80
        flame_level = hex_to_percentage(flame_byte) if power else 0
        burner2 = bool(status_byte & 0x08)  # Bit 3
        pilot = bool(status_byte & 0x80)     # Bit 7

        return FireplaceStatus(
            power=power,
            flame_level=flame_level,
            burner2=burner2,
            pilot=pilot,
            raw_response=response.hex(),
        )

    async def power_on(self) -> bool:
        """Turn fireplace on. Sends 3-command sequence with delays."""
        async with self._lock:
            try:
                for i, cmd in enumerate(self.CMD_ON_SEQ):
                    await self._send_raw(cmd, timeout=2.0)
                    if i < len(self.CMD_ON_SEQ) - 1:
                        await asyncio.sleep(0.5)
                return True
            except Exception:
                return False

    async def power_off(self) -> bool:
        """Turn fireplace off (network standby)."""
        try:
            await self._send_command(self.CMD_OFF)
            return True
        except Exception:
            return False

    async def set_flame_level(self, level: int) -> bool:
        """Set flame level (0-100%)."""
        if not 0 <= level <= 100:
            raise ValueError("Flame level must be 0-100")

        hex_val = percentage_to_hex(level)
        payload = f'303030308016{hex_val:02X}'.encode('ascii')

        try:
            await self._send_command(payload)
            return True
        except Exception:
            return False

    async def burner2_on(self) -> bool:
        """Enable second burner."""
        try:
            await self._send_command(self.CMD_BURNER2_ON)
            return True
        except Exception:
            return False

    async def burner2_off(self) -> bool:
        """Disable second burner."""
        try:
            await self._send_command(self.CMD_BURNER2_OFF)
            return True
        except Exception:
            return False


# Global client instance
fireplace = FireplaceClient()
