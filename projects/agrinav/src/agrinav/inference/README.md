# Inference status

`inference_rice.py` is intentionally disabled. The historical implementation was incompatible
with the active model and treated every area outside a rice detection as a weed/spray target.
That complement-of-rice policy is unsafe: a missed, uncertain, stale, or invalid detection must
always result in no treatment.

A replacement runtime must not be added until it has:

- one canonical preprocessing/postprocessing path shared with evaluation;
- strict model/config/checkpoint compatibility checks;
- affirmative treatment evidence rather than detector absence;
- explicit no-treatment defaults for missing, uncertain, stale, or invalid inputs;
- independent safety vetoes and a tested decision schema;
- export-parity, latency, geometry, and fail-closed tests from the July 20 roadmap.

The old implementation has been moved to `../_archive/unsafe_inference/inference_rice.py`
(and remains in Git history) for audit purposes only. It must not be copied into active code
or connected to an actuator.
