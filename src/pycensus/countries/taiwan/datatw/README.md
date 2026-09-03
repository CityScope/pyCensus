# Taiwan — data.gov.tw

**Source:** https://data.gov.tw/

Taiwan's open government data portal. Datasets are exposed individually, each
with its own REST endpoint, e.g.:

```
GET https://data.gov.tw/api/v1/rest/dataset/{dataset_id}
```

There's a "Population" dataset (population by city and gender) that's the
most directly relevant for census-style data — its dataset id needs to be
looked up on the portal (the id referenced in scraped notes,
`8bf6db3b-a131-4ee9-bbf1-114e45ac6a56`, should be re-verified against the
live portal before use, since dataset ids can change).

**Auth / token:** none — open API. `api_keys.json` has no entry for Taiwan.

**Data format:** JSON.

See `api_info.txt` (gitignored, not committed) in this directory for the raw
notes this README was derived from.
