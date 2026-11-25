# Holdout Tasks for package validation and self-evaluation

The Advisor deliberately withholds some or all Packages from a configurable random fraction of Tasks (Holdouts), so that Outcomes with and without experience can be compared on the same Goal Metrics. One mechanism answers two questions: whether a given Package improves Outcomes (the criterion for promoting a Candidate Package to Validated) and whether the Experience Base as a whole helps (the research claim). We accept that Holdout Tasks run with less knowledge than they could have, because without a comparison group "validated" would mean only "recurred" or "a human liked it", and before/after comparisons are confounded by everything else that changes in a Project.

## Considered Options

- **Before/after comparison of Project Metrics**: cheap and costs no Task performance, but drift in the Project, the models and the tools confounds it. Rejected as the primary method.
- **Offline replay only**: controlled, but it misses how real Tasks are distributed. Kept as a complement for controlled experiments, not a replacement.

## Consequences

- The Holdout fraction is configurable per Project and can be zero for production use. With zero Holdouts, no Package can reach Validated through measured effect, only through human fast-tracking.
- Holdout assignment must be recorded with each Task so the Analyst and Packager can stratify comparisons by Characterization.
- Do not "fix" Holdouts by giving those Tasks the experience anyway. That removes the comparison group.
