import typing


class PendingReq(typing.NamedTuple):
    valid_ids: typing.Sequence
    resp_callable: typing.Callable[[typing.Any], None]
