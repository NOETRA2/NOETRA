# Contributing

Include a small reproducible input, actual versus expected behaviour, and tests
for changes. Keep optional model/runtime execution explicit. Do not add downloads,
cloud uploads or credential access to an ordinary inference or analysis request.

Run `npm run check`. Python test dependencies are separately provisioned; document
the environment and run `python -m unittest discover -s tests/reconstruction`.
Do not turn a successful render or formal constraint check into an unsupported
reconstruction-accuracy claim. Preserve failed experiments and source provenance.
