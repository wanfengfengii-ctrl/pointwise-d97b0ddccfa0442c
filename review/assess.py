from evidence.codec import decode_artifact
from reports.publish import publish_report
from review.ratios import compute_ratio_set
from review.request import bind_request


def assess_and_publish(connection, artifact_text, request):
    bound = bind_request(decode_artifact(artifact_text), request)
    ratios = compute_ratio_set(bound)
    artifact = bound.artifact
    return publish_report(
        connection, artifact_id=artifact.artifact_id, revision_id=artifact.revision_id,
        revision_fingerprint=artifact.revision_fingerprint, inlet=bound.request.inlet,
        outlet=bound.request.outlet, ratios=ratios,
    )
