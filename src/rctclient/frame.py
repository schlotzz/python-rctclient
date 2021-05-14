
# Copyright 2020, Peter Oberhofer (pob90)
# Copyright 2020, Stefan Valouch (svalouch)
# SPDX-License-Identifier: GPL-3.0-only

import struct
from typing import Union

from .exceptions import FrameCRCMismatch, FrameNotComplete
from .types import Command, FrameType
from .utils import CRC16

#: Token that starts a frame
START_TOKEN = b'+'
#: Token that escapes the next value
ESCAPE_TOKEN = b'-'
#: Length of the header
FRAME_LENGTH_HEADER = 1
#: Length of a command
FRAME_LENGTH_COMMAND = 1
#: Length of the length information
FRAME_LENGTH_LENGTH = 2
#: Length of a frame, contains 1 byte header, 1 byte command and 2 bytes length
FRAME_HEADER_WITH_LENGTH = FRAME_LENGTH_HEADER + FRAME_LENGTH_COMMAND + FRAME_LENGTH_LENGTH
#: Length of the CRC16 checkum
FRAME_LENGTH_CRC16 = 2


def make_frame(command: Command, id: int, payload: bytes = b'', address: int = 0,
               frame_type: FrameType = FrameType.STANDARD) -> bytes:
    '''
    Crafts the byte-stream representing the input values. The result of this function can be sent as-is to the target
    device.

    `payload` is ignored for ``READ`` commands. and the `address` is ignored for ``STANDARD`` frames.

    For a variant which stores the input values as well as the output, see :class:`~rctclient.frame.SendFrame`.

    .. versionadded:: 0.0.2

    :param command: The command to transmit.
    :param id: The object ID to target.
    :param payload: The payload to be transmitted. Use :func:`~rctclient.utils.encode_value` to generate valid
       payloads.
    :param address: Address for plant communication (untested, ignored for standard communication).
    :param frame_type: The type if frame to transmit (standard or plant).

    :return: byte object ready to be sent to a device.
    '''
    # start with the command
    buf = bytearray(struct.pack('B', command))

    # add frame type and length of payload
    if command in [Command.LONG_WRITE, Command.LONG_RESPONSE]:
        buf += struct.pack('>H', frame_type + len(payload))  # 2 bytes
    else:
        buf += struct.pack('>B', frame_type + len(payload))  # 1 byte

    # add address for plants
    if frame_type == FrameType.PLANT:
        buf += struct.pack('>I', address)  # 4 bytes

    # add the ID
    buf += struct.pack('>I', id)  # 4 bytes

    # add the payload unless it's a READ
    if command != Command.READ:
        buf += payload  # N bytes

    # calculate and append the checksum
    crc16 = CRC16(buf)
    buf += struct.pack('>H', crc16)

    data = bytearray(struct.pack('c', START_TOKEN))

    # go over the buffer and inject escape tokens

    for byt in buf:
        byte = bytes([byt])
        if byte in [START_TOKEN, ESCAPE_TOKEN]:
            data += ESCAPE_TOKEN

        data += byte

    return data


