from bench.wiring import ChannelDefinition
from calibration.fit import FittedCalibration
from evidence.projection import project_joint_domain, project_tolerance_domain
from evidence.register import IssueRegister


class WiringMismatchError(ValueError):
    pass


def issue_calibration(fitted: FittedCalibration, register: IssueRegister, wiring=None):
    revision = fitted.revision
    original_wiring = revision.cohort.wiring
    if wiring is not None:
        try:
            wiring = tuple(wiring)
        except TypeError as error:
            raise WiringMismatchError('expected frozen channel definitions') from error
        if any(not isinstance(channel, ChannelDefinition) for channel in wiring):
            raise WiringMismatchError('expected frozen channel definitions')
        if tuple(sorted(wiring, key=lambda channel: channel.name)) != original_wiring:
            raise WiringMismatchError(revision.revision_id)
    readings = project_joint_domain(fitted, original_wiring)
    return register.record(revision.revision_id, revision.fingerprint, readings)


def issue_tolerance_calibration(fitted: FittedCalibration, register: IssueRegister):
    revision = fitted.revision
    original_wiring = revision.cohort.wiring
    readings = project_tolerance_domain(fitted, original_wiring)
    return register.record_tolerance(
        revision.revision_id, revision.fingerprint, readings,
        fitted.least_squares.residual_sum, fitted.budget.limit,
    )
