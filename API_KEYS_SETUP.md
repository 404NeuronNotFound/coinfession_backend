# API Keys Management Feature - Setup Instructions

## Overview
The API Keys management feature has been successfully added to the CoinFession backend. This feature allows users to securely store and manage their Anthropic and CoinGecko API keys with AES-256 encryption.

## Files Modified/Created

### New Files
1. **`api/encryption.py`** - Encryption utilities using Fernet (AES-128-CBC + HMAC)

### Modified Files
1. **`api/serializers.py`** - Added API Key serializers (APIKeyReadSerializer, APIKeySaveSerializer, APIKeyWriteSerializer)
2. **`api/views.py`** - Added API Key views (api_key_list_or_save, api_key_delete, api_key_ping)
3. **`api/urls.py`** - Added API Key URL patterns

### Unchanged Files
- **`api/models.py`** - No changes (APIKey model already exists)

## Installation Steps

### 1. Install Required Dependencies

```bash
pip install cryptography anthropic
```

Or add to `requirements.txt`:
```
cryptography>=41.0.0
anthropic>=0.25.0
```

### 2. Generate Encryption Key

Run this Python code **ONCE** to generate your encryption key:

```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

This will output something like:
```
xK4T9mZpL3vN8qR2wY5uH7jC1bF6dG0sA4eI9oP3tX8=
```

### 3. Add to Django Settings

Add to `backend/settings.py`:

```python
# API Key Encryption
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")
```

### 4. Add to Environment Variables

Add to your `.env` file:

```
FIELD_ENCRYPTION_KEY=xK4T9mZpL3vN8qR2wY5uH7jC1bF6dG0sA4eI9oP3tX8=
```

**⚠️ CRITICAL WARNING:**
- The same `FIELD_ENCRYPTION_KEY` must be used forever
- Changing it will make all existing encrypted keys unreadable
- Store this key securely (treat it like a database password)
- Never commit this key to version control
- Back it up in a secure location

### 5. Run Migrations (if needed)

The APIKey model should already exist, but if you need to create it:

```bash
python manage.py makemigrations
python manage.py migrate
```

## API Endpoints

### List API Keys
```
GET /api/api-keys/
Authorization: Bearer <token>

Response 200:
[
  {
    "id": 1,
    "provider": "anthropic",
    "key_suffix": "Xk4T",
    "plan": "paid",
    "last_used": "2026-04-15T10:32:00Z",
    "created_at": "2026-01-10T08:00:00Z",
    "is_connected": true
  }
]
```

### Save API Key
```
POST /api/api-keys/
Authorization: Bearer <token>
Content-Type: application/json

Body:
{
  "provider": "anthropic",
  "key": "sk-ant-api03-xxxxxxxxxxxxxxxxxxXk4T"
}

Response 201:
{
  "id": 1,
  "provider": "anthropic",
  "key_suffix": "Xk4T",
  "plan": "paid",
  "created_at": "2026-04-25T10:00:00Z",
  "full_key": "sk-ant-api03-xxxxxxxxxxxxxxxxxxXk4T",
  "warning": "Save this key now — it will not be shown again in full after this response."
}
```

### Delete API Key
```
DELETE /api/api-keys/anthropic/
Authorization: Bearer <token>

Response 204: No Content
```

### Test API Key (Ping)
```
POST /api/api-keys/ping/
Authorization: Bearer <token>
Content-Type: application/json

Body:
{
  "provider": "coingecko"
}

Response 200:
{
  "ok": true,
  "latency_ms": 238
}

OR

{
  "ok": false,
  "error": "Invalid API key"
}
```

## Security Features

1. **Encryption**: All API keys are encrypted using Fernet (AES-128-CBC + HMAC)
2. **Key Suffix Only**: Only the last 4 characters are stored in plain text for display
3. **One-Time Full Key Display**: Full key is only returned once in the save response
4. **Per-User Isolation**: Users can only access their own keys
5. **Provider Validation**: Keys are validated based on provider-specific formats
6. **Plan Detection**: Automatically detects plan tier based on key prefix

## Key Format Validation

### Anthropic
- Must start with `sk-ant`
- Plan: Always `paid` (no free tier)

### CoinGecko
- Must start with `CG-`
- Plan: `demo` if starts with `CG-demo`, otherwise `pro`

## Future Integration: AI Feedback View

When you create the AI feedback generation view, it should:

1. Look up the user's Anthropic API key:
```python
from .models import APIKey
from .encryption import decrypt_key
from django.utils import timezone

try:
    api_key_record = APIKey.objects.get(user=request.user, provider='anthropic')
    decrypted_key = decrypt_key(api_key_record.key_encrypted)
    
    # Use the key for Anthropic API call
    import anthropic
    client = anthropic.Anthropic(api_key=decrypted_key)
    # ... make API call ...
    
    # Update last_used timestamp after successful call
    api_key_record.last_used = timezone.now()
    api_key_record.save()
    
except APIKey.DoesNotExist:
    return Response(
        {'error': 'No Anthropic API key configured. Add your key in Settings → API Keys.'},
        status=503
    )
```

2. Return a 503 error if no key is configured
3. Update `last_used` timestamp after successful API calls

## Testing

### Test Encryption/Decryption
```python
from api.encryption import encrypt_key, decrypt_key

plain = "sk-ant-test-key-1234"
encrypted = encrypt_key(plain)
decrypted = decrypt_key(encrypted)
assert plain == decrypted
```

### Test API Key Save
```bash
curl -X POST http://localhost:8000/api/api-keys/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic", "key": "sk-ant-test-key-1234"}'
```

### Test API Key List
```bash
curl http://localhost:8000/api/api-keys/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test API Key Ping
```bash
curl -X POST http://localhost:8000/api/api-keys/ping/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "anthropic"}'
```

## Troubleshooting

### Error: "FIELD_ENCRYPTION_KEY is not set"
- Make sure you added `FIELD_ENCRYPTION_KEY` to your `.env` file
- Restart your Django server after adding the environment variable

### Error: "Failed to decrypt key"
- The encryption key has changed since the key was encrypted
- You must use the same `FIELD_ENCRYPTION_KEY` that was used to encrypt the keys
- If you lost the key, you'll need to delete all APIKey records and have users re-add them

### Error: "Anthropic keys must start with 'sk-ant'"
- The provided key doesn't match the expected format
- Verify the key is correct and complete

## Production Considerations

1. **Backup the Encryption Key**: Store `FIELD_ENCRYPTION_KEY` in a secure backup location
2. **Environment Variables**: Use proper secret management (AWS Secrets Manager, etc.)
3. **Key Rotation**: If you need to rotate the encryption key, you'll need to:
   - Decrypt all keys with the old key
   - Re-encrypt with the new key
   - Update all environment variables
4. **Monitoring**: Monitor `last_used` timestamps to identify unused keys
5. **Rate Limiting**: Consider adding rate limiting to the ping endpoint

## Summary

✅ API Keys management feature is fully implemented
✅ Secure encryption using Fernet (AES-128-CBC + HMAC)
✅ Support for Anthropic and CoinGecko providers
✅ Full CRUD operations (Create, Read, Delete)
✅ Connectivity testing (ping)
✅ Plan detection based on key format
✅ One key per provider per user
✅ Full key shown only once on save

The feature is ready to use once you complete the installation steps above.