class SendFrame:
    '''
    A container for data to be transmitted to the target device. Instances of this class keep the input values so they
    can be retrieved later, if that is not a requirement it's easier to use :func:`~rctclient.frame.make_frame` which
    is called by this class internally to generate the byte stream. The byte stream stored by this class is generated on
    initialization and can be retrieved at any time using the ``data`` property.

    The frame byte stream that is generated by this class is meant to be sent to a device. The receiving side is
    implemented in :class:`ReceiveFrame`.

    `payload` needs to be encoded before it can be transmitted. See :func:`~rctclient.utils.encode_value`. It is
    ignored for ``READ`` commands.

    `address` is used for ``PLANT`` frames and otherwise ignored, when queried later using the ``address`` property, 0
    is returned for non-PLANT frames.

    :param command: The command to transmit.
    :param id: The message id.
    :param payload: Optional payload (ignored for read commands).
    :param address: Address for plant communication (untested, ignored for non-PLANT frame types).
    :param frame_type: Type of frame (standard or plant).
    '''

    _command: Command
    _id: int
    _address: int
    _frame_type: FrameType
    _payload: bytes

    _data: bytes

    def __init__(self, command: Command, id: int, payload: bytes = b'', address: int = 0,
                 frame_type: FrameType = FrameType.STANDARD) -> None:
        self._command = command
        self._id = id
        self._frame_type = frame_type

        self._payload = payload if command != Command.READ else b''
        self._address = address if frame_type == FrameType.PLANT else 0

        self._data = make_frame(self._command, self._id, self._payload, self._address, self._frame_type)

    def __repr__(self) -> str:
        return f'<SendFrame(command={self._command}, id=0x{self._id:X}, payload=0x{self._payload.hex()})>'

    @property
    def data(self) -> bytes:
        '''
        Returns the data after encoding, ready to be sent over the socket.
        '''
        return self._data

    @property
    def command(self) -> Command:
        '''
        Returns the command.
        '''
        return self._command

    @property
    def id(self) -> int:
        '''
        Returns the object ID.
        '''
        return self._id

    @property
    def address(self) -> int:
        '''
        Returns the address for plant communication. Note that this returns 0 unless plant-communication was requested.
        '''
        return self._address

    @property
    def frame_type(self) -> FrameType:
        '''
        Returns the type of communication frame.
        '''
        return self._frame_type

    @property
    def payload(self) -> bytes:
        '''
        Returns the payload (input data). To get the result to send to a device, use ``data``. Note that this returns
        an empty byte stream for ``READ`` commands, regardless of any input.
        '''
        return self._payload


