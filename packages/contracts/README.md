# API contracts

`src/api.d.ts` is generated from FastAPI's OpenAPI document. Do not edit it by hand.

From the repository root, run:

```bash
make contracts
```

The command exports the schema directly from the application factory, so it does not need a
running API or database connection. CI repeats the command and fails when the committed output
is stale.
