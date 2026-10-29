"""Let aiortc receive data a TURN server delivers as Data indications.

A TURN server forwards a peer's packets to the bot either as ChannelData or,
before a channel is bound for that peer, as a STUN Data indication. aioice only
reads ChannelData and drops Data indications, so when the browser's ICE checks
arrive that way through the relay the call never connects. Importing this module
teaches aioice to unwrap Data indications and hand their payload to ICE.
"""

from aioice import stun, turn

_DATA_ATTRIBUTE = (0x0013, "DATA", stun.pack_bytes, stun.unpack_bytes)
stun.ATTRIBUTES_BY_TYPE.setdefault(_DATA_ATTRIBUTE[0], _DATA_ATTRIBUTE)
stun.ATTRIBUTES_BY_NAME.setdefault(_DATA_ATTRIBUTE[1], _DATA_ATTRIBUTE)

_original_datagram_received = turn.TurnClientMixin.datagram_received


def _datagram_received(self, data, addr):
    if not turn.is_channel_data(data) and self.receiver is not None:
        try:
            message = stun.parse_message(data)
        except ValueError:
            message = None
        if (
            message is not None
            and message.message_method == stun.Method.DATA
            and message.message_class == stun.Class.INDICATION
            and "XOR-PEER-ADDRESS" in message.attributes
            and "DATA" in message.attributes
        ):
            self.receiver.datagram_received(
                message.attributes["DATA"], message.attributes["XOR-PEER-ADDRESS"]
            )
            return
    _original_datagram_received(self, data, addr)


turn.TurnClientMixin.datagram_received = _datagram_received
