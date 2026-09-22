# R2 environment setup

Create one private bucket per environment and an object read/write token scoped only to that
bucket. Keep public access and `r2.dev` disabled.

Apply `cors.example.json` in the R2 dashboard after replacing the example origin with the exact
frontend origin. Add a lifecycle rule that aborts incomplete multipart uploads after one day.
Production exports should receive the 30-day expiry rule described in
`docs/architecture/10-storage.md` when that prefix ships.

Set `STORAGE_PROVIDER=r2`, the bucket name, S3 endpoint, access key, and secret key. Keep
`STORAGE_REGION=auto`. The application refuses incomplete credentials, non-`auto` regions, and
non-HTTPS endpoints outside local development.
