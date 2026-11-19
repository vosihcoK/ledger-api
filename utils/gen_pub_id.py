import secrets

# Crockford base32: 32 characters, without I, L, O, U (they are confused with 1, 0 and curse words)
SOURCE_DATA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_LEN = 8  # ~ 1.1 TR variants

def generate_public_id() -> str:
    # random is predictable
    return "".join(secrets.choice(SOURCE_DATA) for _ in range(ID_LEN))
