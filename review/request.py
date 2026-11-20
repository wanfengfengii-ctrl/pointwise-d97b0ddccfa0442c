from dataclasses import dataclass

from evidence.channels import ReadingPair
from evidence.codec import CalibrationArtifact


class UnknownChannelError(ValueError):
    pass


@dataclass(frozen=True)
class RatioRequest:
    inlet: str
    outlet: str


@dataclass(frozen=True)
class BoundRatioRequest:
    artifact: CalibrationArtifact
    request: RatioRequest
    pair: ReadingPair


def bind_request(artifact, request):
    if not isinstance(request, RatioRequest):
        raise ValueError('expected a ratio request')
    readings = artifact.readings
    try:
        inlet_index = readings.catalog.index_of(request.inlet)
        outlet_index = readings.catalog.index_of(request.outlet)
    except KeyError as error:
        raise UnknownChannelError(f'unknown public channel {error.args[0]!r}') from error
    return BoundRatioRequest(artifact, request, readings.pair(inlet_index, outlet_index))
