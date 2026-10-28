# Dashboard smoke-test fixtures

These fixtures provide the minimum NOMAD data needed to distinguish an empty
database from a broken dashboard query.

Before a deployment test, add the three `.archive.yaml` files to a writable
upload in the sandbox and make sure at least one `SubstrateMbe` also exists.

## New MBE Experiment

1. Open the dashboard through NOMAD GUI v2.
2. Verify that no API request returns 404 or 422.
3. Verify that TEST-HOLDER-01 appears.
4. Verify that unpublished visible substrates appear.
5. Select holder/substrate and verify that the view updates.

## Substrate Processing

1. Verify that Material, Crystal ID and Orientation are populated.
2. Verify that TEST-RECIPE-CLEAN-01 and TEST-RECIPE-ETCH-01 appear.
3. Verify that unpublished visible substrates appear.

## Error interpretation

- 404: API base/deployment path
- 401/403: authentication/permissions
- 422: endpoint/query/required-field contract
- 200 + empty result: check owner, filters and fixture data

## Local regression test

    python -m unittest tests.test_dashboard_api_contracts -v

The local test complements, but does not replace, the sandbox test.
