from evidence.codec import decode_artifact, decode_tolerance_artifact
from reports.publish import publish_report, publish_tolerance_report
from reports.tolerance_records import ToleranceReport
from review.ratios import compute_ratio_set
from review.request import bind_request
from review.tolerance import minimum_residual_sum, parse_intervals


def assess_and_publish(connection, artifact_text, request):
    bound = bind_request(decode_artifact(artifact_text), request)
    ratios = compute_ratio_set(bound)
    artifact = bound.artifact
    return publish_report(
        connection, artifact_id=artifact.artifact_id, revision_id=artifact.revision_id,
        revision_fingerprint=artifact.revision_fingerprint, inlet=bound.request.inlet,
        outlet=bound.request.outlet, ratios=ratios,
    )


def assess_tolerance_and_publish(connection, artifact_text, intervals):
    artifact = decode_tolerance_artifact(artifact_text)
    parsed = parse_intervals(artifact, intervals)
    minimum = minimum_residual_sum(artifact, parsed)
    within_budget = minimum is not None and minimum <= artifact.limit
    provisional = ToleranceReport(
        report_id=0, artifact_id=artifact.artifact_id,
        revision_id=artifact.revision_id,
        revision_fingerprint=artifact.revision_fingerprint,
        limit=artifact.limit, intervals=parsed,
        minimum_residual_sum=minimum, within_budget=within_budget,
    )
    return publish_tolerance_report(
        connection, artifact_id=artifact.artifact_id,
        revision_id=artifact.revision_id,
        revision_fingerprint=artifact.revision_fingerprint, report=provisional,
    )
