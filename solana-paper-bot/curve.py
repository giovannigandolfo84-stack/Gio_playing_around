"""Is a Solana address a normal wallet (on the ed25519 curve) or a program-owned
address (off-curve, e.g. a liquidity pool, locker or bonding curve)?

Uses the `solders` library. If solders is not installed, falls back to an
identical pure-Python check so the offline demo still works.
"""
import hashlib

try:
    from solders.pubkey import Pubkey
    HAVE_SOLDERS = True
except ImportError:  # pragma: no cover
    HAVE_SOLDERS = False

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def b58decode(s):
    n = 0
    for ch in s:
        n = n * 58 + _B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out


def _bytes_on_curve(b):
    # Same rule as curve25519-dalek's decompress(): on-curve iff x^2 = (y^2-1)/(d*y^2+1) has a root.
    y = (int.from_bytes(b, "little") & ((1 << 255) - 1)) % _P
    u = (y * y - 1) % _P
    v = (_D * y * y + 1) % _P
    x2 = u * pow(v, _P - 2, _P) % _P
    return x2 == 0 or pow(x2, (_P - 1) // 2, _P) == 1


def is_on_curve(address):
    """True = normal wallet. False = program-owned (pool/locker/PDA)."""
    if HAVE_SOLDERS:
        return Pubkey.from_string(address).is_on_curve()
    b = b58decode(address)
    if len(b) != 32:
        raise ValueError("not a 32-byte Solana address: %s" % address)
    return _bytes_on_curve(b)


def find_program_address(seeds, program_id):
    """Only used by the demo to make realistic off-curve (pool) addresses."""
    if HAVE_SOLDERS:
        pda, _ = Pubkey.find_program_address(seeds, Pubkey.from_string(program_id))
        return str(pda)
    prog = b58decode(program_id)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(b"".join(seeds) + bytes([bump]) + prog + b"ProgramDerivedAddress").digest()
        if not _bytes_on_curve(h):
            return b58encode(h)
    raise ValueError("no PDA found")


def demo_wallet_address(label):
    """Only used by the demo: a made-up on-curve address. No keys involved."""
    i = 0
    while True:
        h = hashlib.sha256(("demo-wallet-%s-%d" % (label, i)).encode()).digest()
        if _bytes_on_curve(h):
            return b58encode(h)
        i += 1
