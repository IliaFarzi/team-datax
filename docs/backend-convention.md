# Environment Variable Naming Convention

This document defines how to name and organize environment variables across local `.env` files and GitHub Secrets.

---

## 1. General Rules
- Use **UPPERCASE** with **snake_case** (`MODULE_PROVIDER_ITEM`).
- Structure:
```

MODULE_PROVIDER_ITEM

```
- **MODULE** = functional area (e.g., `DB`, `AUTH`, `STORAGE`, `MAIL`, `LLM`, `VECTOR`, `EMBEDDING`, `FRONTEND`, `VPS`).
- **PROVIDER** = technology/vendor (e.g., `MONGO`, `MINIO`, `SMTP`, `OPENROUTER`, `GOOGLE`, `QDRANT`, `HUGGINGFACE`).
- **ITEM** = specific configuration (e.g., `URI`, `SECRET`, `ACCESS_KEY`, `MODEL`).

**Examples:**
```

DB_MONGO_URI
AUTH_GOOGLE_CLIENT_SECRET
STORAGE_MINIO_BUCKET_UPLOADS

```

---

## 2. Local `.env` Files
In local `.env` files, variables should be written exactly as specified (no environment prefix):

```

DB_MONGO_URI=mongodb://localhost:27017
AUTH_JWT_SECRET=local_secret
STORAGE_MINIO_BUCKET_UPLOADS=dev-uploads

```

---

## 3. GitHub Secrets Naming
For GitHub Actions or CI/CD pipelines, each variable must be prefixed with the environment:

- **Development secrets:** `DEV_<VARIABLE_NAME>`
- **Production secrets:** `PROD_<VARIABLE_NAME>`

**Examples:**
```

DEV_DB_MONGO_URI
DEV_AUTH_JWT_SECRET
DEV_STORAGE_MINIO_BUCKET_UPLOADS

PROD_DB_MONGO_URI
PROD_AUTH_JWT_SECRET
PROD_STORAGE_MINIO_BUCKET_UPLOADS

```

---

## 4. Mapping Between `.env` and GitHub Secrets

| Local `.env` Variable             | GitHub Secret (DEV)                 | GitHub Secret (PROD)                  |
|----------------------------------|-------------------------------------|---------------------------------------|
| `DB_MONGO_URI`                   | `DEV_DB_MONGO_URI`                  | `PROD_DB_MONGO_URI`                   |
| `AUTH_JWT_SECRET`                | `DEV_AUTH_JWT_SECRET`               | `PROD_AUTH_JWT_SECRET`                |
| `STORAGE_MINIO_BUCKET_UPLOADS`   | `DEV_STORAGE_MINIO_BUCKET_UPLOADS`  | `PROD_STORAGE_MINIO_BUCKET_UPLOADS`   |
| `LLM_OPENROUTER_API_KEY`         | `DEV_LLM_OPENROUTER_API_KEY`        | `PROD_LLM_OPENROUTER_API_KEY`         |
| `EMBEDDING_HUGGINGFACE_MODEL`    | `DEV_EMBEDDING_HUGGINGFACE_MODEL`   | `PROD_EMBEDDING_HUGGINGFACE_MODEL`    |