class ReceiveFrame:
    '''
    Frame that is used to decode data received from the RCT device. This class can decode frames created via
    :class:`~rctmon.rct_frame.SendFrame`, too. To use, create an instance and feed data to the `consume` function
    until the frame was completly received. The `consume` function will return the amount of bytes it consumed.

    To decode the payload, use :func:`~rctclient.utils.decode_value`.

    :param frame_type: Type of frame (standard or plant).
    '''
    # frame complete yet?
    _complete: bool
    # did the crc match?
    _crc_ok: bool
    # parser in escape mode?
    _escaping: bool
    # received crc16 checksum data
    _crc16: int
    # frame length
    _frame_length: int
    # frame type
    _frame_type: FrameType
    # data buffer
    _buffer: bytearray
    # command
    _command: Command

    # ID, once decoded
    _id: int
    # raw received payload
    _data: bytes
    # address for plant frames
    _address: int

    _dbg: str

    def __init__(self, frame_type: FrameType = FrameType.STANDARD) -> None:
        self._complete = False
        self._crc_ok = False
        self._escaping = False
        self._crc16 = 0
        self._frame_length = 0
        self._frame_type = frame_type
        self._command = Command._NONE
        self._buffer = bytearray()
        self._dbg = ''

        # output data
        self._id = 0
        self._data = b''
        self._address = 0

    def __repr__(self) -> str:
        return f'<ReceiveFrame(cmd={self.command.name}, id={self.id:x}, address={self.address:x}, data={self.data.hex()})>'

    @property
    def debug(self) -> str:
        return self._dbg

    @property
    def id(self) -> int:
        '''
        Returns the ID. If the frame has been received but the checksum does not match up, 0 is returned.

        :raises FrameNotComplete: If the frame has not been fully received.
        '''
        if not self._complete:
            raise FrameNotComplete('The frame is incomplete')
        return self._id

    @property
    def data(self) -> bytes:
        '''
        Returns the received data payload. This is empty if there has been no data received or the CRC did not match.

        :raises FrameNotComplete: If the frame has not been fully received.
        '''
        if not self._complete:
            raise FrameNotComplete('The frame is incomplete')
        return bytes(self._data)

    @property
    def address(self) -> int:
        '''
        Returns the address if the frame is a plant frame (``FrameType.PLANT``) or 0.

        :raises FrameNotComplete: If the frame has not been fully received.
        '''
        if not self._complete:
            raise FrameNotComplete('The frame is incomplete')
        return self._address

    @property
    def command(self) -> Command:
        '''
        Returns the command.
        '''
        return self._command

    def complete(self) -> bool:
        '''
        Returns whether the frame has been received completely. If this returns True, do **not** ``consume()`` any more
        data with this instance, but instead create a new instance of this class for further consumption of data.
        '''
        return self._complete

    def consume(self, data: Union[bytes, bytearray]) -> int:
        '''
        Consumes data until the frame is complete. Returns the number of consumed bytes.

        :param data: Data to consume.
        :return: The amount of bytes consumed from the input data.
        '''

        # print(f'consume({len(data)} bytes: {data.hex()})')
        i = 0
        for d in data:
            i += 1
            c = bytes([d])
            self._dbg += f'read: {c.hex()}\n'

            # sync to start_token
            if len(self._buffer) == 0:
                self._dbg += '      buffer empty\n'
                if c == START_TOKEN:
                    self._dbg += '      start token found\n'
                    self._buffer += c
                continue

            if self._escaping:
                self._dbg += '      resetting escape\n'
                self._escaping = False
            else:
                if c == ESCAPE_TOKEN:
                    self._dbg += '      setting escape\n'
                    # set the escape mode and ignore the byte at hand.
                    self._escaping = True
                    continue

            self._buffer += c
            self._dbg += '      adding to buffer\n'

            # when enough data has been received to construct a frame, decode the length and check for completeness
            if len(self._buffer) >= FRAME_HEADER_WITH_LENGTH:
                self._dbg += '      buffer length >= header with length\n'
                if len(self._buffer) == FRAME_HEADER_WITH_LENGTH:
                    self._dbg += '      buffer length == header with length\n'
                    cmd = struct.unpack('B', bytes([self._buffer[1]]))[0]
                    self._dbg += f'      cmd: {cmd}\n'
                    if cmd == Command.LONG_RESPONSE or cmd == Command.LONG_WRITE:
                        self._frame_length = struct.unpack('>H', self._buffer[2:4])[0] + 2  # 2 byte length MSBF
                    else:
                        self._frame_length = struct.unpack('>B', bytes([self._buffer[2]]))[0] + 1  # 1 byte length

                    self._frame_length += 2  # 2 bytes header
                    self._dbg += f'      frame length: {self._frame_length}\n'

                else:
                    self._dbg += f'      buffer length {len(self._buffer)} > header with length\n'
                    if len(self._buffer) == self._frame_length + FRAME_LENGTH_CRC16:
                        self._dbg += '      buffer contains full frame\n'
                        self._complete = True
                        self._dbg += f'buffer: {self._buffer.hex()}\n'
                        try:
                            self.decode()
                        except FrameCRCMismatch as e:
                            e.consumed_bytes = i
                            raise
                        return i
        return i

    def decode(self):
        '''
        Decodes a received stream. This function is automatically called by :func:`consume` once a complete frame has
        been received.

        :raises FrameCRCMismatch: If the CRC checksum in the received data does not match up with the calculated
           values.
        '''
        # the crc16 checksum is 2 bytes at the end of the stream
        self._crc16 = struct.unpack('>H', self._buffer[-2:])[0]
        calc_crc16 = CRC16(self._buffer[1:-2])
        if self._crc16 == calc_crc16:
            self._crc_ok = True

            command = struct.unpack('>B', bytes([self._buffer[1]]))[0]
            self._command = Command(command)
            if self._command == Command.LONG_RESPONSE or self._command == Command.LONG_WRITE:
                data_length = struct.unpack('>H', self._buffer[2:4])[0]  # 2 byte length MSBF
                idx = 4
            else:
                data_length = struct.unpack('>B', bytes([self._buffer[2]]))[0]  # 1 byte length
                idx = 3

            data_length -= self._frame_type

            if self._frame_type == FrameType.PLANT:
                self._address = struct.unpack('>I', self._buffer[idx:idx + 4])[0]
                idx += 4

            self._id = struct.unpack('>I', self._buffer[idx:idx + 4])[0]
            # self._id_obj = find_by_id(self._id)
            idx += 4

            self._data = self._buffer[idx:idx + data_length]
            idx += data_length
        else:
            raise FrameCRCMismatch('CRC mismatch', self._crc16, calc_crc16)

    def is_complete(self) -> bool:
        '''
        Returns whether the frame has been fully received and decoded.
        '''
        return self._complete and self._crc_ok
