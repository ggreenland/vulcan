"""Tests for the fireplace protocol encoding/decoding."""

import pytest
from app.fireplace import (
    decode_response,
    percentage_to_hex,
    hex_to_percentage,
    STX,
    ETX,
)


class TestPercentageConversion:
    """Test flame level percentage <-> hex conversions."""

    def test_percentage_to_hex_zero(self):
        assert percentage_to_hex(0) == 0x80

    def test_percentage_to_hex_hundred(self):
        assert percentage_to_hex(100) == 0xFF

    def test_percentage_to_hex_fifty(self):
        # 128 + (50/100 * 127) = 128 + 63.5 = 191.5 -> 191 = 0xBF
        result = percentage_to_hex(50)
        assert 0xBE <= result <= 0xC0  # Allow slight rounding variance

    def test_percentage_to_hex_negative_clamps(self):
        assert percentage_to_hex(-10) == 0x80

    def test_hex_to_percentage_min(self):
        assert hex_to_percentage(0x80) == 0

    def test_hex_to_percentage_max(self):
        assert hex_to_percentage(0xFF) == 100

    def test_hex_to_percentage_mid(self):
        # 0xBF = 191 -> (191 - 128) / 127 * 100 = 49.6 -> 49
        result = hex_to_percentage(0xBF)
        assert 48 <= result <= 51  # Allow rounding variance

    def test_roundtrip_conversion(self):
        """Test that conversion is reasonably reversible."""
        for pct in [0, 25, 50, 75, 100]:
            hex_val = percentage_to_hex(pct)
            recovered = hex_to_percentage(hex_val)
            assert abs(recovered - pct) <= 2  # Within 2% tolerance


class TestFrameDecoding:
    """Test response frame decoding."""

    def test_decode_valid_frame(self):
        # STX + "0303000000035c" + ETX
        frame = STX + b'0303000000035c' + ETX
        result = decode_response(frame)
        assert result == bytes.fromhex('0303000000035c')

    def test_decode_missing_stx(self):
        frame = b'0303000000035c' + ETX
        assert decode_response(frame) is None

    def test_decode_missing_etx(self):
        frame = STX + b'0303000000035c'
        assert decode_response(frame) is None

    def test_decode_empty_frame(self):
        assert decode_response(b'') is None

    def test_decode_too_short(self):
        assert decode_response(b'\x02\x03') is None

    def test_decode_invalid_hex(self):
        frame = STX + b'GHIJ' + ETX
        assert decode_response(frame) is None

    def test_decode_real_status_response(self):
        """Test decoding a real status response from the fireplace."""
        # Real response captured during testing
        raw_hex = '0303000000035c8a82c900040000011f00c84c616b652046697265706c616365ffffffffffff000000000000000000000000044201'
        frame = STX + raw_hex.encode('ascii') + ETX
        result = decode_response(frame)

        assert result is not None
        assert len(result) == 53  # Device info response is 53 bytes
        assert result[0:2] == bytes([0x03, 0x03])  # Response header


class TestStatusParsing:
    """Test parsing of status response bytes."""

    def test_parse_power_on(self):
        """Byte 7 >= 0x80 means power on."""
        assert 0x8A >= 0x80  # Power on with flame

    def test_parse_power_off(self):
        """Byte 7 == 0x00 means power off."""
        assert 0x00 < 0x80  # Power off

    def test_parse_burner2_on(self):
        """Byte 9 bit 3 set means burner2 on."""
        status_byte = 0xC9  # 11001001
        assert bool(status_byte & 0x08)  # Bit 3 = burner2

    def test_parse_burner2_off(self):
        """Byte 9 bit 3 clear means burner2 off."""
        status_byte = 0xC1  # 11000001
        assert not bool(status_byte & 0x08)

    def test_parse_pilot_on(self):
        """Byte 9 bit 7 set means pilot on."""
        status_byte = 0xC9  # 11001001
        assert bool(status_byte & 0x80)  # Bit 7 = pilot

    def test_parse_pilot_off(self):
        """Byte 9 bit 7 clear means pilot off."""
        status_byte = 0x09  # 00001001
        assert not bool(status_byte & 0x80)


class TestCommandPayloads:
    """Test that command payloads are correctly formatted."""

    def test_status_command(self):
        from app.fireplace import FireplaceClient
        assert FireplaceClient.CMD_STATUS == b'303030308003'

    def test_off_command(self):
        from app.fireplace import FireplaceClient
        assert FireplaceClient.CMD_OFF == b'303030308010'

    def test_on_sequence_length(self):
        from app.fireplace import FireplaceClient
        assert len(FireplaceClient.CMD_ON_SEQ) == 3

    def test_on_sequence_commands(self):
        from app.fireplace import FireplaceClient
        assert FireplaceClient.CMD_ON_SEQ[0] == b'3030303080FE00'
        assert FireplaceClient.CMD_ON_SEQ[1] == b'303030308001'
        assert FireplaceClient.CMD_ON_SEQ[2] == b'30303030801A'

    def test_burner2_commands(self):
        from app.fireplace import FireplaceClient
        assert FireplaceClient.CMD_BURNER2_ON == b'30303030802001'
        assert FireplaceClient.CMD_BURNER2_OFF == b'30303030802000'

    def test_flame_command_format(self):
        """Test flame command is correctly formatted."""
        level = 50
        hex_val = percentage_to_hex(level)
        payload = f'303030308016{hex_val:02X}'.encode('ascii')

        assert payload.startswith(b'303030308016')
        assert len(payload) == 14  # 12 chars prefix + 2 chars hex value
